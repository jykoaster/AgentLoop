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
├── openspec_runner.py         # OpenSpec CLI 封裝層（唯一跟 `openspec` CLI 對話的地方；目前只有 archive）
├── skill_loader.py           # Skill 注入器
├── project_context.py         # 動態偵測工作區內各專案的 CLAUDE.md / AGENT.md
├── git_ops.py                 # 在目標專案 checkout／建立 AgentState["branch_name"]
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .claude/
│   └── skills/               # 專案內建 Skill（見下方「Skill 系統作為知識注入」）
├── nodes/
│   ├── analyze_plan.py     # 規劃 / 重新規劃 Agent 節點
│   ├── human_confirm.py    # 人工確認中斷點
│   ├── execute.py          # 執行 Agent 節點
│   ├── review.py           # 程式碼審查 Agent 節點
│   └── archive.py          # review 通過後的收尾節點（純 Python，呼叫 openspec archive）
└── docs/
    └── nodes/review/        # review 節點產出的審查報告（YYYY-MM-DD-iterN.md）
```

規格文件本身不再存在 AgentLoop 這個 repo 底下，而是寫進**目標專案**的
`<project_dir>/openspec/changes/<change_name>/`（`proposal.md` / `tasks.md` /
`specs/<domain>/spec.md`；非小改動時另有 `design.md`），遵照 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 的
change/spec-delta 規則；review 通過後由 `archive` 節點呼叫 `openspec archive` 併入該目標專案
持久的 `<project_dir>/openspec/specs/`。詳見下方「規劃 Agent」與「收尾節點」兩節。

---

## 核心資料結構：`AgentState`

所有節點之間以一個不可變的 `TypedDict` 傳遞狀態，完整定義如下：

```python
class AgentState(TypedDict):
    task: str              # 使用者輸入的任務描述
    analysis: str          # proposal.md 全文，供 human_confirm 顯示
    plan: list[str]        # tasks.md checkbox 清單，供 human_confirm 顯示（execute／review 自行讀檔，不注入）
    execution_result: str  # 執行節點的文字摘要（除錯／state-file；review 不注入，改讀 git diff 與 OpenSpec）
    review_result: str     # 審查節點的完整報告
    review_level: str      # "重寫" | "修補" | ""
    review_blocking: bool  # review_node 的最終路由結論：True → 重新規劃；False → 通過
    status: str            # "pending" | "needs_revision" | "error" | "confirmed" | "aborted"
    iteration: int         # 重試計數器（上限 3）
    human_feedback: str    # 使用者在 human_confirm 拒絕計畫時填寫的修改意見
    change_name: str       # OpenSpec change 名稱（由 branch_name 轉 kebab-case）；任務開始時問一次，全程沿用
    branch_name: str       # 使用者指定的 git 分支（必填）；規劃／執行／審查／archive 都切到此分支
    project_dir: str       # 本次任務對應的目標專案目錄（相對 workspace root）；由 analyze_plan
                           # 初始規劃時在呼叫 Claude 前決定，之後所有節點據此定位 openspec/changes/<change_name>/
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
       │                      ┌────────────────────┼───────────────────────┐
       │                      │                    │                       │
       │           review_blocking=False   review_blocking=True    review_blocking=True
       │                      │            + 未達上限               + 已達 iteration 上限
       │                      ▼                    │                       │
       │             ┌────────────────┐            ▼                       ▼
       │             │ archive_change │  increment_iteration              END ⚠️
       │             │ 併入目標專案持久 │            │
       │             │ openspec/specs/│            ▼
       │             └───────┬────────┘     回到 analyze_plan
       │                     │              （帶入 review_result
       │                     ▼               與 review_level，
       │                  END ✅             只針對 review 結果 grill）
       │                                     再次等待人工確認
       │
       ├─── 輸入 N + 填寫修改意見 ──────────→ analyze_plan
       │    (needs_revision + human_feedback)  （帶入 human_feedback
       │                                        重新規劃後再次確認）
       │
       └─── 輸入 N + 空白 (aborted) ────────→ END 🛑
```

`archive_change` 是純 Python 節點，不呼叫 Claude：終端機問一次是否要 archive（`_ask_should_archive()`，
答 `y` 才繼續），同意才呼叫 `openspec archive <change_name> --yes --json` 把這次的 spec delta 併入
目標專案持久的 `openspec/specs/`；使用者選擇不 archive、或 archive 本身失敗，都只印警告，不影響
工作流程結束狀態。

### 關鍵函式

| 函式                    | 所在檔案      | 說明                                                                                  |
| ----------------------- | ------------- | ------------------------------------------------------------------------------------- |
| `route_after_confirm()` | `workflow.py` | 條件路由：`confirmed` → execute；`needs_revision` → replan；`aborted` / `error` → END |
| `route_after_review()`  | `workflow.py` | 條件路由：只讀取 `review_node` 已判定好的 `review_blocking`（不再自行解析 review 文字）——`False`（通過）→ `archive_change`；`True` 且已達 iteration 上限 → END（放棄重試，不 archive）；其餘 → replan |
| `increment_iteration()` | `workflow.py` | 增加重試計數，重設 status 為 `pending`                                                |
| `archive_node()`        | `nodes/archive.py` | review 通過後先問一次是否要 archive（`_ask_should_archive()`），同意才呼叫 `openspec_runner.archive_change()`；純機械式動作，不佔用 Claude 呼叫，略過或失敗都只印警告 |
| `build_workflow()`      | `workflow.py` | 編譯 `StateGraph`，回傳可執行的 app                                                   |

常數 `MAX_ITERATIONS = 3`：超過後強制結束，避免無限迴圈。

---

## 動態專案偵測：`project_context.py`

系統不把目標專案的目錄結構寫死在 prompt 裡，但也不需要每次都讓 Agent 自己「猜」是哪個專案——
`analyze_plan`、`execute`、`review` 三個節點呼叫這段邏輯時，`project_dir` 都已經確定（workspace
只支援單一 `TARGET_PROJECT`，見上方「目標專案與 Domain」），所以三者一律呼叫
`build_project_doc_hint_for(project_dir)`：直接指名 `<project_dir>/CLAUDE.md`（或 AGENT.md /
AGENTS.md）要求 Read，不列出、也不需要判斷其他專案。這比舊版的 `build_project_docs_hint()`（掃描
整個 workspace root、列出所有偵測到的專案說明檔、交由 Agent 自行判斷）省下大量 token——在一個掛了
好幾個同系列 side project 的 workspace 裡，舊版可能列出五、六個完全無關的專案，還讓 Agent 有選錯
的風險。`list_project_docs()` / `build_project_docs_hint()` 仍保留在 `project_context.py`：只在
`project_dir` 意外為空（例如手動指定的 state 檔缺欄位）時，`build_project_doc_hint_for()` 內部
才會退回這個舊的整個 workspace 掃描邏輯作為 fallback；目標專案本身找不到任何說明檔時，也是退回用
Read/Glob/Grep 自行探索程式碼風格。

---

## 五個節點詳述（3 個 Claude Agent + 1 個人工確認閘 + 1 個純 Python 收尾節點）

### 1. `analyze_plan`（規劃 Agent）

**職責：** 扮演資深全端工程師，依觸發來源分成三種模式，輸出結構化的實作計畫文件。目標專案／分支／
domain／`openspec` 的 init／new change／validate 等機械式判斷全部由 Python 端在呼叫 Claude 之前
（或之後）處理，不再讓 Claude 自己用 Bash 判斷或執行——這樣既省下對應的 prompt 篇幅，也省下那些
本可用一次函式呼叫解決、卻要在 agentic session 裡多繞一輪 Bash 工具呼叫的 token。

**模式判斷（依 `AgentState` 欄位）：**

| 模式                    | 觸發條件                                     | 工具     | 模型 |
| ----------------------- | -------------------------------------------- | -------- | ---- |
| 初始規劃                | `review_result` 與 `human_feedback` 皆為空   | `plan`   | opus |
| 重新規劃（review 觸發） | `review_result` 非空                         | `revise` | opus |
| 依人工意見調整計畫      | `human_feedback` 非空且 `review_result` 為空 | `revise` | opus |

`rollback`／`openspec` init／new change／validate 皆已搬到 Python（見下），三種模式都不再需要
`Bash` 才能完成規劃，`claude_runner.TOOL_PRESETS` 因此新增／調整了兩個 preset：`plan`
（`Read,Write,Glob,Grep`，僅初始規劃——只新增規格文件，不改既有檔案，也不含 `Edit`）與新增的
`revise`（`Read,Write,Edit,Glob,Grep`，重新規劃／依人工意見調整共用——兩者都是 Edit 既有規格
文件）。`full`（含 `Bash`）留給 `execute` 節點用，不再給 `analyze_plan` 沿用——這也修正了一個
既有落差：依人工意見調整的 prompt 一直要求「用 Read 讀取、Edit/Write 更新」，但先前沿用的
`plan` preset 其實不含 `Edit`。

**任務開始時詢問 git 分支名稱與目標專案：**

初始規劃模式進入 `analyze_plan_node()` 時，若 `state["branch_name"]` 尚未設定，會在呼叫 Claude
之前先用 `_ask_branch_name()` 直接向終端機使用者提問（不透過 Claude、不是 grilling 機制的一部
分）。**不可為空**：空白會重問；非互動式環境或使用者中止則視為錯誤（`status: "error"`）。取得的
值全程保存在 `AgentState["branch_name"]`。OpenSpec `change_name` 由此分支名稱經
`_sanitize_change_name()` 轉成 kebab-case（含把 `/` 轉成 `-`，例如 `feature/add-login` →
`feature-add-login`），不另問、也不讓 Claude 改名。

`state["project_dir"]`（本次任務對應的目標專案目錄，相對 workspace root）同樣改成初始規劃時由
`_resolve_project_dir()` 在呼叫 Claude **之前**決定，不再讓 Claude 判斷、事後從回覆解析：workspace
只支援掛載單一目標專案，直接讀環境變數 `TARGET_PROJECT`，確認對應目錄存在即可，不掃描 workspace、
不需要使用者選擇。環境變數未設定，或對應目錄不存在，都視為錯誤（`status: "error"`）。之後所有節點
（`execute`、`review`、`human_confirm`、`archive`）都直接讀 `AgentState["project_dir"]` 定位
OpenSpec change 位置，不需要各自重新判斷；`archive_node` 單獨執行（沒有 state 可讀）時也是同樣
直接採用 `TARGET_PROJECT`，見 `nodes/archive.py` 的 `_resolve_location()`。

確認 `branch_name`／`project_dir` 後，規劃／執行／審查／archive 都會透過 `git_ops.ensure_on_branch()`
切到該分支（已存在則 `checkout`，不存在則 `checkout -b` 從目前 HEAD 建立）——這一步在呼叫 Claude
之前就完成，不再讓 Claude 自己 checkout。

**Domain 歸屬確認、`openspec init`／`new change`（皆已搬到 Python，呼叫 Claude 之前完成）：**
初始規劃在 `ensure_on_branch()` 之後、組 prompt 之前，依序執行：

1. `openspec_runner.ensure_initialized()`：`<目標專案>/openspec/` 不存在才執行一次性
   `openspec init --tools claude --force`，已存在則直接略過
2. `_ask_domain_selection()`：用 `_list_existing_domains()` 列出 `<目標專案>/openspec/specs/`
   底下既有的 domain（資料夾名稱）；沒有既有 domain 時不提問，直接視為新建 domain。有既有
   domain 時在終端機列出清單 + 一個「以上皆非，建立新 domain」選項，讓使用者輸入編號選擇本次
   規格 delta 歸屬哪個（可用逗號輸入多個編號，對應「同一任務涉及多個既有 domain」的情況）；
   非互動式環境預設視為新建 domain。選定的既有 domain 名稱清單會組進 system prompt 的
   `_DOMAIN_CONTEXT_EXISTING` 區塊（沿用名稱、不加 `## Purpose`）。回傳空清單（確定是純粹新建
   domain：沒有既有 domain，或使用者選了「建立新 domain」）時，額外呼叫 `_ask_domain_purpose()`
   讓使用者選填這個新 domain 的 Purpose 文字；有填就用 `_DOMAIN_CONTEXT_NEW_WITH_PURPOSE`（Claude
   直接採用這段文字寫入 `## Purpose`，不自己改寫），留白（含非互動式環境、使用者中止）則用
   `_DOMAIN_CONTEXT_NEW`（Claude 依任務語意自行命名 domain 並撰寫 `## Purpose`）。若使用者選擇同時
   涉及既有 domain 又可能需要新 domain（回傳清單非空），是否額外建立新 domain 完全交給 Claude 判斷，
   不會觸發這個 Purpose 提問——Python 只在「確定會建立新 domain」時才問
3. `openspec_runner.ensure_change_created()`：change 資料夾不存在才執行 `openspec new change
   <name>`，已存在則直接略過

這三步都不再透過 Claude 的 Bash 呼叫執行，Claude 收到的 system prompt 直接是已確定的結果
（「目標專案與 Domain」區塊），不需要再探索或提問。此機制只在初始規劃跑，沿用階段
（`_CHANGE_SETUP_EXISTING`）沿用同一個 change，不重新走這一步。

**「重寫」等級的 rollback（已搬到 Python，呼叫 Claude 之前完成）：** 重新規劃若 `review_level`
為「重寫」，在 `ensure_on_branch()` 之後、組 prompt 之前，呼叫 `git_ops.rollback_except_openspec()`：
在目標專案執行 `git stash push --include-untracked -- . ':!openspec'`（失敗則 `git checkout --
. ':!openspec'` + `git clean -fd --exclude=openspec/`）丟棄程式碼變更（含 execute 留下的
untracked 新檔），但保留 `openspec/`，失敗即視為錯誤（`status: "error"`）、不繼續呼叫 Claude。
「修補」等級不執行此步驟，保留現有變更。

**互動式釐清（grilling）機制：**

三種模式的 prompt 都要求 Claude 在需要人工決策時，該輪回應「只能」輸出固定格式的 `QUESTION: <問題>` + 數字選項，而不得自行臆測。這由 `_run_with_grilling()` 迴圈驅動：

1. `call_claude()` 執行後，偵測輸出是否以 `QUESTION:` 開頭
2. 若是，暫停等待使用者輸入（非 TTY 環境自動採用 Agent 自己建議的答案繼續，避免無限等待）
3. 帶著使用者回覆、以 `--resume <session_id>` 延續同一個 Claude session 繼續對話，避免每輪重新給上下文
4. 最多 15 輪（`_MAX_QUESTIONS`），超過則中止釐清、採用當前結果繼續

`_run_with_grilling()` 現在多接受一個可選的 `resume` 參數，讓呼叫端可以從一個既有 session
（而非全新對話）開始這個迴圈——`_run_with_validate()`（見下）就是靠這個參數，把 openspec
validate 的錯誤修正也接到同一套「有問題就等使用者、否則繼續」的迴圈裡。

**依模式而異的提問規則：**

- **初始規劃 / 依人工意見調整計畫**：完整 grilling 流程——依 grilling 逐一提問，過程中依 domain-modeling 即時更新 `CONTEXT.md` / `docs/adr/`。初始規劃的 grill 結果必須能寫出 Specine 強制三項（規範目的、輸出要求、範例及解釋）的具體內容（不是任務原句複述），其餘七項依適用納入；依人工意見調整時只在意見影響這些項時才重問，不重跑完整 Specine 清單
- **重新規劃（review 觸發）**：**只針對 review 結果 grill**——針對審查標記的每個問題點逐一提出質疑性問題（判斷是否成立、修正方向如何取捨），不要求重新走一遍完整的 grilling 釐清或 Specine 清單，也不強制 domain-modeling 文件同步；更新規格時仍須維持強制三項寫在對應 OpenSpec 欄位

**三種 Prompt 版本：**

| 版本                   | 用途                                                                                                                                                                               |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_SYSTEM_INITIAL`      | 全新任務規劃：Read/Glob/Grep 探索 → grilling 互動釐清（同步 domain-modeling；grill 結果須含 Specine 強制三項）→ 依「OpenSpec 產出規則」撰寫 proposal.md / specs delta / tasks.md（非小改動時另寫 design.md）於系統已建好的 change 資料夾（目標專案／domain／`openspec init`／`new change` 皆已由 Python 事先確認並附在 prompt 裡） |
| `_SYSTEM_REPLAN`       | 帶入 `<<REVIEW_CONTEXT>>`（`review_result`，截斷至最後 3000 字）與 `<<REVIEW_LEVEL>>`；依「重寫／修補」分流見上（rollback 已由 Python 事先完成），並用專屬的 `_REVIEW_QUESTION_PROTOCOL` 針對 review 結果逐點 grill；沿用既有 change，不重新 `openspec new change` |
| `_SYSTEM_HUMAN_REVISE` | 帶入 `<<HUMAN_FEEDBACK>>`（`human_confirm` 收到的使用者修改意見）：理解意見（不夠明確則提問）→ 視需要重讀程式碼 → 視需要更新 domain-modeling → 更新既有 change 的規格文件            |

**輸出格式與解析邏輯：**

規格正文只寫在 OpenSpec change 資料夾，聊天不再重複一份「## 分析」「## 計畫」或 TASK 清單，最終
回應一句話回報完成狀態即可——`PROJECT_DIR:`/`CHANGE_NAME:` 這兩行輸出契約已經取消，因為
`project_dir`／`change_name` 現在在呼叫 Claude 之前就由 Python 決定好了，不需要再從回覆解析。

- `state["analysis"]`、`state["plan"]` **只讀檔**：`analysis` 讀該 change 資料夾下 `proposal.md` 全文；`plan` 讀 `tasks.md` 的 checkbox 清單（`_TASK_CHECKBOX_RE`）。單一事實來源是 OpenSpec CLI 自己會 `validate` 的檔案；`proposal.md` 或 `tasks.md` 讀不到（或 tasks 沒有任何 checkbox）視為錯誤（`status: "error"`），不 fallback 去 regex 聊天文字
- 涉及新增或修改行為的 TASK，須額外排入對應的「撰寫／更新測試」TASK，讓 `execute` 有明確依據依 tdd skill 執行紅-綠循環；純文件、設定調整或不改變行為的重構可不需要
- 是否需要新增「更新文件」TASK，依該任務所屬專案的 `CLAUDE.md` / `AGENT.md` 判斷：說明檔要求同步維護 `docs/` 商業邏輯說明文件才排入，未提及此類慣例則不強制新增

**注入的 Skills（完整內容）：** 初始規劃／依人工意見調整用 `_SKILLS`（`grilling`、`domain-modeling`、`tdd`）；
重新規劃（review 觸發）改用 `_SKILLS_REPLAN`（`grilling`、`tdd`），**不含** `domain-modeling`——
`_SYSTEM_REPLAN` 本來就明講「不需重新進行完整的 grilling 釐清或文件同步」，注入它的完整內容（三個
skill 裡最大的一塊）純屬浪費 token。`tdd` 三種模式都注入完整內容（見下方「Skill 系統作為知識注入」
關於為什麼不能只列名稱）。規格格式由 `_OPENSPEC_ARTIFACT_RULES` 寫死。

**檔案骨架範本（`_OPENSPEC_TEMPLATES`）只注入初始規劃：** replan／依人工意見調整都是 Edit 既有
change 資料夾裡已存在的檔案，Claude 直接 Read 就看得到實際格式，不需要再看一次
proposal.md/design.md/specs delta/tasks.md 的空白骨架——這部分只留在 `_SYSTEM_INITIAL`，
`_OPENSPEC_ARTIFACT_RULES` 本身瘦身成只保留規則文字（Specine 對齊、自檢、各檔案的規則清單），
不含骨架範本。

**OpenSpec Change 建立與規格文件範本：** 規格文件不再是 AgentLoop 自訂的單一 Markdown 檔案，而是遵照 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 的 change 資料夾格式，寫在目標專案的 `<project_dir>/openspec/changes/<change_name>/` 底下：

- **建立階段**（僅初始規劃，皆由 Python 在呼叫 Claude 前完成，見上方說明）：`ensure_on_branch()`
  checkout 分支 → `ensure_initialized()` bootstrap `openspec/` → `_ask_domain_selection()` 確認
  domain 歸屬 → `ensure_change_created()` 建立 change 資料夾
- **沿用階段**（`_CHANGE_SETUP_EXISTING`，replan／human-revise 共用）：`project_dir`/`change_name`
  沿用 `AgentState` 已存的值，不重新 `init`/`new change`，直接 Edit/Write 同一個 change 資料夾；
  「重寫」等級的 replan 在 Claude 完成撰寫、`openspec validate` 通過後，由 `_reset_task_checkboxes()`
  把 `tasks.md` 所有 checkbox 重設回 `- [ ]`（純字串處理，不需要 Claude 再做一次）
- **產出規則**（`_OPENSPEC_ARTIFACT_RULES`，三種模式共用）：章節結構維持 OpenSpec，不另開 Specine 專章；`_SPECINE_ALIGNMENT` 把十項對齊要素對應進既有欄位。強制三項缺一不可（純重構且 `skip_specs: true` 時 Intent 仍須寫目的，輸出／範例可註明無外部可觀察行為）：規範目的 → `proposal.md` 的 `## Intent`（新建 domain 的 `## Purpose` 與其對齊）；輸出要求 → Requirement 的 SHALL/MUST 與主路徑 Scenario 的 THEN（資料類型、格式、約束）；範例及解釋 → 至少一個主路徑 Scenario 的「逐步邏輯」（從輸入到輸出）。其餘七項適用才寫：背景 → Intent／Approach；關鍵概念 → domain-modeling；輸入要求 → GIVEN/WHEN；邊界／錯誤處理 → 額外 Scenario；APIs／提示 → Approach 或 `design.md`
  - `proposal.md`：`## Intent`（規範目的，適用時補背景）/ `## Scope`（In scope / Out of scope）/ `## Approach`（適用時寫 APIs、建議演算法／資料結構）
  - `design.md`（採 OpenSpec 預設：小改動可略過、不要建立空檔；有架構取捨、新模組／接縫、或需要留下技術債時才寫）：`## Technical Approach` / `## Architecture Decisions` / `## Testing Strategy`（含「Seam（測試接縫）」「測試案例矩陣（Test Matrix）」固定小節，矩陣須涵蓋主路徑逐步範例）/ `## Technical Debt & Follow-up Notes`；一旦撰寫，沒有內容也要保留標題填「無」，不可留白或整段刪除
  - `specs/<domain>/spec.md`（delta，可能有多個 domain）：只用 `## ADDED Requirements` / `## MODIFIED Requirements` / `## REMOVED Requirements` 三種分節，`### Requirement:`（SHALL/MUST/SHOULD，一個 Requirement 只講一件事，含輸出要求）+ `#### Scenario:`（逐步邏輯 + GIVEN/WHEN/THEN，至少一個主路徑須含從輸入到輸出的逐步解釋，THEN 須含輸出格式／約束）；新建 domain 才加 `## Purpose`（與 Intent 對齊，或直接採用使用者透過 `_ask_domain_purpose()` 指定的文字，見上方「Domain 歸屬確認」）；純重構/文件/設定變更可在 `.openspec.yaml` 設 `skip_specs: true` 略過；REMOVED 移除某 domain 最後一個 Requirement 時需設 `retire_capabilities: true` 才會被 archive 一併刪除該 domain 的 spec。寫之前須先 Read/Grep 目標專案已合併的 `openspec/specs/<domain>/spec.md`（不是這次 change 的 delta），逐一比對既有 Requirement 的規範範圍：能合併或完全重複就用 MODIFIED 改寫，找不到才用 ADDED，避免同一件事拆成多個重疊的 Requirement；Requirement／Scenario 標題用抽象措辭涵蓋規則本身，不寫死具體數量或列舉值（例如「兩個權限皆為 true」），否則功能擴充時舊標題對不上新情況，被迫另開一個而非既有規則自然涵蓋；兩者都只寫規範（系統對外呈現的行為與約束），不寫實作細節（不限技術棧，泛指前端 DOM/CSS/元件庫或後端 DB 欄位型別/SQL/框架 API/內部函式類別變數名稱），實作方式留給 `design.md` 的 Technical Approach
  - `tasks.md`：`## N. <群組>` + `- [ ] N.M <任務>` checkbox、階層編號——這份檔案本身就是任務清單；`execute` 與 `review` 都自行 Read 完整 change 資料夾（不從 `state["plan"]` 注入扁平清單），`execute` 逐項勾選、`review` 核對完成度
  - Claude 完成撰寫、`_run_with_grilling()` 的問答迴圈結束後，`_run_with_validate()` 呼叫
    `openspec_runner.validate_change()` 執行 `openspec validate <change-name> --json --strict`：
    只有 `ERROR` 等級的 issue 會擋下（`WARNING` 不阻擋），有的話把訊息組進一則新 prompt、用
    `_run_with_grilling(..., resume=session_id)` 接續同一個 session 請 Claude 修正，最多重試 5 次
    （`_MAX_VALIDATE_RETRIES`）；這一步完全在 Python 端驅動，Claude 不需要（也不被要求）自己執行
    `openspec validate`

---

### 2. `human_confirm`（人工確認閘道）

**職責：** 在規劃完成後、執行開始前，暫停工作流程，讓使用者審閱計畫並決定是否繼續。

**行為：**

- 列印分析摘要、TASK 清單（含數量）、OpenSpec change 路徑與工作分支
- 偵測到非互動式 stdin（如管道重導向）時自動中止，避免無限等待
- 輸入 `y`（不區分大小寫、忽略空白；`yes` 亦可）→ 返回 `status: "confirmed"` → 工作流程繼續至 `execute`
- 輸入非 `y` 後，再輸入修改意見（非空白）→ 返回 `status: "needs_revision"` + `human_feedback` → 回到 `analyze_plan` 重新規劃
- 輸入非 `y` 後，直接按 Enter（空白）、EOFError、KeyboardInterrupt → 返回 `status: "aborted"` → 工作流程結束

**注意：** review 失敗觸發重新規劃時，下一輪 `analyze_plan` 完成後同樣需要再次人工確認。

---

### 3. `execute`（執行 Agent）

**職責：** 扮演資深全端工程師，依計畫依序執行所有 TASK，完成程式碼修改、文件同步、測試執行。系統不假設任何特定技術棧。

**工具權限：** `full`（Read, Write, Edit, Bash, Glob, Grep）
**Timeout：** 900 秒（15 分鐘）

**執行前準備（必須完成）：**

1. Python 先用 `git_ops.ensure_on_branch()` 把目標專案切到 `state["branch_name"]`（已存在則 checkout，不存在則建立）；失敗則 `status: "error"`，不呼叫 Claude
2. Read `openspec/changes/<change_name>/` 下的 proposal.md、specs/**/*.md、tasks.md（若有 design.md 一併讀取）。規格、驗收條件與任務清單以這些檔案為準，**不**把 `state["plan"]` 扁平清單貼進 prompt
3. 依 `project_context.build_project_doc_hint_for(project_dir)` 指名的目標專案，Read 讀取其 `CLAUDE.md` / `AGENT.md`，了解架構、指令（測試、lint、build 等）、目錄慣例、程式碼規範與技術棧；找不到說明檔則自行 Read/Glob/Grep 探索並比對現有風格
4. 依偵測到的技術棧，**自行**從可用的 skills 中挑選並使用適合的其他 skill（例如 Vue 專案適用 `vue-best-practices`、Nuxt + Vitest 專案適用 `nuxt-vitest-msw`）——不寫死任何特定技術棧的 skill 清單。這些完全不經過 `skill_loader.py`，靠 Claude Code 自己原生的 skill 探索機制（只認執行者 `$HOME/.claude/skills/`，見下方「Skill 系統作為知識注入」）；`tdd` 已固定完整注入（見下方「注入的 Skills」），不需要另外挑選
5. 若該專案 `docs/` 目錄存在，讀取其下所有現有文件，了解商業邏輯說明；`docs/` 目錄不存在時不需自行建立

**執行方式：** 依 change 資料夾內 `tasks.md` 的順序嚴格依序完成：

- **不** commit——是否提交由使用者事後決定
- **不**自行呼叫 `/code-review`——後續有獨立的 Review Agent 依專案規格審查本次修改
- tasks.md 中若有「撰寫／更新測試」的 TASK，**必須**依 `tdd` skill 的紅-綠循環執行：先寫會失敗的測試，再寫最小可行實作讓測試通過，最後重構；不可先完成其他 TASK 的實作、事後才回頭補測試
- 過程中定期執行型別檢查與單一測試檔案，全部 TASK 完成後執行完整測試

嚴格依序完成 `tasks.md` 中的每一項；先 Read 再 Write/Edit，避免覆蓋不相關程式碼；風格、命名、目錄結構、i18n／型別／auto-generated 檔案等規則，一律依該專案 `CLAUDE.md` / `AGENT.md` 的說明判斷，不硬編碼在 prompt 裡。每完成一個 TASK，立即用 Edit 把該任務對應的 OpenSpec change（`<project_dir>/openspec/changes/<change_name>/tasks.md`，路徑由 `AgentState["project_dir"]`/`["change_name"]` 組成）裡對應的 checkbox 從 `- [ ]` 改成 `- [x]`，讓這份檔案即時反映實際完成進度，供 `review` 節點核對。

**文件同步要求：** 是否需要同步更新文件，依該任務所屬專案的 `CLAUDE.md` / `AGENT.md` 判斷——說明檔要求同步維護 `docs/` 商業邏輯說明文件才需處理（依 `tasks.md` 中對應的文件更新 TASK 執行，或在說明檔明確要求但 `tasks.md` 未包含時主動補上）；說明檔未提及此類慣例時不需要主動撰寫或更新文件。

**強制測試與自動修復：** 依該專案 `CLAUDE.md` / `AGENT.md` 中列出的測試指令執行測試；若說明檔未列出，探索 `package.json` / `pyproject.toml` 等設定檔判斷正確指令。測試失敗時分析錯誤並修復、重跑，最多重試 3 次；3 次後不論結果如何都繼續輸出最終摘要。

**最終輸出格式（文字摘要，不含測試輸出）：**

1. 所有已修改的程式碼檔案清單
2. 所有已新增/修改的說明文件清單
3. 每個 TASK 的完成狀態（✅ 已完成 / ❌ 未完成 + 原因）

**注入的 Skills：** `tdd`（完整內容，見下方「Skill 系統作為知識注入」關於為什麼不能只列名稱）；其餘依偵測到的技術棧由 Agent 自行從可用 skills 中挑選使用（依賴 Claude Code 自己的原生 skill 探索，不經過 `skill_loader.py`）。不 commit、不自行 `/code-review`，流程寫在 `_SYSTEM`。

---

### 4. `review`（程式碼審查 Agent）

**職責：** 扮演資深程式碼審查者，依 `code-review` skill 的流程，從 Standards 與 Spec 兩軸（各自透過平行 sub-agent）審查本次修改。

**工具權限：** `review`（Read, Glob, Grep, Bash, **Task**）—**不可修改任何檔案**
（`Task` 是必要的：`code-review` skill 需要平行呼叫 Standards / Spec 兩個 sub-agent）
**Timeout：** 600 秒

**審查依據：**

異動與規格都以檔案為準，prompt **不**注入 `state["plan"]` 扁平清單，也 **不**注入 `execution_result`。fixed point（固定為 `HEAD`）與 spec 來源（OpenSpec change 資料夾）由本節點參數提供給 `code-review` skill，不經由 skill 自己詢問使用者或找 issue tracker——這兩步在 `AgentLoop/.claude/skills/code-review/SKILL.md` 這份專案內建副本裡已經直接拿掉（見下方「Skill 系統作為知識注入」的說明）。

- **Fixed point**：本次修改尚未 commit，固定為 `HEAD`（`git diff HEAD` 取得完整異動，不用三點 diff）
- **Spec 來源**：`<project_dir>/openspec/changes/<change_name>/`（`AgentState["project_dir"]`/`["change_name"]` 組成的路徑）——Read 讀取其下 proposal.md / tasks.md / specs/**/*.md（若有 design.md 一併讀取；小改動可能沒有此檔，不視為缺漏），也可用 `openspec show <change_name> --json` 快速確認結構；若該 change 已被前一輪迭代 archive，改讀 `<project_dir>/openspec/specs/` 下對應 domain 的 spec.md
- **Standards 來源**：依 `project_context.build_project_doc_hint_for(project_dir)` 指名的目標專案，讀取其 `CLAUDE.md` / `AGENT.md`，以及其中提及或專案根目錄下的 `CODING_STANDARDS.md` / `CONTRIBUTING.md`（若有）
- 其餘仍依 skill：Fowler smell baseline、平行 sub-agent、以 `## Standards` / `## Spec` 並陳報告

**額外操作指示：**

1. 確認 TASK 清單完整性：Read `tasks.md`，依其 checkbox 狀態（`- [x]` 已完成／`- [ ]` 未完成）逐項核對，列出未完成的 TASK 編號
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

### 5. `archive_change`（收尾節點，`nodes/archive.py`）

**職責：** review 判定通過（`review_blocking=False`）後的機械式收尾動作——把這次的 OpenSpec change 併入目標專案持久的 `openspec/specs/`。這是「該不該 archive」的判斷（review 通過就 archive），不需要 Claude 的判斷力，因此**不呼叫 `call_claude()`**，純 Python 直接跑 `openspec` CLI，不佔用一次 Claude 呼叫、不耗費 token。

**觸發時機：** 只在 `route_after_review()` 判定 `review_blocking=False` 時進入；`status=="error"` 或 `review_blocking=True` 且已達 iteration 上限（放棄重試）時直接 END，不會進入這個節點——沒有通過審查的東西不併入持久 specs/。

**人工卡控：** 定位到 change 位置、（有需要時）checkout 完分支後，實際呼叫 `openspec archive` 前，`_ask_should_archive()` 在終端機問一次「是否要將此 change 併入 `<project_dir>/openspec/specs/`？[y/N]」——單層問法，答 `y` 才 archive，其餘（`N`、直接 Enter、非互動式環境、Ctrl-C/EOF）一律視為否、略過 archive 並印出手動指令，跟其他 archive 略過的情況一樣不讓整個工作流程失敗。CJK 提示文字改用 `print(..., end="")` 印出、`input()` 不帶 prompt 參數，避免重蹈 `human_confirm` 曾修過的「CJK readline 提示吃字元」問題（見 `f59edb4`）。

**執行內容：** 透過 `openspec_runner.archive_change(project_dir_abs, change_name)`（`openspec_runner.py`，跟 `claude_runner.py` 是「唯一跟 claude CLI 對話的地方」同樣的角色，這裡是唯一跟 `openspec` CLI 對話的地方）執行 `openspec archive <change_name> --yes --json`，把 change 的 spec delta 合併進 `openspec/specs/`、change 資料夾搬到 `openspec/changes/archive/YYYY-MM-DD-<name>/`。

**單獨執行：** `python -m AgentLoop.main --node archive <change_name>`。`change_name` 取 `AgentState["change_name"]`，沒有則用 CLI 的 `task` 參數。`project_dir` 已在 state 裡就直接用；否則直接採用環境變數 `TARGET_PROJECT`（workspace 只支援單一目標專案），再依 `change_name` 的原值／kebab-case 兩種形式比對哪個資料夾實際存在。`branch_name` 仍可選，有填才 checkout。

**失敗處理：** 容錯解析 stdout 的 JSON 診斷（OpenSpec agent-contract 的 `status: StoreDiagnostic[]` 慣例），失敗（`openspec` 指令不存在、validate 沒過、change 不存在等）只印警告訊息並附上手動補跑指令，**不**讓整個 workflow 失敗——程式碼已經審查通過，archive 只是收尾，失敗頂多之後手動執行 `openspec archive <name> --yes`。

**回傳：** 不更動 `AgentState` 任何欄位（`{}`），純粹是收尾動作。

---

## 節點間協作機制

### 1. 狀態字典傳遞

每個節點讀取前一個節點填入的欄位，再將自己的輸出寫入對應欄位，例如：

- `analyze_plan` → 填入 `analysis`、`plan`、`change_name`、`branch_name`、`project_dir`
- `human_confirm` → 填入 `status`（`"confirmed"` / `"needs_revision"` + `human_feedback` / `"aborted"`）
- `execute` → 填入 `execution_result`、`status`
- `review` → 填入 `review_result`、`review_level`、`review_blocking`、`status`
- `archive_change` → 不填入任何欄位（純收尾動作）

### 2. 動態專案偵測作為共同上下文

`project_context.py` 不寫死任何目標專案，但 `analyze_plan`、`execute`、`review` 三個節點呼叫時
`project_dir` 都已確定，因此都呼叫 `build_project_doc_hint_for(project_dir)` 直接指名要 Read 哪份
說明檔，而不是呼叫會掃描整個 workspace、列出所有專案交由 Agent 自行判斷的 `build_project_docs_hint()`
（後者只在 `project_dir` 意外為空時當作 fallback）。

### 3. 檔案系統作為共享記憶

| 產出物   | 路徑                                     | 讀寫者                                      |
| -------- | ---------------------------------------- | ------------------------------------------- |
| OpenSpec Change | `<project_dir>/openspec/changes/<change_name>/`（`proposal.md`/`tasks.md`/`specs/**/*.md`，非小改動時另有 `design.md`；`<project_dir>`/`<change_name>` 為 `AgentState` 對應欄位） | `analyze_plan` 寫；`human_confirm` 讀 proposal.md + tasks.md 供顯示；`execute` 讀完整 change 後實作並勾選 tasks.md；`review`、`archive_change` 讀 |
| 持久規格 | `<project_dir>/openspec/specs/<domain>/spec.md` | `archive_change` 呼叫 `openspec archive` 合併寫入，跨任務累積 |
| 審查報告 | `docs/nodes/review/YYYY-MM-DD-iterN.md`  | `review` 寫，下次迭代的 `analyze_plan` 可讀 |
| 業務文件 | 各偵測到專案的 `docs/` 目錄              | `execute` 寫，`review` 驗證                 |

### 4. Git Diff 作為稽核媒介

`review` 節點執行 `git diff HEAD` 取得所有實際變更，而非僅依賴執行節點的自述，確保審查基於事實。

### 5. Skill 系統作為知識注入

`skill_loader.py` 讀取 Claude Code Skill 文件，以完整內容或僅列名稱的方式注入系統提示。查找順序為專案內建的 `AgentLoop/.claude/skills/<name>/` 優先，找不到才 fallback 到使用者本機的 `~/.claude/skills/<name>/`。目前 `_FULL_CONTENT_SKILLS` 白名單完整注入的是 `grilling`、`domain-modeling`、`code-review`、`tdd`。

**為什麼 `tdd` 也一定要完整注入，不能只列名稱：** 實測過 `claude -p`（`claude_runner.py` 唯一呼叫 `claude` CLI 的地方）發現，Claude Code **原生**的 skill 探索機制（在系統提示的 `available skills` 清單、`Skill` 工具背後）只認執行者的 `$HOME/.claude/skills/`，跟 `claude_runner.py:165` 呼叫 subprocess 時設的 `cwd=REPO_ROOT` 完全無關——不管 cwd 指到哪裡，找到的永遠是同一份 `$HOME/.claude/skills/` 清單（曾用一個完全空的 cwd 目錄重複驗證過）。這代表 `AgentLoop/.claude/skills/` 底下隨版控帶著走的內建副本，原生機制**永遠不會發現**；只列名稱的 skill 能不能被 Claude 用到，完全取決於執行者自己的 `~/.claude/skills/` 剛好有沒有同名 skill——換一台機器、換一個沒有這些 skill 的使用者，就會失效，違反本檔案開頭「讓專案自帶所需 skill、不依賴使用者本機設定」的設計目標。白名單機制（Python 直接讀檔、逐字塞進 prompt）不經過原生探索，因此不受這個限制，是唯一能保證跨機器一致運作的方式。

規格格式由 `analyze_plan` 的 `_OPENSPEC_ARTIFACT_RULES` 寫死，執行流程寫在 `execute` 的 `_SYSTEM`。fallback 路徑（`~/.claude/skills/<name>/`）仍保留給其餘依技術棧動態選用、專案未內建的 skill（例如 `vue-best-practices`、`nuxt-vitest-msw`）——這些完全交給 Claude Code 自己原生的 skill 探索機制處理，不經過 `skill_loader.py`，所以確實受「執行者本機有沒有這個 skill」影響；這是刻意的設計取捨，因為 AgentLoop 不可能預先知道每個目標專案會用到哪些技術棧專屬的 skill。

**`AgentLoop/.claude/skills/code-review/SKILL.md` 是刻意跟個人版本分岔的專案內建副本，不是單純 vendor 進來的原文複製。** 原版 skill 的「Pin the fixed point」「Identify the spec source」兩步（問使用者要比對哪個 fixed point、去 issue tracker／`docs/`／`.scratch/` 找規格）在 `review` 這裡完全不會被執行到——`review_node()` 把這兩個參數釘死成固定值（fixed point 永遠是 `HEAD`、spec 來源永遠是 OpenSpec change 資料夾，見 `_SYSTEM` 的「依 code-review skill 執行時的具體參數」），原本得靠 `_SYSTEM` 開頭額外寫一段話覆蓋這兩步。這份專案內建副本直接把這兩步從 skill 文字裡拿掉（`## Process` 從「Identify the standards sources」開始算第 1 步），改成一句話聲明「fixed point 與 spec 來源由呼叫端提供，不要詢問使用者或自找」，讓 `_SYSTEM` 那段覆蓋文字也跟著簡化——省下約 1035 字元、且不再讓 Claude 同時看到「skill 說要問使用者」跟「`_SYSTEM` 說不要問」兩份互相矛盾的指示。之後若要同步升級這個 skill（例如 smell baseline 或 sub-agent brief 有更新），要手動比對 `~/.claude/skills/code-review/SKILL.md` 合併，不會自動同步。

### 6. 反饋迴圈

```
Iteration 1:
  analyze_plan → human_confirm [y] → execute → review → "需要修補" (review_level="修補")
                                                                │
                                                                ▼
Iteration 2:
  analyze_plan（接收 review_result；針對 review 提出的問題逐點 grill，
                不重新走完整 grilling 流程；依 review_level
                決定是否 rollback 保留現有變更）
    → human_confirm [y]（再次等待確認）
    → execute（執行差異修補）
    → review → "通過"
    → archive_change（併入目標專案持久 openspec/specs/）
    → END ✅
```

---

## Claude Runner：CLI 封裝層

`claude_runner.py` 是整個系統的技術核心，封裝了對 `claude -p` CLI 的所有呼叫。

### 工具權限預設集

| 名稱       | 工具                                | 用途                                                                       |
| ---------- | ----------------------------------- | -------------------------------------------------------------------------- |
| `readonly` | Read, Glob, Grep                    | 安全探索                                                                   |
| `plan`     | Read, Write, Glob, Grep             | 建立文件（`analyze_plan` 初始規劃，只新增檔案）                           |
| `revise`   | Read, Write, Edit, Glob, Grep       | 編輯既有文件（`analyze_plan` 重新規劃／依人工意見調整，不需要 `Bash`）     |
| `full`     | Read, Write, Edit, Bash, Glob, Grep | 完整程式碼修改（`execute`）                                                |
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

stdin 已關閉（非 TTY / pipe EOF）時自動中止，避免無限等待。

**重試時接續原本的 session，不重開新的：** 中斷前那次呼叫若已經透過串流事件拿到 `session_id`（代表 Claude session 已經建立，中途才因限流被打斷），按 Enter 繼續時會改用 `--resume <session_id>` 接上同一個 session，並只送出一段簡短的接續指示（`_RESUME_AFTER_LIMIT_PROMPT`：先確認目前檔案與 tasks.md 實際進度、不要重做已完成的部分、也不要假設中斷前最後一個動作一定完整），而不是重新送出原始的完整 prompt。這避免了「中斷前已經寫入的部分變更/已打勾的 checkbox，被一個完全沒有記憶的新 session 忽略或重做」的問題。只有在中斷發生得太早、連 `session_id` 都還沒拿到時，才會退回重送原始 prompt、開一個全新 session。

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
| **Skill System**                                  | `AgentLoop/.claude/skills/`（專案內建，優先）或 `~/.claude/skills/`（fallback）中的 Markdown 文件，動態注入 Agent 系統提示 |
| **OpenSpec CLI** (`@fission-ai/openspec`)         | 規格文件遵照的 change/spec-delta 規則來源；`openspec_runner.py` 是唯一跟這個 CLI 對話的模組，`analyze_plan` 用它 `init`/`new change`/`validate`，`archive_change` 節點用它 `archive`——皆由 Python 直接呼叫，不透過 Claude 的 Bash 工具。同樣透過容器內的 Node.js 20 安裝 |

### 目標專案技術棧

系統本身不假設固定技術棧——透過 `project_context.py` 動態偵測工作區內各專案的 `CLAUDE.md` / `AGENT.md`，`execute` 與 `review` 節點再依偵測結果自行選用對應 skill（例如 `vue-best-practices`、`nuxt-vitest-msw`）。

### 容器化層：Docker outside of Docker（DooD）

AgentLoop 容器本身不跑 Docker daemon，而是讓容器內的 Docker CLI 透過掛載進來的 host `docker.sock` 直接操控**宿主**的 Docker engine——因此容器內執行的 `docker` / `docker compose` 指令，實際上是宿主 daemon 在執行，其建立的所有 bind mount 也以宿主上的路徑為準。這讓 Agent 能在容器內對任一目標專案執行 `docker compose up / exec` 等指令來啟動服務、跑測試，而不需要在 AgentLoop 容器內重新起一顆 daemon（DinD）。

| 技術                            | 說明                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Docker**                      | 以 `python:3.11-slim` 為基底，加裝 Node.js 20 執行 Claude Code CLI，並加裝 `docker-ce-cli` + `docker-compose-plugin`（僅 CLI，不含 daemon）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **Docker Compose 路徑掛載**     | AgentLoop 與目標專案一律以「與 host 相同的絕對路徑」掛載（`${HOST_WORKSPACE_ROOT}/AgentLoop:${HOST_WORKSPACE_ROOT}/AgentLoop`、`${HOST_WORKSPACE_ROOT}/${TARGET_PROJECT}:${HOST_WORKSPACE_ROOT}/${TARGET_PROJECT}`），而非重新映射到 `/workspace/...`。原因：宿主 daemon 幫目標專案建立 bind mount 時，用的是掛載路徑「字串本身」，該字串必須在宿主上真實存在，否則會掛到空目錄。目標專案資料夾名稱由 `.env` 的 `TARGET_PROJECT` 決定（目前範例值為 `cdn_frontend_vue`）；`project_context.py` 的動態偵測邏輯本身不寫死任何專案名稱。只支援單一目標專案，不提供多專案掛載的擴充方式 |
| **`/var/run/docker.sock` 掛載** | `- /var/run/docker.sock:/var/run/docker.sock`，讓容器內 Docker CLI 連上宿主 daemon（DooD 的核心）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **Claude 設定掛載** | 分兩塊，刻意分開：(1) 登入狀態（`.claude/` 其餘內容、`.claude.json`）掛在容器專屬的 `agent_home` named volume（`- agent_home:/home/agent`），**不**與 host 共用——原因是若直接掛載 host 的 `~/.claude`，host 與容器內的 `claude` subprocess 會共用同一份 OAuth 憑證檔，兩邊同時使用時 token refresh 互搶，會導致容器內 node 執行到一半認證失效、或剛啟動時讀到寫入中的檔案顯示未登入；因此改為另外設定認證——首選在 host 執行 `claude setup-token`，將產出的 token 寫入 `.env` 的 `CLAUDE_CODE_OAUTH_TOKEN`（或改設 `ANTHROPIC_API_KEY`）；容器內互動式 `claude login` 仍可用但非首選，因為 `docker exec -it` 的嵌套 TTY 貼授權碼常因 paste 截斷或過期顯示 `Invalid code`。登入狀態隨 volume 持久化，容器重建不會遺失。(2) skills 內容：本專案用到的 skill 已直接複製進 `AgentLoop/.claude/skills/` 隨專案版控、不再依賴掛載即可運作；host 的 `${HOME}/.claude/skills:/home/agent/.claude/skills:ro` 與 `${HOME}/.agents:/home/agent/.agents:ro`（純靜態、無寫入需求）仍保留唯讀掛載，作為 `skill_loader.py` 的 fallback 來源，供 Agent 依偵測到的技術棧動態選用專案未內建的其他 skill（`~/.claude/skills` 底下多為指向 `~/.agents/skills` 的符號連結，需一併掛載才能解析）。`working_dir: ${HOST_WORKSPACE_ROOT}` |
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
python -m AgentLoop.main --node archive 54-feat-ai-ad-content-extend-to-1024-chars
```

State file 可預載 `plan`、`execution_result` 等欄位，便於針對單一節點除錯。`archive` 單獨執行時參數即 change 名稱，會掃描工作區定位 `openspec/changes/<name>/`，不需要 `--state-file`。`human_confirm` 不在 `--node` 可選清單中，只能作為完整工作流程的一部分執行。

---

## 總結

| 面向         | 細節                                                                     |
| ------------ | ------------------------------------------------------------------------ |
| 架構模式     | LangGraph StateGraph + 3 個 Claude Agent 節點 + 人工確認閘 + 審查驅動的反饋迴圈 + 純 Python 收尾節點 |
| 節點數量     | 5（規劃、人工確認、執行、審查、收尾 archive）                            |
| 最大重試次數 | 3 次迭代後強制結束                                                       |
| 執行模型     | 序列執行 + 迭代精修（審查驅動，重新規劃時只針對 review 結果 grill）      |
| 語言         | Python 協調層 + 繁體中文提示                                             |
| 目標架構     | 動態偵測，不假設固定技術棧（目前範例：Vue + Ant Design Vue）             |
| 驅動方式     | Claude Code CLI（本地認證，非 API Key）+ OpenSpec CLI（規格文件格式與 archive） |
| 狀態傳遞     | 不可變 TypedDict 流經整個工作流程                                        |
| 產出物       | 目標專案下的 OpenSpec change（規格文件）、執行摘要、審查報告、程式碼變更、review 通過後合併進目標專案持久的 openspec/specs/ |

</content>
