# Agents 系統架構文件

## 概覽

這是一套以 **LangGraph** 為骨架的多 Agent 工作流程系統，透過 Python 進行協調，以 **Claude Code CLI**（`claude -p`）驅動各個 Agent。系統目標是對 `join-us` monorepo（Next.js 15 前端 + FastAPI 後端）執行端對端的自動化全端開發任務，包含規劃、實作、程式碼審查，以及失敗時的自動重試與修補。

---

## 目錄結構

```
agents/
├── main.py              # CLI 入口
├── workflow.py          # LangGraph 工作流程定義
├── state.py             # AgentState 型別定義
├── claude_runner.py     # Claude Code CLI 封裝層
├── skill_loader.py      # Skill 注入器
├── requirements.txt     # Python 相依套件
├── Dockerfile           # 容器映像設定
├── docker-compose.yml   # Docker Compose 編排
├── nodes/
│   ├── analyze_plan.py  # 規劃 Agent 節點
│   ├── human_confirm.py # 人工確認中斷點
│   ├── execute.py       # 執行 Agent 節點
│   └── review.py        # 程式碼審查 Agent 節點
└── tools/
    ├── file_tools.py    # LangChain 檔案工具（未使用）
    └── shell_tools.py   # LangChain Shell 工具（未使用）
```

---

## 核心資料結構：`AgentState`

所有節點之間以一個不可變的 `TypedDict` 傳遞狀態，完整定義如下：

```python
class AgentState(TypedDict):
    task: str              # 使用者輸入的任務描述
    analysis: str          # 規劃節點產出的摘要
    plan: list[str]        # 有序的 TASK 清單
    execution_result: str  # 執行節點的輸出
    review_result: str     # 審查節點的完整報告
    review_level: str      # "重寫" | "修補" | ""
    status: str            # "pending" | "approved" | "needs_revision" | "error" | "confirmed" | "aborted"
    iteration: int         # 重試計數器（上限 3）
```

每個節點讀取需要的欄位、寫入自己負責的欄位，節點之間**不直接呼叫彼此**，全部透過狀態字典溝通。

---

## 工作流程：LangGraph StateGraph

### 流程圖

```
START
  │
  ▼
┌─────────────┐
│ analyze_plan│  讀取任務與現有程式碼，產出分析與 TASK 清單
└──────┬──────┘
       │
       ▼
┌──────────────┐
│ human_confirm│  顯示計畫摘要，等待人工輸入 y 確認
└──────┬───────┘
       │
       ├─── 輸入 y (confirmed) ─────────────────────┐
       │                                             ▼
       │                                    ┌─────────────┐
       │                                    │   execute   │  依序執行所有 TASK，修改程式碼，跑測試
       │                                    └──────┬──────┘
       │                                           │
       │                                           ▼
       │                                    ┌─────────────┐
       │                                    │   review    │  以唯讀方式驗證實作完整性與程式碼品質
       │                                    └──────┬──────┘
       │                                           │
       │                      ┌────────────────────┤
       │                      │                    │
       │              通過 (Pass)         有阻塞問題 + 未達上限
       │                      │                    │
       │                      ▼                    ▼
       │                   END ✅         increment_iteration
       │                                           │
       │                                           ▼
       │                                    回到 analyze_plan
       │                                  （帶入 review_result
       │                                   與 review_level）
       │                                    再次等待人工確認
       │
       └─── 非 y (aborted / error) ────────────→ END 🛑
```

> 有阻塞問題且已達 iteration 上限 (3) 時，`route_after_review` 亦路由至 END ⚠️。

### 關鍵函式

| 函式 | 所在檔案 | 說明 |
|---|---|---|
| `route_after_confirm()` | `workflow.py` | 條件路由：`confirmed` → execute；`aborted` / `error` → END |
| `route_after_review()` | `workflow.py` | 條件路由：判斷是否通過、是否需要重試 |
| `increment_iteration()` | `workflow.py` | 增加重試計數，重設 status 為 `pending` |
| `build_workflow()` | `workflow.py` | 編譯 `StateGraph`，回傳可執行的 app |

常數 `MAX_ITERATIONS = 3`：超過後強制結束，避免無限迴圈。

---

## 三個 Agent 節點詳述

### 1. `analyze_plan`（規劃 Agent）

**職責：** 扮演資深全端工程師，讀取任務需求與既有程式碼，輸出結構化的實作計畫文件。

**工具權限：**

| 情境 | 模式 | 可用工具 |
|---|---|---|
| 第一次規劃 | `plan` | Read, Write, Glob, Grep |
| 重新規劃（審查失敗後） | `full` | Read, Write, Edit, Bash, Glob, Grep |

重新規劃時開放 `Bash` 是因為需要根據 `review_level` 決定是否執行 git 回滾：
- **重寫（rewrite）**：執行 `git stash` 或 `git checkout -- .` 丟棄現有變更，重頭規劃
- **修補（patch）**：保留現有變更，僅追加差異修補計畫

**輸出格式：**
```
## 分析
[2-5 行：任務摘要、受影響檔案、潛在問題]

## 計畫
TASK 1: [操作] [路徑] — [說明]
TASK 2: [操作] [路徑] — [說明]
...
TASK N: 更新 tabletop/docs/ 與 tabletop-backend/docs/（必要項目）
```

**解析邏輯：**
- 使用 `re.findall(r'TASK \d+: (.+)', ...)` 擷取 TASK 清單（Fallback：`STEP \d+:`）
- 每個 TASK 成為 `state["plan"]` 中的一個元素
- 計畫文件寫入 `docs/superpowers/plans/YYYY-MM-DD-<feature>.md`

**注入的 Skills：**
`writing-plans`（完整內容）、`architecture-patterns`、`architecture-decision-records`、`next-best-practices`、`test-driven-development`

---

### 2. `human_confirm`（人工確認閘道）

**職責：** 在規劃完成後、執行開始前，暫停工作流程，讓使用者審閱計畫並決定是否繼續。

**行為：**
- 列印分析摘要、TASK 清單（含數量），以及最新計畫文件路徑
- 偵測到非互動式 stdin（如管道重導向）時自動中止，避免無限等待
- 輸入 `y`（不區分大小寫）→ 返回 `status: "confirmed"` → 工作流程繼續至 `execute`
- 輸入任何其他值、EOFError、KeyboardInterrupt → 返回 `status: "aborted"` → 工作流程結束

**注意：** review 失敗觸發重新規劃時，下一輪 `analyze_plan` 完成後同樣需要再次人工確認。

---

### 3. `execute`（執行 Agent）

**職責：** 扮演資深全端工程師，依計畫依序執行所有 TASK，完成程式碼修改、文件同步、測試執行。

**工具權限：** `full`（Read, Write, Edit, Bash, Glob, Grep）  
**Timeout：** 900 秒（15 分鐘）

**強制執行前置步驟：**
1. 讀取 `tabletop/docs/` 與 `tabletop-backend/docs/` 所有現有文件
2. 如目錄不存在則建立
3. 嚴格依 TASK 順序執行，不得跳過或重排

**重要規則：**

| 規則 | 說明 |
|---|---|
| i18n 同步 | 任何前端文字變更都必須同步更新 `messages/zh.json` 與 `messages/en.json` |
| 型別同步 | TypeScript 型別必須與 Python 模型保持一致 |
| 禁止安裝 | 不可在執行期執行 `pip install` 或 `npm install` |

**允許的 Bash 指令：** `alembic`、`npm run lint`、`pytest`、`docker`、`git`、`ls`、`cat`、`grep`、`find`、`node`

**測試執行（所有 TASK 完成後）：**
```bash
cd tabletop && npm run test
cd tabletop && npm run test:e2e
cd tabletop-backend && pytest
# 或 Docker 環境：
docker exec $(docker ps -q --filter ancestor=tabletop-backend) bash -c "cd /app && pytest"
```

**自動修復：** 測試失敗時自動分析錯誤、修復程式碼、重跑所有測試，最多重試 3 次。

**注入的 Skills：**
`frontend-design`、`next-best-practices`、`vercel-react-best-practices`、`vercel-composition-patterns`、`test-driven-development`、`docker-expert`

---

### 4. `review`（程式碼審查 Agent）

**職責：** 扮演資深程式碼審查者，以唯讀方式驗證實作完整性、程式碼品質、文件同步，以及 DB 遷移正確性。

**工具權限：** `check`（Read, Glob, Grep, Bash）—**不可修改任何檔案**  
**Timeout：** 300 秒  
**Skill：** 載入 `requesting-code-review` 中的 `code-reviewer.md`

**驗證清單：**

| 項目 | 內容 |
|---|---|
| 計畫完整性 | 列出所有未完成的 TASK |
| 程式碼品質 | 依 code-reviewer.md 規則檢查 |
| 文件同步 | 確認 `tabletop/docs/` 與 `tabletop-backend/docs/` 已更新 |
| 遷移審查 | 如有 DB 變更，檢查 `tabletop-backend/migrations_extra/`（**非** `migrations/`）|

**使用 `git diff` 查看所有實際變更。**

**輸出格式：**
```
[完整審查報告（繁體中文）]

各 TASK 狀態：
✅ TASK 1: [說明]
❌ TASK 2: [失敗原因]

問題嚴重性分層：
- Critical: [問題]
- Important: [問題]
- Minor: [問題]

Ready to merge? Yes / No

（若 No，必須附上：）
REVIEW_LEVEL: 重寫
（或）
REVIEW_LEVEL: 修補
```

**REVIEW_LEVEL 判斷標準：**

| 等級 | 觸發條件 |
|---|---|
| **重寫** | 核心邏輯錯誤、架構偏離、多個相互關聯的根本問題、大量 TASK 未完成 |
| **修補** | 小型 Bug、型別不符、缺少 i18n key、個別 TASK 失敗、小幅修正 |

**審查報告儲存至：** `docs/nodes/review/YYYY-MM-DD-iterN.md`

---

## 節點間協作機制

### 1. 狀態字典傳遞
每個節點讀取前一個節點填入的欄位，再將自己的輸出寫入對應欄位，例如：
- `analyze_plan` → 填入 `analysis`、`plan`
- `human_confirm` → 填入 `status`（`"confirmed"` 或 `"aborted"`）
- `execute` → 填入 `execution_result`、`status`
- `review` → 填入 `review_result`、`review_level`、`status`

### 2. 檔案系統作為共享記憶
| 產出物 | 路徑 | 讀寫者 |
|---|---|---|
| 計畫文件 | `docs/superpowers/plans/YYYY-MM-DD-*.md` | `analyze_plan` 寫，`execute` 讀 |
| 審查報告 | `docs/nodes/review/YYYY-MM-DD-iterN.md` | `review` 寫，下次迭代的 `analyze_plan` 可讀 |
| 業務文件 | `tabletop/docs/`、`tabletop-backend/docs/` | `execute` 寫，`review` 驗證 |

### 3. Git Diff 作為稽核媒介
`review` 節點執行 `git diff` 取得所有實際變更，而非僅依賴執行節點的自述，確保審查基於事實。

### 4. Skill 系統作為知識注入
`skill_loader.py` 從 `~/.claude/skills/` 讀取 Claude Code Skill 文件，以 `<skills>` XML 區塊注入系統提示，讓各節點具備對應的最佳實踐知識，而無需硬編碼在 prompt 中。

### 5. 反饋迴圈
```
Iteration 1:
  analyze_plan → human_confirm [y] → execute → review → "需要修補" (review_level="修補")
                                                                │
                                                                ▼
Iteration 2:
  analyze_plan（接收 review_result、保留現有變更）
    → human_confirm [y]（再次等待確認）
    → execute（執行差異修補）
    → review → "通過"
    → END ✅
```

---

## Claude Runner：CLI 封裝層

`claude_runner.py` 是整個系統的技術核心，封裝了對 `claude -p` CLI 的所有呼叫。

### 工具權限預設集

| 名稱 | 工具 | 用途 |
|---|---|---|
| `readonly` | Read, Glob, Grep | 安全探索 |
| `plan` | Read, Write, Glob, Grep | 建立文件 |
| `full` | Read, Write, Edit, Bash, Glob, Grep | 完整程式碼修改 |
| `check` | Read, Glob, Grep, Bash | 驗證，不修改檔案 |

### 執行流程
1. 組合指令：`claude -p --allowedTools {tools} --output-format stream-json --verbose`
2. 以 subprocess 啟動，即時串流 stdout JSON 事件
3. 解析 `assistant`、`tool_use`、`tool_result` 事件並即時印出（dimmed 格式）
4. 解析最終 `result` 事件取得文字輸出與 token 用量
5. 回傳 `ClaudeResult`（含文字、elapsed time、token stats、快取統計）

### Token / Rate-Limit 暫停機制

`call_claude()` 包含一個 `while True` 重試迴圈：若偵測到錯誤訊息含有以下關鍵字（`rate limit`、`429`、`credit balance`、`billing` 等），則**暫停工作流程**並在 terminal 提示使用者：

- 按 **Enter** → 等待配額更新後重新呼叫 Claude
- 輸入 **`q`** 後按 Enter → 中止程序並回傳原始錯誤結果

stdin 已關閉（非 TTY / pipe EOF）時自動中止，避免無限等待。此機制讓長時間任務在遇到 API 限流時不需重頭開始，只需等待後繼續。

### 模型對應
```python
MODEL_IDS = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-7",
}
```

---

## 使用技術彙整

### Python 層

| 技術 | 版本 | 用途 |
|---|---|---|
| **LangGraph** | ≥0.2.0 | StateGraph 工作流程編排、條件路由、節點串接 |
| **python-dotenv** | ≥1.0.0 | 讀取 `.env` 環境變數 |
| **Python** | 3.11 | 執行環境 |

### Claude Code CLI 層

| 技術 | 說明 |
|---|---|
| **Claude Code CLI** (`@anthropic-ai/claude-code`) | 以 `claude -p` 啟動 Agent，使用本地身份驗證（不需要 API Key） |
| **stream-json output** | 即時串流 JSON 事件，支援 `assistant`、`tool_use`、`tool_result`、`result` 類型 |
| **Built-in Tools** | Read、Write、Edit、Bash、Glob、Grep（Claude Code 原生工具） |
| **Skill System** | `~/.claude/skills/` 中的 Markdown 文件，動態注入 Agent 系統提示 |

### 容器化層

| 技術 | 說明 |
|---|---|
| **Docker** | 以 `python:3.11-slim` 為基底，加裝 Node.js 20 執行 Claude Code CLI |
| **Docker Compose** | 掛載整個 monorepo（`../:/repo`）與使用者 Claude 設定（`~/.claude:/home/agent/.claude`） |
| **非 root 使用者** | `agent` 使用者執行 `claude --dangerously-skip-permissions`，符合 Claude Code 安全要求 |

### 目標專案技術棧

| 層 | 技術 |
|---|---|
| 前端 | Next.js 15 App Router、TypeScript、Tailwind CSS 4、Zustand、next-intl、Supabase Auth |
| 後端 | Python FastAPI、SQLModel、Alembic、Supabase、Firebase Cloud Messaging |
| 測試 | Vitest（前端單元）、Playwright（E2E）、Pytest + aiosqlite（後端） |

---

## CLI 入口：`main.py`

### 完整工作流程模式
```bash
python -m agents.main "幫我在後端新增一個 GET /tables/featured 端點"
```

### 單節點偵錯模式
```bash
python -m agents.main --node analyze_plan "任務描述"
python -m agents.main --node execute --state-file /tmp/state.json "任務描述"
python -m agents.main --node review "任務描述"
```

State file 可預載 `plan`、`execution_result` 等欄位，便於針對單一節點除錯。

---

## 未使用的元件

`tools/` 目錄下的 `file_tools.py` 與 `shell_tools.py` 定義了 LangChain 風格的工具物件，但目前**並未被任何節點使用**。現行架構完全依賴 Claude Code CLI 的原生工具，這些檔案可能是早期 LangChain-only 架構的遺留，或作為備用執行路徑的參考。

---

## 總結

| 面向 | 細節 |
|---|---|
| 架構模式 | LangGraph StateGraph + 4 個節點 + 人工確認閘 + 審查驅動的反饋迴圈 |
| 節點數量 | 4（規劃、人工確認、執行、審查） |
| 最大重試次數 | 3 次迭代後強制結束 |
| 執行模型 | 序列執行 + 迭代精修（審查驅動） |
| 語言 | Python 協調層 + 繁體中文提示 |
| 目標架構 | Next.js 15 前端 + FastAPI 後端 monorepo |
| 驅動方式 | Claude Code CLI（本地認證，非 API Key） |
| 狀態傳遞 | 不可變 TypedDict 流經整個工作流程 |
| 產出物 | 計畫文件、執行摘要、審查報告、程式碼變更 |
