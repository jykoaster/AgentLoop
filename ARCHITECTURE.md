# Agents 系統架構文件

## 概覽

這是一套以 **LangGraph** 為骨架的多 Agent 工作流程系統，透過 Python 進行協調，以 **Claude Code CLI**（`claude -p`）驅動各個 Agent。系統本身不假設固定的目標技術棧——透過 `project_context.py` 動態偵測工作區內各專案的 `CLAUDE.md` / `AGENT.md`，再由各節點依偵測結果自行判斷架構、慣例與適用的 Skill。目標是對任一 monorepo / 專案執行端對端的自動化開發任務：規劃、人工確認、實作、程式碼審查，以及失敗時的自動重試與修補。

---

## 目錄結構

```
AgentLoop/
├── main.py               # CLI 入口
├── workflow.py            # LangGraph 工作流程定義
├── state.py                # AgentState 型別定義
├── claude_runner.py         # Claude Code CLI 封裝層
├── skill_loader.py           # Skill 注入器
├── project_context.py         # 動態偵測工作區內各專案的 CLAUDE.md / AGENT.md
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── nodes/
│   ├── analyze_plan.py     # 規劃 / 重新規劃 Agent 節點
│   ├── human_confirm.py    # 人工確認中斷點
│   ├── execute.py          # 執行 Agent 節點
│   └── review.py           # 程式碼審查 Agent 節點
└── docs/
    └── nodes/review/        # review 節點產出的審查報告（YYYY-MM-DD-iterN.md）
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
    review_blocking: bool  # review_node 的最終路由結論：True → 重新規劃；False → 通過
    status: str            # "pending" | "needs_revision" | "error" | "confirmed" | "aborted"
    iteration: int         # 重試計數器（上限 3）
    human_feedback: str    # 使用者在 human_confirm 拒絕計畫時填寫的修改意見
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
       │                                    │             │  （嚴重影響功能的問題自動判定；
       │                                    │             │   非嚴重的修改建議則列出讓人工
       │                                    │             │   勾選要修哪幾條，見下方說明）
       │                                    └──────┬──────┘
       │                                           │
       │                      ┌────────────────────┤
       │                      │                    │
       │           review_blocking=False   review_blocking=True + 未達上限
       │                      │                    │
       │                      ▼                    ▼
       │                   END ✅         increment_iteration
       │                                           │
       │                                           ▼
       │                                    回到 analyze_plan
       │                                  （帶入 review_result
       │                                   與 review_level，
       │                                   只針對 review 結果 grill）
       │                                    再次等待人工確認
       │
       ├─── 輸入 N + 填寫修改意見 ──────────→ analyze_plan
       │    (needs_revision + human_feedback)  （帶入 human_feedback
       │                                        重新規劃後再次確認）
       │
       └─── 輸入 N + 空白 (aborted) ────────→ END 🛑
```

> `review_blocking=True` 且已達 iteration 上限 (3) 時，`route_after_review` 亦路由至 END ⚠️。

### 關鍵函式

| 函式                    | 所在檔案      | 說明                                                                                  |
| ----------------------- | ------------- | ------------------------------------------------------------------------------------- |
| `route_after_confirm()` | `workflow.py` | 條件路由：`confirmed` → execute；`needs_revision` → replan；`aborted` / `error` → END |
| `route_after_review()`  | `workflow.py` | 條件路由：只讀取 `review_node` 已判定好的 `review_blocking`（不再自行解析 review 文字），配合 iteration 上限決定是否重試 |
| `increment_iteration()` | `workflow.py` | 增加重試計數，重設 status 為 `pending`                                                |
| `build_workflow()`      | `workflow.py` | 編譯 `StateGraph`，回傳可執行的 app                                                   |

常數 `MAX_ITERATIONS = 3`：超過後強制結束，避免無限迴圈。

---

## 動態專案偵測：`project_context.py`

系統不把目標專案的目錄結構寫死在 prompt 裡。`list_project_docs()` 掃描工作區根目錄下每個子目錄，找出含有 `CLAUDE.md` / `AGENT.md` / `AGENTS.md` 的專案；`build_project_docs_hint()` 把偵測到的清單組成提示區塊，注入 `analyze_plan`、`execute`、`review` 三個節點的 system prompt，讓 Agent 自行判斷本次任務涉及哪個（或哪些）專案、該讀哪份說明檔。

若任務同時涉及多個專案（例如前後端分屬不同目錄），Agent 需分別讀取各自的說明檔；找不到任何說明檔時，退回用 Read/Glob/Grep 自行探索程式碼風格。

---

## 四個節點詳述（3 個 Agent + 1 個人工確認閘）

### 1. `analyze_plan`（規劃 Agent）

**職責：** 扮演資深全端工程師，依觸發來源分成三種模式，輸出結構化的實作計畫文件。

**模式判斷（依 `AgentState` 欄位）：**

| 模式                    | 觸發條件                                     | 工具   | 模型 |
| ----------------------- | -------------------------------------------- | ------ | ---- |
| 初始規劃                | `review_result` 與 `human_feedback` 皆為空   | `plan` | opus |
| 重新規劃（review 觸發） | `review_result` 非空                         | `full` | opus |
| 依人工意見調整計畫      | `human_feedback` 非空且 `review_result` 為空 | `plan` | opus |

重新規劃額外開放 `Edit` 是因為需要依 `review_level` 決定是否執行 git 回滾：

- **重寫（rewrite）**：`git stash`（失敗則 `git checkout -- .`）丟棄現有變更，重頭規劃
- **修補（patch）**：保留現有變更，僅追加差異修補計畫

`plan` 工具集本身也含 `Bash`（`claude_runner.TOOL_PRESETS`），供初始規劃用 `git branch --show-current` 判斷規格文件檔名裡的 branch name，不含 `Edit`（規劃階段只新增規格文件，不改既有程式碼）。

**任務開始時詢問規劃文件檔名：**

初始規劃模式進入 `analyze_plan_node()` 時，若 `state["plan_filename"]` 尚未設定，會在呼叫 Claude 之前先用 `_ask_plan_filename()` 直接向終端機使用者提問（不透過 Claude、不是 grilling 機制的一部分），取得的值全程保存在 `AgentState["plan_filename"]`，供本次任務所有輪次（含後續 replan／human-revise）的規格檔名沿用。若使用者留空，交由 Claude 改用 `git branch --show-current` 取得的目前 branch 名稱作為檔名。非互動式環境或使用者直接按 Enter／中止時留空繼續，不阻塞流程。

**互動式釐清（grilling）機制：**

三種模式的 prompt 都要求 Claude 在需要人工決策時，該輪回應「只能」輸出固定格式的 `QUESTION: <問題>` + 數字選項，而不得自行臆測。這由 `_run_with_grilling()` 迴圈驅動：

1. `call_claude()` 執行後，偵測輸出是否以 `QUESTION:` 開頭
2. 若是，暫停等待使用者輸入（非 TTY 環境自動採用 Agent 自己建議的答案繼續，避免無限等待）
3. 帶著使用者回覆、以 `--resume <session_id>` 延續同一個 Claude session 繼續對話，避免每輪重新給上下文
4. 最多 15 輪（`_MAX_QUESTIONS`），超過則中止釐清、採用當前結果繼續

**依模式而異的提問規則：**

- **初始規劃 / 依人工意見調整計畫**：完整 grill-with-docs 流程——依 grilling 逐一提問，過程中依 domain-modeling 即時更新 `CONTEXT.md` / `docs/adr/`
- **重新規劃（review 觸發）**：**只針對 review 結果 grill**——針對審查標記的每個問題點逐一提出質疑性問題（判斷是否成立、修正方向如何取捨），不要求重新走一遍完整的 grill-with-docs 釐清，也不強制 domain-modeling 文件同步

**三種 Prompt 版本：**

| 版本                   | 用途                                                                                                                                                                               |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_SYSTEM_INITIAL`      | 全新任務規劃：Read/Glob/Grep 探索 → grill-with-docs 互動釐清（同步 domain-modeling）→ 依 `_SPEC_TEMPLATE`（覆蓋 to-spec 原本範本，見下方「規格文件範本」）撰寫規格文件 → 轉譯為 TASK 清單 |
| `_SYSTEM_REPLAN`       | 帶入 `<<REVIEW_CONTEXT>>`（`review_result`，截斷至最後 3000 字）與 `<<REVIEW_LEVEL>>`；依「重寫／修補」分流見上，並用專屬的 `_REVIEW_QUESTION_PROTOCOL` 針對 review 結果逐點 grill |
| `_SYSTEM_HUMAN_REVISE` | 帶入 `<<HUMAN_FEEDBACK>>`（`human_confirm` 收到的使用者修改意見）：理解意見（不夠明確則提問）→ 視需要重讀程式碼 → 視需要更新 domain-modeling → 更新既有規格文件                    |

**輸出格式：**

```
## 分析
[2-5 行摘要：需求／問題根因、涉及檔案、潛在問題或修正方向]

## 計畫
TASK 1: [操作] [路徑] — [說明]
TASK 2: [操作] [路徑] — [說明]
...
TASK N: [視該任務所屬專案的說明檔慣例，可能包含測試 TASK 與文件更新 TASK]
```

**解析邏輯：**

- 使用 `re.findall(r'TASK \d+: (.+)', ...)` 擷取 TASK 清單（Fallback：`STEP \d+:`）
- 每個 TASK 成為 `state["plan"]` 中的一個元素
- 規格文件寫入 `docs/superpowers/plans/<filename>.md`（`to-spec` 略過發布 issue tracker 的步驟；`<filename>` 為任務開始時使用者輸入的自訂檔名，留空則改用 Bash 執行 `git branch --show-current` 取得的目前 branch 名稱，並將 `/` 等字元替換為 `-`）。重新規劃／依人工意見調整計畫時沿用同一個檔名，不重新命名
- 涉及新增或修改行為的 TASK，須額外排入對應的「撰寫／更新測試」TASK，讓 `execute` 有明確依據依 tdd skill 執行紅-綠循環；純文件、設定調整或不改變行為的重構可不需要
- 是否需要新增「更新文件」TASK，依該任務所屬專案的 `CLAUDE.md` / `AGENT.md` 判斷：說明檔要求同步維護 `docs/` 商業邏輯說明文件才排入，未提及此類慣例則不強制新增

**注入的 Skills（完整內容）：** `grill-with-docs`、`grilling`、`domain-modeling`、`to-spec`；另列名稱（不注入完整內容）：`tdd`

**規格文件範本（`_SPEC_TEMPLATE`，覆蓋 to-spec 原本的範本）：** 固定章節為 `Problem Statement` / `Solution` / `User Stories` / `Implementation Decisions`（含「影響模組」「關鍵機制與流程」小節）/ `Testing Strategy`（含「Seam（測試接縫）」「測試案例矩陣（Test Matrix）」小節）/ `Out of Scope` / `Technical Debt & Follow-up Notes`，開頭另附 `Date`、`Scope`。三種模式（初始規劃、重新規劃、依人工意見調整計畫）撰寫或更新規格文件時都必須依此範本，章節結構不可增減，**每個章節都必須填寫內容，沒有內容也要填「無」**，不可留白或整段刪除；範本內的具體條目（如 SOT / Error Handling Flow / i18n、Seam 首選/次要接縫、Test Matrix 範例列）僅為格式參考，非固定必填項目。

---

### 2. `human_confirm`（人工確認閘道）

**職責：** 在規劃完成後、執行開始前，暫停工作流程，讓使用者審閱計畫並決定是否繼續。

**行為：**

- 列印分析摘要、TASK 清單（含數量），以及最新計畫文件路徑
- 偵測到非互動式 stdin（如管道重導向）時自動中止，避免無限等待
- 輸入 `y`（不區分大小寫）→ 返回 `status: "confirmed"` → 工作流程繼續至 `execute`
- 輸入非 `y` 後，再輸入修改意見（非空白）→ 返回 `status: "needs_revision"` + `human_feedback` → 回到 `analyze_plan` 重新規劃
- 輸入非 `y` 後，直接按 Enter（空白）、EOFError、KeyboardInterrupt → 返回 `status: "aborted"` → 工作流程結束

**注意：** review 失敗觸發重新規劃時，下一輪 `analyze_plan` 完成後同樣需要再次人工確認。

---

### 3. `execute`（執行 Agent）

**職責：** 扮演資深全端工程師，依計畫依序執行所有 TASK，完成程式碼修改、文件同步、測試執行。系統不假設任何特定技術棧。

**工具權限：** `full`（Read, Write, Edit, Bash, Glob, Grep）
**Timeout：** 900 秒（15 分鐘）

**執行前準備（必須完成）：**

1. 依 `project_context.py` 提供的專案清單，判斷本次任務涉及哪個（或哪些）專案目錄，Read 讀取其 `CLAUDE.md` / `AGENT.md`，了解架構、指令（測試、lint、build 等）、目錄慣例、程式碼規範與技術棧；找不到說明檔則自行 Read/Glob/Grep 探索並比對現有風格
2. 依偵測到的技術棧，**自行**從可用的 skills 中挑選並使用適合的其他 skill（例如 Vue 專案適用 `vue-best-practices`、Nuxt + Vitest 專案適用 `nuxt-vitest-msw`）——不寫死任何特定技術棧的 skill 清單。`tdd` 已是固定注入的 skill（見下方「注入的 Skills」），不需要另外挑選
3. 若該專案 `docs/` 目錄存在，讀取其下所有現有文件，了解商業邏輯說明；`docs/` 目錄不存在時不需自行建立

**執行方式：** 以 `implement` skill 的流程為主軸，但有以下覆蓋規則：

- **不**執行 implement 流程中「commit 到目前分支」的步驟——是否提交由使用者事後決定
- **不**自行呼叫 `/code-review`——後續有獨立的 Review Agent 依專案規格審查本次修改
- TASK 清單中若有「撰寫／更新測試」的 TASK，**必須**依 `tdd` skill 的紅-綠循環執行：先寫會失敗的測試，再寫最小可行實作讓測試通過，最後重構；不可先完成其他 TASK 的實作、事後才回頭補測試
- 其餘步驟（定期執行型別檢查與單一測試檔案、最後執行完整測試）依 implement skill 原本流程進行

嚴格依序完成 TASK 清單中的每一項；先 Read 再 Write/Edit，避免覆蓋不相關程式碼；風格、命名、目錄結構、i18n／型別／auto-generated 檔案等規則，一律依該專案 `CLAUDE.md` / `AGENT.md` 的說明判斷，不硬編碼在 prompt 裡。

**文件同步要求：** 是否需要同步更新文件，依該任務所屬專案的 `CLAUDE.md` / `AGENT.md` 判斷——說明檔要求同步維護 `docs/` 商業邏輯說明文件才需處理（依 TASK 清單中對應的文件更新 TASK 執行，或在說明檔明確要求但 TASK 清單未包含時主動補上）；說明檔未提及此類慣例時不需要主動撰寫或更新文件。

**強制測試與自動修復：** 依該專案 `CLAUDE.md` / `AGENT.md` 中列出的測試指令執行測試；若說明檔未列出，探索 `package.json` / `pyproject.toml` 等設定檔判斷正確指令。測試失敗時分析錯誤並修復、重跑，最多重試 3 次；3 次後不論結果如何都繼續輸出最終摘要。

**最終輸出格式（文字摘要，不含測試輸出）：**

1. 所有已修改的程式碼檔案清單
2. 所有已新增/修改的說明文件清單
3. 每個 TASK 的完成狀態（✅ 已完成 / ❌ 未完成 + 原因）

**注入的 Skills：** `implement`（完整內容）、`tdd`（列名稱）；其餘依偵測到的技術棧由 Agent 自行從可用 skills 中挑選使用

---

### 4. `review`（程式碼審查 Agent）

**職責：** 扮演資深程式碼審查者，依 `code-review` skill 的流程，從 Standards 與 Spec 兩軸（各自透過平行 sub-agent）審查本次修改。

**工具權限：** `review`（Read, Glob, Grep, Bash, **Task**）—**不可修改任何檔案**
（`Task` 是必要的：`code-review` skill 需要平行呼叫 Standards / Spec 兩個 sub-agent）
**Timeout：** 600 秒

**審查依據：**

- **Fixed point**：本次修改尚未 commit，固定為 `HEAD`（`git diff HEAD` 取得完整異動）
- **Spec 來源**：優先讀取 `analyze_plan` 依 to-spec 產生、`docs/superpowers/plans/` 下最新的規格文件（`project_context.latest_plan_file()`）；找不到則以任務描述與 TASK 清單為 fallback
- **Standards 來源**：依 `project_context.py` 判斷本次任務涉及的專案，讀取其 `CLAUDE.md` / `AGENT.md`，以及其中提及或專案根目錄下的 `CODING_STANDARDS.md` / `CONTRIBUTING.md`（若有）；涉及多個專案時分別讀取

**額外操作指示：**

1. 確認 TASK 清單完整性，列出未完成的 TASK 編號
2. 依偵測到的專案讀取其說明檔中列出的測試指令並實際用 Bash 執行測試（找不到則探索 `package.json` / `pyproject.toml`）；測試失敗計入 Standards 軸的問題
3. 若該任務所屬專案的說明檔要求同步維護 `docs/` 商業邏輯說明文件，確認是否已依本次修改更新；說明檔未提及此類慣例時不需要求有文件變更

**輸出格式：**

```
## Standards
[code-review skill 產出的 Standards 軸報告]

## Spec
[code-review skill 產出的 Spec 軸報告]

各 TASK 狀態：
✅ TASK 1: [說明]
❌ TASK 2: [失敗原因]

Ready to merge? Yes / No

（若 No，必須附上：）
REVIEW_LEVEL: 重寫
（或）
REVIEW_LEVEL: 修補

（若 Yes 但仍有不影響功能的修改建議，附上：）
## 建議事項（不影響功能）
SUGGESTION 1: [建議內容與理由]
SUGGESTION 2: [建議內容與理由]
```

**嚴重程度分流（`review_node` 的核心邏輯，`nodes/review.py`）：**

`Ready to merge? No` 只保留給**嚴重影響功能**的問題（核心邏輯錯誤、功能無法正常運作、資料損毀或資安風險、架構根本偏差、TASK 大量未完成）——這類問題一律自動判定為需要重新規劃，不詢問人工：

| 等級     | 觸發條件                                                              |
| -------- | --------------------------------------------------------------------- |
| **重寫** | 核心邏輯錯誤、架構根本偏差、多個互相關聯的根本性問題、TASK 大量未完成 |
| **修補** | 小 bug、測試失敗、遺漏文件同步、個別 TASK 未完成、小幅修正            |

其餘不影響功能正確性的問題（風格、可讀性、效能微調等）一律回答 `Yes`，改列在 `SUGGESTION n:` 建議清單中，交由人工決定：`review_node` 會逐條印出建議、在終端機提示輸入要修改的編號（`1,3`／`all`／直接 Enter 表示不修改）；非互動式環境預設不修改任何建議。人工選中至少一條時才視為需要重新規劃（`review_level` 一律標記「修補」，並把選中的建議附加在 `review_result` 末尾的「人工確認：選定修改的建議事項」小節，供 `analyze_plan` 重新規劃時只針對這些點 grill）；未選中任何建議或無建議可選時直接視為通過。

**路由結論：** 以上兩種情況（嚴重問題 / 人工選中建議）都會把 `review_blocking` 設為 `True`，交由 `route_after_review` 讀取決定是否重新規劃；其餘情況 `review_blocking` 為 `False`，直接結束流程。

**審查報告儲存至：** `docs/nodes/review/YYYY-MM-DD-iterN.md`（`_save_review_report()`，含 task、date、review level、完整報告內容；僅在 `review_blocking=True` 時儲存）

---

## 節點間協作機制

### 1. 狀態字典傳遞

每個節點讀取前一個節點填入的欄位，再將自己的輸出寫入對應欄位，例如：

- `analyze_plan` → 填入 `analysis`、`plan`
- `human_confirm` → 填入 `status`（`"confirmed"` / `"needs_revision"` + `human_feedback` / `"aborted"`）
- `execute` → 填入 `execution_result`、`status`
- `review` → 填入 `review_result`、`review_level`、`review_blocking`、`status`

### 2. 動態專案偵測作為共同上下文

`project_context.py` 不寫死任何目標專案，`analyze_plan`、`execute`、`review` 三個節點都各自呼叫 `build_project_docs_hint()`，依當下工作區實際內容判斷涉及哪些專案。

### 3. 檔案系統作為共享記憶

| 產出物   | 路徑                                     | 讀寫者                                      |
| -------- | ---------------------------------------- | ------------------------------------------- |
| 計畫文件 | `docs/superpowers/plans/<filename>.md`（`<filename>` 為使用者自訂檔名，留空則用 branch name） | `analyze_plan` 寫，`execute`、`review` 讀   |
| 審查報告 | `docs/nodes/review/YYYY-MM-DD-iterN.md`  | `review` 寫，下次迭代的 `analyze_plan` 可讀 |
| 業務文件 | 各偵測到專案的 `docs/` 目錄              | `execute` 寫，`review` 驗證                 |

### 4. Git Diff 作為稽核媒介

`review` 節點執行 `git diff HEAD` 取得所有實際變更，而非僅依賴執行節點的自述，確保審查基於事實。

### 5. Skill 系統作為知識注入

`skill_loader.py` 從 `~/.claude/skills/` 讀取 Claude Code Skill 文件，以完整內容或僅列名稱的方式注入系統提示。白名單 `_FULL_CONTENT_SKILLS`（`grill-with-docs`、`grilling`、`domain-modeling`、`to-spec`、`implement`、`code-review`）會注入完整內容——這些 skill 設有 `disable-model-invocation`，Claude 不會自動觸發，必須完整注入才能正確遵循其流程（提問方式、文件存放規則、平行 sub-agent 呼叫方式等）；其餘只列名稱以節省 token，由 Agent 依偵測到的技術棧自行選用。

### 6. 反饋迴圈

```
Iteration 1:
  analyze_plan → human_confirm [y] → execute → review → "需要修補" (review_level="修補")
                                                                │
                                                                ▼
Iteration 2:
  analyze_plan（接收 review_result；針對 review 提出的問題逐點 grill，
                不重新走完整 grill-with-docs 流程；依 review_level
                決定是否 rollback 保留現有變更）
    → human_confirm [y]（再次等待確認）
    → execute（執行差異修補）
    → review → "通過"
    → END ✅
```

---

## Claude Runner：CLI 封裝層

`claude_runner.py` 是整個系統的技術核心，封裝了對 `claude -p` CLI 的所有呼叫。

### 工具權限預設集

| 名稱       | 工具                                | 用途                                                                       |
| ---------- | ----------------------------------- | -------------------------------------------------------------------------- |
| `readonly` | Read, Glob, Grep                    | 安全探索                                                                   |
| `plan`     | Read, Write, Glob, Grep             | 建立文件                                                                   |
| `full`     | Read, Write, Edit, Bash, Glob, Grep | 完整程式碼修改                                                             |
| `check`    | Read, Glob, Grep, Bash              | 驗證，不修改檔案                                                           |
| `review`   | Read, Glob, Grep, Bash, Task        | 審查；`Task` 供 code-review skill 平行呼叫 Standards / Spec 兩個 sub-agent |

### 執行流程

1. 組合指令：`claude -p --allowedTools {tools} --output-format stream-json --verbose --dangerously-skip-permissions`
2. 以 subprocess 啟動，即時串流 stdout JSON 事件
3. 解析 `assistant`、`tool_use`、`tool_result` 事件並即時印出（dimmed 格式）
4. 解析最終 `result` 事件取得文字輸出與 token 用量
5. 回傳 `ClaudeResult`（含文字、`session_id`、token 統計、快取統計）

### 互動式提問（grilling）支援

`ClaudeResult` 帶有 `session_id`；`_log_event()` 偵測到助理輸出以 `QUESTION_MARKER`（`"QUESTION:"`）開頭時，會用醒目格式即時印出提問內容。`call_claude()` 的 `resume` 參數可帶入先前呼叫回傳的 `session_id`，讓上層（目前僅 `analyze_plan._run_with_grilling()`）能以同一個 Claude session 延續多輪一問一答，不必每輪重新提供完整上下文。

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
    "fable":  "claude-fable-5",
}
```

每個 Agent 節點檔案最上方都有一個 `_MODEL` 常數，值為 `MODEL_IDS` 的其中一個 key，或 `None`（沿用 Claude CLI 本身的預設模型）。要調整某節點使用的模型，直接改該節點檔案的 `_MODEL` 即可。

---

## 使用技術彙整

### Python 層

| 技術              | 版本   | 用途                                        |
| ----------------- | ------ | ------------------------------------------- |
| **LangGraph**     | ≥0.2.0 | StateGraph 工作流程編排、條件路由、節點串接 |
| **python-dotenv** | ≥1.0.0 | 讀取 `.env` 環境變數                        |
| **Python**        | 3.11   | 執行環境                                    |

### Claude Code CLI 層

| 技術                                              | 說明                                                                           |
| ------------------------------------------------- | ------------------------------------------------------------------------------ |
| **Claude Code CLI** (`@anthropic-ai/claude-code`) | 以 `claude -p` 啟動 Agent，使用本地身份驗證（不需要 API Key）；容器內有獨立於 host 的登入狀態，見下方「Claude 設定掛載」 |
| **stream-json output**                            | 即時串流 JSON 事件，支援 `assistant`、`tool_use`、`tool_result`、`result` 類型 |
| **Built-in Tools**                                | Read、Write、Edit、Bash、Glob、Grep、Task（Claude Code 原生工具）              |
| **Skill System**                                  | `~/.claude/skills/` 中的 Markdown 文件，動態注入 Agent 系統提示                |

### 目標專案技術棧

系統本身不假設固定技術棧——透過 `project_context.py` 動態偵測工作區內各專案的 `CLAUDE.md` / `AGENT.md`，`execute` 與 `review` 節點再依偵測結果自行選用對應 skill（例如 `vue-best-practices`、`nuxt-vitest-msw`）。

### 容器化層：Docker outside of Docker（DooD）

AgentLoop 容器本身不跑 Docker daemon，而是讓容器內的 Docker CLI 透過掛載進來的 host `docker.sock` 直接操控**宿主**的 Docker engine——因此容器內執行的 `docker` / `docker compose` 指令，實際上是宿主 daemon 在執行，其建立的所有 bind mount 也以宿主上的路徑為準。這讓 Agent 能在容器內對任一目標專案執行 `docker compose up / exec` 等指令來啟動服務、跑測試，而不需要在 AgentLoop 容器內重新起一顆 daemon（DinD）。

| 技術                            | 說明                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Docker**                      | 以 `python:3.11-slim` 為基底，加裝 Node.js 20 執行 Claude Code CLI，並加裝 `docker-ce-cli` + `docker-compose-plugin`（僅 CLI，不含 daemon）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **Docker Compose 路徑掛載**     | AgentLoop 與目標專案一律以「與 host 相同的絕對路徑」掛載（`${HOST_WORKSPACE_ROOT}/AgentLoop:${HOST_WORKSPACE_ROOT}/AgentLoop`、`${HOST_WORKSPACE_ROOT}/${TARGET_PROJECT}:${HOST_WORKSPACE_ROOT}/${TARGET_PROJECT}`），而非重新映射到 `/workspace/...`。原因：宿主 daemon 幫目標專案建立 bind mount 時，用的是掛載路徑「字串本身」，該字串必須在宿主上真實存在，否則會掛到空目錄。目標專案資料夾名稱由 `.env` 的 `TARGET_PROJECT` 決定（目前範例值為 `cdn_frontend_vue`）；`project_context.py` 的動態偵測邏輯本身不寫死任何專案名稱。若要同時掛載多個目標專案，`.env` 目前只內建單一 `TARGET_PROJECT`，需自行擴充 `TARGET_PROJECT_2`、`TARGET_PROJECT_3`… 並在 `docker-compose.yml` 依樣新增對應的 volume 行（見 README） |
| **`/var/run/docker.sock` 掛載** | `- /var/run/docker.sock:/var/run/docker.sock`，讓容器內 Docker CLI 連上宿主 daemon（DooD 的核心）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **Claude 設定掛載** | 分兩塊，刻意分開：(1) 登入狀態（`.claude/` 其餘內容、`.claude.json`）掛在容器專屬的 `agent_home` named volume（`- agent_home:/home/agent`），**不**與 host 共用——原因是若直接掛載 host 的 `~/.claude`，host 與容器內的 `claude` subprocess 會共用同一份 OAuth 憑證檔，兩邊同時使用時 token refresh 互搶，會導致容器內 node 執行到一半認證失效、或剛啟動時讀到寫入中的檔案顯示未登入；因此改為另外設定認證——首選在 host 執行 `claude setup-token`，將產出的 token 寫入 `.env` 的 `CLAUDE_CODE_OAUTH_TOKEN`（或改設 `ANTHROPIC_API_KEY`）；容器內互動式 `claude login` 仍可用但非首選，因為 `docker exec -it` 的嵌套 TTY 貼授權碼常因 paste 截斷或過期顯示 `Invalid code`。登入狀態隨 volume 持久化，容器重建不會遺失。(2) skills 內容（純靜態、無寫入需求）維持唯讀掛載自 host：`${HOME}/.claude/skills:/home/agent/.claude/skills:ro` 與 `${HOME}/.agents:/home/agent/.agents:ro`（`~/.claude/skills` 底下多為指向 `~/.agents/skills` 的符號連結，需一併掛載才能解析）。`working_dir: ${HOST_WORKSPACE_ROOT}` |
| **非 root 使用者**              | `agent` 使用者執行 `claude --dangerously-skip-permissions`（Claude Code 安全要求，禁止 root 下執行），並設定 `NOPASSWD` sudo 僅限執行 `/usr/bin/docker`——因為宿主掛入的 `docker.sock` 擁有者/群組由宿主環境決定，非 root 使用者常無法單靠 group 權限連線，故一律透過 sudo 執行 docker 指令                                                                                                                                                                                                                                                                                                                                                                                                                                |

---

## CLI 入口：`main.py`

### 完整工作流程模式

```bash
python -m AgentLoop.main "幫我在後端新增一個 GET /tables/featured 端點"
```

### 單節點偵錯模式

```bash
python -m AgentLoop.main --node analyze_plan "任務描述"
python -m AgentLoop.main --node execute --state-file /tmp/state.json "任務描述"
python -m AgentLoop.main --node review "任務描述"
```

State file 可預載 `plan`、`execution_result` 等欄位，便於針對單一節點除錯。`human_confirm` 不在 `--node` 可選清單中，只能作為完整工作流程的一部分執行。

---

## 總結

| 面向         | 細節                                                                     |
| ------------ | ------------------------------------------------------------------------ |
| 架構模式     | LangGraph StateGraph + 3 個 Agent 節點 + 人工確認閘 + 審查驅動的反饋迴圈 |
| 節點數量     | 4（規劃、人工確認、執行、審查）                                          |
| 最大重試次數 | 3 次迭代後強制結束                                                       |
| 執行模型     | 序列執行 + 迭代精修（審查驅動，重新規劃時只針對 review 結果 grill）      |
| 語言         | Python 協調層 + 繁體中文提示                                             |
| 目標架構     | 動態偵測，不假設固定技術棧（目前範例：Vue + Ant Design Vue）             |
| 驅動方式     | Claude Code CLI（本地認證，非 API Key）                                  |
| 狀態傳遞     | 不可變 TypedDict 流經整個工作流程                                        |
| 產出物       | 計畫文件、執行摘要、審查報告、程式碼變更                                 |

</content>
