# Agents 系統架構文件

## 概覽

這是一套以 **LangGraph** 為骨架的多 Agent 工作流程系統，透過 Python 進行協調，以 **Claude Code CLI**（`claude -p`）驅動各個 Agent。系統本身不假設固定的目標技術棧——透過 `project_context.py` 動態偵測工作區內各專案的 `CLAUDE.md` / `AGENT.md`，再由各節點依偵測結果自行判斷架構、慣例與適用的 Skill。目標是對任一 monorepo / 專案執行端對端的自動化開發任務：規劃、人工確認、實作、程式碼審查，以及失敗時的自動重試與修補。

---

## 目錄結構

```
AgentLoop/
├── main.py               # CLI 入口（固定用 `python -m AgentLoop.main` 呼叫，維持在頂層）
├── search.py             # 獨立搜尋工具（`python -m AgentLoop.search "query"`，不屬於 workflow）
├── core/                    # 系統的核心骨架：狀態契約與 LangGraph 圖組裝
│   ├── state.py               # AgentState 型別定義
│   ├── session.py             # 中斷 session 插槽的唯一讀寫處（見下方「跨程序接回：session 插槽」）
│   ├── stages.py               # 各工作階段狀態追蹤（見下方「網頁控制台」的「階段狀態」）
│   └── workflow.py            # LangGraph 工作流程定義（`from ..nodes import ...` 組圖）
├── lib/                     # 節點共用的工具層（見下方各節點對這些模組的說明）
│   ├── claude_runner.py       # Claude Code CLI 封裝層
│   ├── openspec_runner.py     # OpenSpec CLI 封裝層（唯一跟 `openspec` CLI 對話的地方；目前只有 archive）
│   ├── skill_loader.py        # Skill 注入器
│   ├── project_context.py     # 動態偵測工作區內各專案的 CLAUDE.md / AGENT.md；PACKAGE_ROOT／REPO_ROOT 的唯一定義處
│   ├── git_ops.py             # 在目標專案 checkout／建立 AgentState["branch_name"]；初始規劃時另外
│   │                          # 列出本地分支、判斷工作分支是否存在、從使用者選的起點分支只快轉同步後建立
│   └── interaction.py         # 互動埠：CLI／網頁兩種提問實作的唯一切換點（見下方「網頁控制台」）
├── web/                     # 網頁控制台（見下方「網頁控制台」整節）
│   ├── app.py                  # FastAPI app（前綴 `/api`），同時以 StaticFiles 提供前端
│   ├── runner.py               # 單一作用中執行：子行程、日誌、提問/回覆檔、中止、session 回寫
│   ├── repo_view.py            # 唯讀瀏覽 .agentloop/changes、openspec/changes(/archive)、openspec/specs
│   ├── search_api.py           # 重用 search.py 的索引／檢索／回答函式
│   ├── settings.py             # `.web/settings.json` 讀寫、合併 .env、secret 遮罩、資料夾邊界檢查
│   └── frontend/                # Vue 3 + TypeScript + Vite SPA（見下方「前端」）
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .claude/
│   └── skills/               # 專案內建 Skill（見下方「Skill 系統作為知識注入」）
├── .web/                    # 網頁控制台執行期狀態（settings.json、run/ 執行目錄），容器內產生，gitignored
├── pytest.ini               # 註冊 `eval` marker，並預設排除（`addopts = -m "not eval"`）
├── tests/                   # 單元測試（不需要 Claude CLI）
│   └── evals/                 # prompt eval：真的呼叫 Claude CLI，標記 `eval`、預設不執行
├── nodes/
│   ├── analyze_plan.py     # 規劃 / 重新規劃 Agent 節點
│   ├── human_confirm.py    # 人工確認中斷點
│   ├── execute.py          # 執行 Agent 節點
│   ├── review.py           # 程式碼審查 Agent 節點
│   └── archive.py          # review 通過後的收尾節點（純 Python，呼叫 openspec archive）
└── docs/
    └── nodes/review/        # review 節點產出的審查報告（YYYY-MM-DD-iterN.md）
```

頂層只留 `main.py`（固定的 CLI 進入點）；其餘依角色分三層：`core/`（狀態契約 + 圖組裝，全系統的骨架）、
`lib/`（節點共用的工具層，包裝外部 CLI／偵測專案／注入 skill）、`nodes/`（實際的 Agent 行為）。`nodes/*.py`
一律用 `from ..core import AgentState`、`from ..lib import ...` 讀取（`core/__init__.py`／`lib/__init__.py`
各自統一 re-export），不直接深入到子模組；`core/workflow.py` 反過來用 `from ..nodes import ...` 組圖，
是唯一「上層 import 下層」的方向。`lib/` 底下五個模組互相依賴 `PACKAGE_ROOT`／`REPO_ROOT`
（`project_context.py` 是唯一定義處，`claude_runner.py`／`git_ops.py`／`skill_loader.py` 都從這裡
import，不再各自用 `__file__` 反推路徑）。

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
    task: str              # 使用者輸入的任務描述（analyze_plan／review 注入；execute 不讀、不注入）；
                           # 重跑已規劃任務輸入調整內容時，analyze_plan 會在原文後附加「調整 N：<內容>」並寫回
    analysis: str          # proposal.md 全文，供 human_confirm 顯示
    plan: list[str]        # tasks.md checkbox 清單，供 human_confirm 顯示（execute／review 自行讀檔，不注入）
    execution_result: str  # 執行節點的文字摘要（除錯／state-file；review 不注入，改讀 git diff 與 OpenSpec）
    review_result: str     # 審查節點的完整報告
    review_level: str      # "重寫" | "修補" | ""
    review_blocking: bool  # review_node 的最終路由結論：True → 重新規劃；False → 通過
    status: str            # "pending" | "needs_revision" | "error" | "confirmed" | "aborted"
    iteration: int         # 重試計數器（上限 3）
    human_feedback: str    # 人工確認退回意見，或重跑 analyze_plan 取得的調整內容（兩者走同一條
                           # 「依人工意見調整」路徑；見下方「調整」模式）
    change_name: str       # OpenSpec change 名稱（由 branch_name 轉 kebab-case）；任務開始時問一次，全程沿用
    branch_name: str       # 使用者指定的 git 分支（必填）；規劃／執行／審查／archive 都切到此分支
    domains: list[str]     # 本次 change 歸屬的 OpenSpec domain；初始規劃問一次後寫入 state.json，同一 change 再規劃時沿用
    skip_specs: bool | None  # 本次是否略過 specs delta（對應 .openspec.yaml 的 skip_specs）；None＝尚未決定。
                           # 初始規劃問一次後寫入 state.json，同一 change 再規劃時沿用、不再提問
    session_node: str      # 中斷中的 Claude session 屬於哪個 node（""＝沒有）；每個 change 同時
                           # 只會有一個，analyze_plan／execute／review 共用這一個插槽
    session_id: str        # 該 session 的 id，撞到用量上限後可 --resume 接回；只透過
                           # core/session.py 的 take_session()／store_session() 讀寫
    project_dir: str       # 本次任務對應的目標專案目錄（相對 workspace root）；由 analyze_plan
                           # 初始規劃時在呼叫 Claude 前決定，之後所有節點據此定位 openspec/changes/<change_name>/
    stages: dict[str, str]        # 各工作階段狀態："pending"|"running"|"done"|"error"；見下方「網頁控制台」的「階段狀態」
    stage_notes: dict[str, str]   # 階段附註（目前只有 "使用者中止"）
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
目標專案持久的 `openspec/specs/`；同一個 change 已被 archive 過、目標資料夾已存在時，會先把舊的
改名為 `<name>-2` / `<name>-3` … 再呼叫 CLI（OpenSpec 拒絕覆寫既有 archive，也不提供 force 旗標）。
使用者選擇不 archive、或 archive 本身失敗，都只印警告，不影響工作流程結束狀態。

### 關鍵函式

| 函式                    | 所在檔案           | 說明                                                                                                                                                                                                         |
| ----------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `route_after_confirm()` | `workflow.py`      | 條件路由：`confirmed` → execute；`needs_revision` → replan；`aborted` / `error` → END                                                                                                                        |
| `route_after_review()`  | `workflow.py`      | 條件路由：只讀取 `review_node` 已判定好的 `review_blocking`（不再自行解析 review 文字）——`False`（通過）→ `archive_change`；`True` 且已達 iteration 上限 → END（放棄重試，不 archive）；其餘 → replan        |
| `increment_iteration()` | `workflow.py`      | 增加重試計數，重設 status 為 `pending`                                                                                                                                                                       |
| `archive_node()`        | `nodes/archive.py` | review 通過後先問一次是否要 archive（`_ask_should_archive()`），同意才呼叫 `openspec_runner.archive_change()`（目標已存在則先把舊 archive 改名讓出）；純機械式動作，不佔用 Claude 呼叫，略過或失敗都只印警告 |
| `build_workflow()`      | `workflow.py`      | 編譯 `StateGraph`，回傳可執行的 app                                                                                                                                                                          |

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

**模式判斷（依 `AgentState` 欄位，依序判定）：** `is_rerun`（即 `state["start_from"] == "analyze_plan"`）
只在使用者透過網頁重跑按鈕或命令列 `--node analyze_plan` 主動重跑時為真——`main.py` 的 `run_node()`
在呼叫這個 node 前才設這個暫態欄位（不寫入 `state.json`），工作流內部因 review 退回自動回到
`analyze_plan`（走 `increment` 節點）不會觸發。

| 順序 | 模式                        | 觸發條件                                                                    | 工具     | 模型 |
| ---- | --------------------------- | ---------------------------------------------------------------------------- | -------- | ---- |
| 1    | 已封存報錯                  | `is_rerun` 且該 change 已封存（見下方「已封存任務」）                        | 不呼叫 Claude | — |
| 2    | 依人工意見調整計畫          | `human_feedback` 非空（含被中斷的調整，見下方「調整」模式的接回）             | `revise` | opus |
| 3    | 重新規劃（review 觸發）     | `review_result` 非空且 `review_blocking` 為 `True`                          | `revise` | opus |
| 4    | 調整                        | 不屬於以上任何一種，且 `is_rerun` 且 `analysis` 非空（已完成過規劃）          | `revise` | opus |
| 5    | 已規劃但非重跑入口報錯      | 不屬於以上任何一種，且 `analysis` 非空但 `is_rerun` 為否（舊 `state.json` 或直接呼叫 node；正常路由不會出現） | 不呼叫 Claude | — |
| 6    | 初始規劃                    | 不屬於以上任何一種（全新任務）                                                | `plan`   | opus |

`is_replan` 因此定義為 `bool(review_result) and review_blocking`——只看 `review_result` 非空已不足夠：
review 通過後 `review_result` 仍留著最後一份報告，若不檢查 `review_blocking` 會把「調整」誤判成
「依審查結果重新規劃」。順序 3 命中、且 `is_rerun` 為真、`session_node`／`session_id` 插槽裡沒有屬於
`analyze_plan` 的中斷 session 時，會先以選擇題問使用者「依審查結果重新規劃」或「輸入調整內容」
（`_ask_rerun_mode()`，`interaction.ask(kind="choice")`；非互動式環境或使用者中止視為前者，維持
既有行為）；選「輸入調整內容」就降級成順序 4 的調整模式。工作流內部自動回到 `analyze_plan`
（`is_rerun` 為否）或已有可接回的 session 時，順序 3 不提問，直接重新規劃——這跟已中斷的調整
（順序 2）接回不提問是同一個道理：那個答案只用來決定要不要問，問過一次之後的狀態已經記在
`human_feedback`／`review_blocking` 裡，不需要再問一次。

順序 4 要求 `is_rerun`，否則落入順序 5：已完成規劃但不是使用者主動重跑進來（工作流內部正常路由
不會走到這裡，只有舊 `state.json` 或直接呼叫 `analyze_plan_node()` 才會遇到）直接
`_fail("此 change 已完成規劃，請以重跑 analyze_plan 進行調整")`，不提問、不呼叫 Claude——避免掉進
初始規劃後重問分支／spec／domain 並覆寫整份規格。

**調整模式：** 順序 4 命中時，以必填文字題 `interaction.ask(kind="text", required=True)` 詢問
「請輸入本次要調整的內容」（`_ask_adjustment()`；命令列空字串重問，`EOFError`/`KeyboardInterrupt`/
非互動式環境視為 `status: "error"`，不呼叫 Claude、task 與規格皆不變）。取得內容後直接重用「依人工
意見調整計畫」的 prompt 與工具（不新增第四份 `_SYSTEM`，見下方「三種 Prompt 版本」）：把內容寫進
`human_feedback`、清空 `review_result`／`review_level`／`review_blocking`，並呼叫 `_append_adjustment()`
把任務描述保留原文、附加一個空行與下一個編號的「調整 N：<內容>」（`N` 等於既有「調整 k：」行數
加一）回寫進 `state["task"]`——這個更新後的 `task` 會出現在送給 Claude 的 prompt 裡（取代注入
`<<HUMAN_FEEDBACK>>` 的那段修改意見本身只放本次新增內容），讓網頁任務列與之後 review 看到的需求
描述累積全部調整歷史。成功完成後這個模式額外把 `iteration` 重設為 0，審查重試次數重新起算；若
Claude 呼叫中途被中斷，`_fail()` 回傳的 `task`／`human_feedback`／session id 照常存進
`state.json`，下次重跑命中順序 2（`human_feedback` 已非空），不再詢問、不再附加，直接以
`call_resuming()` 接回同一個 session。

**已封存任務：** 順序 1 命中時直接 `_fail("此 change 已封存，請以新任務進行後續修改")`，不呼叫任何
`interaction.ask()`。判定邏輯 `_is_archived_change()` 委派給 `lib/openspec_runner.is_change_archived()`：
`openspec/changes/archive/` 底下有名稱為 `<change_name>` 或以 `-<change_name>` 結尾的目錄，且
`openspec/changes/<change_name>/` 當前不存在，才視為已封存——不能用 `archive_destination_name()`，
它組出來的名稱前面加的是「今天」的日期，對已經封存在過去日期資料夾下的 change 永遠比對不上。
這份規則放在 `lib` 層而非寫死在節點裡，是因為網頁任務列（`web/repo_view.py` 的 `_is_archived()`）
共用同一個函式——否則「網頁看得到的任務」跟「重跑會被判定已封存的任務」容易兜不起來。

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

確認 `branch_name`／`project_dir` 後，執行／審查／archive，以及初始規劃時工作分支本地已存在的情況，
都會透過 `git_ops.ensure_on_branch()` 切到該分支（已存在則 `checkout`，不存在則 `checkout -b` 從目前
HEAD 建立）——這一步在呼叫 Claude 之前就完成，不再讓 Claude 自己 checkout。

**初始規劃、且工作分支本地不存在時，改為讓使用者選擇起點分支並先同步：** 這一步只發生在初始規劃
（`execute`／`review`／`archive` 切到既有分支時不會觸發，因為那時工作分支必然已存在）。流程在原本
呼叫 `ensure_on_branch()` 之前先用 `git_ops.branch_exists()` 判斷工作分支是否已存在，不存在才走這條
路徑：

1. `_ask_base_branch()` 用 `git_ops.list_local_branches()` 列出目標專案全部本地分支（依名稱排序），
   以 `interaction.numbered()` 組成「編號. 分支名稱」選項，目前所在分支加註「（目前分支）」，向使用者
   提問「要從哪個分支建立 `<branch_name>`？」。直接 Enter 或非互動式環境採用目前分支（detached HEAD
   時直接 Enter 要重問，非互動式環境則直接回傳空字串）；輸入非清單內編號會提示後重問；使用者中止
   （EOF／Ctrl-C）回傳空字串，呼叫端 `_fail()` 記為錯誤，不建立工作分支、不呼叫 Claude
2. 取得起點分支後呼叫 `git_ops.create_branch_from(project_dir, branch_name, base_branch)`：
   `checkout base_branch` → 用 `rev-parse --abbrev-ref --symbolic-full-name @{u}` 判斷有無 upstream
   →有則 `pull --ff-only`（失敗或逾時都回傳 `(False, 訊息)`，停在 `base_branch` 上，不建立
   `branch_name`；沒有 upstream 則印出「起點分支 `<base>` 未設定 upstream，略過 git pull」直接略過
   這步）→ 同步成功（或略過）後 `checkout -b branch_name`
3. 失敗（切換起點分支失敗、`git pull` 失敗或逾時）時 `_fail(f"無法建立分支 {branch_name}：{msg}")`，
   錯誤說明包含工作分支名稱與 git 回報的原因，工作分支不會被建立，系統不進入規格撰寫

起點分支只在這次呼叫內使用，不寫進 `AgentState`——後續節點只需要 `branch_name`，不需要知道當初從哪個
分支建立。

**Domain 歸屬確認、`openspec init`／`new change`（皆已搬到 Python，呼叫 Claude 之前完成）：**
初始規劃在 `ensure_on_branch()` 之後、組 prompt 之前，依序執行：

1. `openspec_runner.ensure_initialized()`：`<目標專案>/openspec/` 不存在才執行一次性
   `openspec init --tools none --force`（只建目錄，不安裝 workflow skill），已存在則直接略過
2. Domain 歸屬：先 `_recover_domains()`——依序看當前 `AgentState["domains"]`、同 change 的
   `.agentloop/changes/<change_name>/state.json`、`openspec/changes/<change_name>/specs/`、
   以及（change 已被 archive 時）`openspec/changes/archive/<YYYY-MM-DD-name>/specs/`。
   還原得到名稱就印「沿用上次的 domain」、注入 `_DOMAIN_CONTEXT_EXISTING`，
   **不再提問**（review 通過後驗收又開一輪完整工作流、或 `--node analyze_plan` 進同一個 change
   時，不該再選一次）。還原不出才 `_ask_domain_selection()`：用 `_list_existing_domains()` 列出
   `<目標專案>/openspec/specs/` 底下既有的 domain（資料夾名稱）；沒有既有 domain 時不提問，直接
   視為新建 domain。有既有 domain 時在終端機列出清單 + 一個「以上皆非，建立新 domain」選項，讓
   使用者輸入編號選擇本次規格 delta 歸屬哪個（可用逗號輸入多個編號，對應「同一任務涉及多個既有
   domain」的情況）；非互動式環境預設視為新建 domain。送給 `interaction.ask()` 的 `options` 一律是
   「編號. 文字」格式（例如「1. web-gui」「2. 以上皆非，建立新 domain」），讓網頁模式的選項按鈕能把
   編號交給工作流，效果與終端輸入同一編號相同。選定的既有 domain 名稱清單會組進 system
   prompt 的 `_DOMAIN_CONTEXT_EXISTING` 區塊（只給名稱；`## Purpose` 的寫法在 `openspec-authoring` skill）。回傳空清單（確定是
   純粹新建 domain：沒有既有 domain，或使用者選了「建立新 domain」）時，額外呼叫
   `_ask_domain_purpose()` 讓使用者選填這個新 domain 的 Purpose 文字；有填就用
   `_DOMAIN_CONTEXT_NEW_WITH_PURPOSE`（只傳使用者這段文字，並要求 `## Purpose` 原樣採用、不改寫；
   與 Intent 對齊等格式規則在 skill），留白（含非互動式環境、使用者中止）則用 `_DOMAIN_CONTEXT_NEW`
   （只告知這是新 domain、請依任務語意命名）。若使用者選擇同時涉及既有 domain 又可能需要新 domain（回傳清單
   非空），是否額外建立新 domain 完全交給 Claude 判斷，不會觸發這個 Purpose 提問——Python 只在
   「確定會建立新 domain」時才問。規劃成功後把名稱寫進 `AgentState["domains"]`；若當次是「新
   domain 且名稱由 Claude 自訂」，改從 change 資料夾的 `specs/` 回填
3. `openspec_runner.ensure_change_created()`：change 資料夾不存在才執行 `openspec new change
<name>`，已存在則直接略過

這三步都不再透過 Claude 的 Bash 呼叫執行，Claude 收到的 system prompt 直接是已確定的結果
（「目標專案與 Domain」區塊），不需要再探索或提問。domain 提問只在初始規劃且還原不出上次歸屬
時跑；同一 change 再進初始規劃（驗收後開新一輪、或 change 已被 archive 後重建）會沿用
`state.json` 裡的 `domains`。沿用階段（`_CHANGE_SETUP_EXISTING` 的 replan／human-revise）本來
就不走這一步。

**是否撰寫 spec（`skip_specs`，問在 domain 之前）：** 初始規劃在 `openspec init` 之後、domain
歸屬之前，先 `_recover_skip_specs()`——依序看當前 `AgentState["skip_specs"]`（只有明確的布林算數，
`None` 與舊 state 缺這欄都不算）、同 change 的 `state.json`、change 資料夾的 `.openspec.yaml`、
以及 archive 快照裡的 `.openspec.yaml`。還原得到布林就印「沿用上次的決定」、**不再提問**。還原不出
才 `_ask_skip_specs()`：終端機問 y（需要寫 spec）或 n（不需要）。n 寫入 `skip_specs: true`，由程式
直接略過後面的 domain 提問（不寫進 prompt）。y 寫入 `skip_specs: false`，照舊走 domain。三份
system prompt 只多一行 `skip_specs: true` 或 `skip_specs: false`；怎麼寫 `.openspec.yaml`、略過
哪些檔，以 `openspec-authoring` skill 為準，不在 prompt 重述。非互動式環境預設 y；使用者中止則
`status: "error"`。接回中斷的 session 時不重問（還原不到就視為要寫 spec）。重新規劃與依人工意見
調整只讀這個欄位（舊 state 沒有就預設要寫 spec），注入同一行旗標，不再提問。決定隨
`state.json` 持久化，所以驗收後對同一個 change 再開一輪會沿用。

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
validate 的錯誤修正也接到同一套「有問題就等使用者、否則繼續」的迴圈裡；跨程序接回上次撞到
用量上限而中斷的 session（見下方「跨程序接回：session 插槽」）走的也是同一個參數。接回時會
**略過是否撰寫 spec 與 domain 歸屬提問**，因為那些答案只用來組完整 prompt，接回時不會送出。

**依模式而異的提問規則：**

- **初始規劃 / 依人工意見調整計畫**：完整 grilling 流程——依 grilling 逐一提問，過程中依 domain-modeling 即時更新 `CONTEXT.md` / `docs/adr/`。初始規劃在強制三項還寫不出來時繼續問（三項的內容與「不是任務原句複述」以 skill 為準）；依人工意見調整時只在意見影響這些項時才重問，不重跑完整 Specine 清單
- **重新規劃（review 觸發）**：**只針對 review 結果 grill**——針對審查標記的每個問題點逐一提出質疑性問題（判斷是否成立、修正方向如何取捨），不要求重新走一遍完整的 grilling 釐清或 Specine 清單，也不強制 domain-modeling 文件同步；更新規格時仍須維持強制三項（寫在哪個欄位以 skill 為準）

**三種 Prompt 版本：**（調整模式刻意不新增第四份 `_SYSTEM`，重用 `_SYSTEM_HUMAN_REVISE`——見上方「調整
模式」；`<<HUMAN_FEEDBACK>>` 只放本次調整內容，累積的調整歷史靠 `<<PROJECT_CONTEXT>>` 之後注入的
「任務：」那行帶上附加過的完整 `task`）

| 版本                   | 用途                                                                                                                                                                                                                                                                                                                               |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_SYSTEM_INITIAL`      | 全新任務規劃：Read/Glob/Grep 探索 → grilling 互動釐清（同步 domain-modeling；grill 結果須含 Specine 強制三項）→ 依「OpenSpec 產出規則」撰寫 proposal.md / specs delta / tasks.md（非小改動時另寫 design.md）於系統已建好的 change 資料夾（目標專案／domain／`openspec init`／`new change` 皆已由 Python 事先確認並附在 prompt 裡） |
| `_SYSTEM_REPLAN`       | 帶入 `<<REVIEW_CONTEXT>>`（`review_result`，截斷至最後 3000 字）與 `<<REVIEW_LEVEL>>`；依「重寫／修補」分流見上（rollback 已由 Python 事先完成），並用專屬的 `_REVIEW_QUESTION_PROTOCOL` 針對 review 結果逐點 grill；沿用既有 change，不重新 `openspec new change`                                                                 |
| `_SYSTEM_HUMAN_REVISE` | 帶入 `<<HUMAN_FEEDBACK>>`（`human_confirm` 收到的使用者修改意見，或重跑 analyze_plan 取得的調整內容）：理解意見（不夠明確則提問）→ 視需要重讀程式碼 → 視需要更新 domain-modeling → 更新既有 change 的規格文件                                                                                                                   |

三份 `_SYSTEM` 共用的 `_ANALYZE_PROHIBITIONS` 區塊裡有一條雙向的勾選限制：**不得變更 `tasks.md`
任何勾選狀態**——完成標記只由 `execute` node 在實作後即時更新；analyze 階段不論哪個模式都只能新增
或改寫 `- [ ]`，既有 `- [x]` 維持原文。這條規則只寫在共用區塊一次（遵守「Keep prompts from
growing」），不在個別 `_SYSTEM` 裡重複描述。

**輸出格式與解析邏輯：**

規格正文只寫在 OpenSpec change 資料夾，聊天不再重複一份「## 分析」「## 計畫」或 TASK 清單，最終
回應一句話回報完成狀態即可——`PROJECT_DIR:`/`CHANGE_NAME:` 這兩行輸出契約已經取消，因為
`project_dir`／`change_name` 現在在呼叫 Claude 之前就由 Python 決定好了，不需要再從回覆解析。

- `state["analysis"]`、`state["plan"]` **只讀檔**：`analysis` 讀該 change 資料夾下 `proposal.md` 全文；`plan` 讀 `tasks.md` 的 checkbox 清單（`_TASK_CHECKBOX_RE`）。單一事實來源是 OpenSpec CLI 自己會 `validate` 的檔案；`proposal.md` 或 `tasks.md` 讀不到（或 tasks 沒有任何 checkbox）視為錯誤（`status: "error"`），不 fallback 去 regex 聊天文字
- 涉及新增或修改行為的 TASK，須額外排入對應的「撰寫／更新測試」TASK，讓 `execute` 有明確依據依 tdd skill 執行紅-綠循環；純文件、設定調整或不改變行為的重構可不需要
- 是否需要新增「更新文件」TASK，依該任務所屬專案的 `CLAUDE.md` / `AGENT.md` 判斷：說明檔要求同步維護 `docs/` 商業邏輯說明文件才排入，未提及此類慣例則不強制新增

**注入的 Skills（完整內容）：** 初始規劃／依人工意見調整用 `_SKILLS`（`grilling`、`domain-modeling`、
`tdd`、`openspec-authoring`）；重新規劃（review 觸發）改用 `_SKILLS_REPLAN`（`grilling`、`tdd`、
`openspec-authoring`），**不含** `domain-modeling`——`_SYSTEM_REPLAN` 本來就明講「不需重新進行完整
的 grilling 釐清或文件同步」，注入它的完整內容（這幾個 skill 裡最大的一塊）純屬浪費 token。`tdd`
三種模式都注入完整內容（見下方「Skill 系統作為知識注入」關於為什麼不能只列名稱）。

**規格格式來自 `openspec-authoring` skill，不再寫在節點程式碼裡。** 產出規則、Specine 對齊、檔案
骨架範本原本是 `analyze_plan.py` 的三個模組常數（`_OPENSPEC_ARTIFACT_RULES` /
`_SPECINE_ALIGNMENT` / `_OPENSPEC_TEMPLATES`），以字串內插進三份 `_SYSTEM`；現在整份移到
`AgentLoop/.claude/skills/openspec-authoring/SKILL.md`，改走既有的 skill 注入機制。這份 skill 檔案
是規格格式的**唯一事實來源**——下面的條列只是導覽，細則以 SKILL.md 為準。移出去的好處是改規格格式
不必動節點程式碼，而且這些規則可以被單獨當成 system prompt 餵給 Claude 做 prompt eval
（`AgentLoop/tests/evals/`，預設不隨 `pytest` 執行，見 `pytest.ini` 的 `eval` marker）。

**已知副作用：骨架範本現在三種模式都會注入。** 範本原本刻意只放在 `_SYSTEM_INITIAL`——replan／
依人工意見調整都是 Edit 既有 change 資料夾裡已存在的檔案，Claude 直接 Read 就看得到實際格式，
再送一次空白骨架是白花 token。移進 skill 之後它與產出規則同在一個檔案，而 `openspec-authoring`
同時列在 `_SKILLS` 與 `_SKILLS_REPLAN`，所以 replan 也會收到那段範本，這個 token 最佳化已經失效。
要恢復的話得把範本另外拆成一個只列在 `_SKILLS` 的 skill。

**OpenSpec Change 建立與規格文件範本：** 規格文件不再是 AgentLoop 自訂的單一 Markdown 檔案，而是遵照 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 的 change 資料夾格式，寫在目標專案的 `<project_dir>/openspec/changes/<change_name>/` 底下：

- **建立階段**（僅初始規劃，皆由 Python 在呼叫 Claude 前完成，見上方說明）：`ensure_on_branch()`
  checkout 分支 → `ensure_initialized()` bootstrap `openspec/` → `_ask_domain_selection()` 確認
  domain 歸屬 → `ensure_change_created()` 建立 change 資料夾
- **沿用階段**（`_CHANGE_SETUP_EXISTING`，replan／human-revise 共用）：`project_dir`/`change_name`
  沿用 `AgentState` 已存的值，不重新 `init`/`new change`，直接 Edit/Write 同一個 change 資料夾；
  「重寫」等級的 replan 在 Claude 完成撰寫、`openspec validate` 通過後，由 `_reset_task_checkboxes()`
  把 `tasks.md` 所有 checkbox 重設回 `- [ ]`（純字串處理，不需要 Claude 再做一次）
- **產出規則**（`openspec-authoring` skill，三種模式共用）：章節結構維持 OpenSpec，不另開 Specine 專章；skill 裡的「Specine 規格對齊」一節把十項對齊要素對應進既有欄位。強制三項缺一不可（純重構且 `skip_specs: true` 時 Intent 仍須寫目的，輸出／範例可註明無外部可觀察行為）：規範目的 → `proposal.md` 的 `## Intent`（新建 domain 的 `## Purpose` 與其對齊）；輸出要求 → Requirement 的 SHALL/MUST 與主路徑 Scenario 的 THEN（資料類型、格式、約束）；範例及解釋 → 至少一個主路徑 Scenario 的「逐步邏輯」（從輸入到輸出）。其餘七項適用才寫：背景 → Intent／Approach；關鍵概念 → domain-modeling；輸入要求 → GIVEN/WHEN；邊界／錯誤處理 → 額外 Scenario；APIs／提示 → Approach 或 `design.md`
  - `proposal.md`：`## Intent`（規範目的，適用時補背景）/ `## Scope`（In scope / Out of scope）/ `## Approach`（適用時寫 APIs、建議演算法／資料結構）
  - `design.md`（採 OpenSpec 預設：小改動可略過、不要建立空檔；有架構取捨、新模組／接縫、或需要留下技術債時才寫）：`## Technical Approach` / `## Architecture Decisions` / `## Testing Strategy`（含「Seam（測試接縫）」「測試案例矩陣（Test Matrix）」固定小節，矩陣須涵蓋主路徑逐步範例）/ `## Technical Debt & Follow-up Notes`；一旦撰寫，沒有內容也要保留標題填「無」，不可留白或整段刪除
  - `specs/<domain>/spec.md`（delta，可能有多個 domain）：只用 `## ADDED Requirements` / `## MODIFIED Requirements` / `## REMOVED Requirements` 三種分節，`### Requirement:`（SHALL/MUST/SHOULD，一個 Requirement 只講一件事，含輸出要求）+ `#### Scenario:`（逐步邏輯 + GIVEN/WHEN/THEN，至少一個主路徑須含從輸入到輸出的逐步解釋，THEN 須含輸出格式／約束）；新建 domain 才加 `## Purpose`（與 Intent 對齊，或直接採用使用者透過 `_ask_domain_purpose()` 指定的文字，見上方「Domain 歸屬確認」）；純重構/文件/設定且使用者在初始規劃選擇不寫 spec 時，在 `.openspec.yaml` 設 `skip_specs: true` 略過（決定來自終端提問並寫入 `skip_specs`，見上方「是否撰寫 spec」；prompt 只帶 `skip_specs: true|false` 這一行，產出規則以 skill 為準）；REMOVED 移除某 domain 最後一個 Requirement 時需設 `retire_capabilities: true` 才會被 archive 一併刪除該 domain 的 spec。寫之前須先 Read/Grep 目標專案已合併的 `openspec/specs/<domain>/spec.md`（不是這次 change 的 delta），逐一比對既有 Requirement 的規範範圍：能合併或完全重複就用 MODIFIED 改寫，找不到才用 ADDED，避免同一件事拆成多個重疊的 Requirement；Requirement／Scenario 標題用抽象措辭涵蓋規則本身，不寫死具體數量或列舉值（例如「兩個權限皆為 true」），否則功能擴充時舊標題對不上新情況，被迫另開一個而非既有規則自然涵蓋；既有標題已寫死「單一／僅含一個」時，MODIFIED 必須改寫該 Scenario（含標題），禁止另開並列條目；Requirement 與 Scenario（含逐步邏輯）都只能用自然語言描述規範（系統對外呈現的行為與約束），不寫實作細節（不限技術棧：前端 DOM/CSS/元件庫、後端 DB 欄位型別/SQL/框架 API/內部函式類別變數名稱之外，也包括具體程式碼片段或條件式如 `a.b === true`、框架特定的生命週期或渲染機制用語如掛載/mount/render——判斷依據一律換成業務語言），實作方式留給 `design.md` 的 Technical Approach
    - **spec 是正向契約，不是實作差異紀錄**：只描述系統仍保證的行為。沒寫到就沒有承諾（含不存在、送出時不帶、原值不變、不受影響），靠不寫、不准點名。本次拿掉的能力只出現在 REMOVED（從未 specced 則完全不寫），不得進 ADDED／MODIFIED，也不為「別蓋掉舊欄位」另開 Requirement（該手段寫 design.md／tasks.md）。`MUST NOT` 只准約束該 Scenario 已經在講的行為（滑到底載入下一批，AND 在 hasMore=false 後不再請求），不准點名被拿掉或清單裡沒有的項目
    - **以 `openspec/specs` 為唯一基準，不從 proposal 翻譯**：既有 spec 提及的行為本次修改 → MODIFIED、完全移除 → REMOVED、未提及而本次新增 → ADDED；**既有 spec 未提及、本次只是從程式碼移除 → 不寫任何條文**（從未 specced 的東西，移除不需要 spec 紀錄，否則產出的是憑空冒出來的「幽靈功能」規格）。`proposal.md` 的 Scope／Approach 講的是工程任務（HOW）不是規格項目（WHAT），禁止把「移除 X 元件」「刪掉 Y API call」翻譯成 Requirement 或 Scenario
    - **消費者視角自檢**：只寫最外層消費者能從邊界外觀察並驗證的事，以「若完全重寫內部實作，這條規格還成立嗎？」自問——成立才是驗收標準，不成立就該移到 `design.md`
    - **Scenario 對應行為分支，不列舉資料變體**：每個 Scenario 必須對應一個不同的行為結果、政策或約束（通常是不同的 GIVEN 或 WHEN）；同一條規則套不同輸入資料不另開 Scenario，合進範例或 GIVEN 前提。同一 Requirement 底下第一個 GIVEN＋WHEN 都相同的 Scenario 必須合併——列出同一個集合的成員（tab 列有哪些標籤、表格有哪些欄）是一條「初始化組成」規則，不是不同分支。集合變大時改寫既有初始化 Scenario（含寫死「單一／僅含一個」的舊標題），禁止留下舊條再並列一條「同時包含 Y」。真正不同分支才另開（例如點擊切換 tab、切換語系）
    - **API 欄位名稱分前後端**：前端消費端禁止把 endpoint path、request/response 欄位名稱寫進 spec（改用業務描述，欄位名稱留給 `design.md`）；但當本次交付物本身就是 API 合約（`backend-api` 類型專案，或任務明確指出要定義 endpoint／改 response schema）時，這些就是對外承諾、屬於可觀察輸出，可直接寫進 SHALL/MUST 與 Scenario 的 THEN
  - `tasks.md`：`## N. <群組>` + `- [ ] N.M <任務>` checkbox、階層編號——這份檔案本身就是任務清單；`execute` 與 `review` 都自行 Read 完整 change 資料夾（不從 `state["plan"]` 注入扁平清單），`execute` 逐項勾選、`review` 核對完成度
    - **測試刪除任務必須明確列出**：`MODIFIED` 後某些 Scenario 標題不再出現於新版本，要排「移除 `<消失的 Scenario 標題>` 測試」；`REMOVED` 整條 Requirement，要排 Requirement 層級的「移除相關測試」，**並**為其下每個 Scenario 各排一個「移除 `<Scenario 標題>` 測試」。`execute` 依 tasks.md 裡的 Scenario 標題原字串，在該測試本體裡定位該刪的測試；沒列出來的測試會殘留，而殘留的舊測試會讓 `review` 的 Spec 追溯誤判
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

- 列印分析摘要、執行計畫（含數量；逐行印出 tasks.md checkbox 原文，沿用其 1.1、2.1 階層編號，不另加序號）、OpenSpec change 路徑與工作分支
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
2. Read `openspec/changes/<change_name>/` 下的 proposal.md、specs/**/\*.md、tasks.md（若有 design.md 一併讀取）。規格、驗收條件與任務清單以這些檔案為準，**不**把 `state["plan"]` 扁平清單貼進 prompt，也 **不\*\*注入 `state["task"]`（原始使用者描述只給規劃用；execute 的工作範圍就是 change 資料夾，再貼一次會讓它重新診斷原始問題、略過 tasks.md 已收斂的剩餘項）
3. 依 `project_context.build_project_doc_hint_for(project_dir)` 指名的目標專案，Read 讀取其 `CLAUDE.md` / `AGENT.md`，了解架構、指令（測試、lint、build 等）、目錄慣例、程式碼規範與技術棧；找不到說明檔則自行 Read/Glob/Grep 探索並比對現有風格
4. 依偵測到的技術棧，**自行**從可用的 skills 中挑選並使用適合的其他 skill（例如 Vue 專案適用 `vue-best-practices`、Nuxt + Vitest 專案適用 `nuxt-vitest-msw`）——不寫死任何特定技術棧的 skill 清單。這些完全不經過 `skill_loader.py`，靠 Claude Code 自己原生的 skill 探索機制（只認執行者 `$HOME/.claude/skills/`，見下方「Skill 系統作為知識注入」）；`tdd` 已固定完整注入（見下方「注入的 Skills」），不需要另外挑選
5. 若該專案 `docs/` 目錄存在，讀取其下所有現有文件，了解商業邏輯說明；`docs/` 目錄不存在時不需自行建立

**執行方式：** 依 change 資料夾內 `tasks.md` 的順序嚴格依序處理（不重排）：

- `- [ ]` 必須執行；`- [x]` **預設略過**，略過前先 Read/Grep 核對該項聲稱完成的檔案是否真的在磁碟上、內容是否對得上規格——對得上才略過，對不上才重做該項。這條寫在 `_SYSTEM` 裡，所以即使 session 失效、冷啟動重送完整 prompt，也不會把已完成的實作重做一遍（`RESUME_AFTER_INTERRUPT_PROMPT` 另外保住「做到一半」的脈絡）
- **不** commit——是否提交由使用者事後決定
- **不**自行呼叫 `/code-review`——後續有獨立的 Review Agent 依專案規格審查本次修改
- tasks.md 中若有「撰寫／更新測試」的 TASK，**必須**依 `tdd` skill 的紅-綠循環執行：先寫會失敗的測試，再寫最小可行實作讓測試通過，最後重構；不可先完成其他 TASK 的實作、事後才回頭補測試
- 過程中定期執行型別檢查與單一測試檔案，全部 TASK 完成後執行完整測試

未完成項嚴格依序做完；先 Read 再 Write/Edit，避免覆蓋不相關程式碼；風格、命名、目錄結構、i18n／型別／auto-generated 檔案等規則，一律依該專案 `CLAUDE.md` / `AGENT.md` 的說明判斷，不硬編碼在 prompt 裡。每完成一個 TASK，立即用 Edit 把該任務對應的 OpenSpec change（`<project_dir>/openspec/changes/<change_name>/tasks.md`，路徑由 `AgentState["project_dir"]`/`["change_name"]` 組成）裡對應的 checkbox 從 `- [ ]` 改成 `- [x]`，讓這份檔案即時反映實際完成進度，供 `review` 節點核對。

**文件同步要求：** 是否需要同步更新文件，依該任務所屬專案的 `CLAUDE.md` / `AGENT.md` 判斷——說明檔要求同步維護 `docs/` 商業邏輯說明文件才需處理（依 `tasks.md` 中對應的文件更新 TASK 執行，或在說明檔明確要求但 `tasks.md` 未包含時主動補上）；說明檔未提及此類慣例時不需要主動撰寫或更新文件。

**強制測試與自動修復：** 依該專案 `CLAUDE.md` / `AGENT.md` 中列出的測試指令執行測試；若說明檔未列出，探索 `package.json` / `pyproject.toml` 等設定檔判斷正確指令。測試失敗時分析錯誤並修復、重跑，最多重試 3 次；3 次後不論結果如何都繼續輸出最終摘要。

**最終輸出格式（文字摘要，不含測試輸出）：**

1. 所有已修改的程式碼檔案清單
2. 所有已新增/修改的說明文件清單
3. 每個 TASK 的完成狀態（✅ 已完成 / ❌ 未完成 + 原因）

**注入的 Skills：** `tdd`（完整內容，見下方「Skill 系統作為知識注入」關於為什麼不能只列名稱）；其餘依偵測到的技術棧由 Agent 自行從可用 skills 中挑選使用（依賴 Claude Code 自己的原生 skill 探索，不經過 `skill_loader.py`）。不 commit、不自行 `/code-review`，流程寫在 `_SYSTEM`。

**撞到用量上限後跨程序接回同一個 session：** 中斷時把 session id 存進 `AgentState` 的插槽，重跑 `python -m AgentLoop.main --node execute` 並選同一個 change 就會接回續作，不重跑已完成的 TASK。機制與 `analyze_plan`／`review` 共用，見下方「跨程序接回：session 插槽」。

---

### 4. `review`（程式碼審查 Agent）

**職責：** 扮演資深程式碼審查者，依 `code-review` skill 的流程，從 Standards 與 Spec 兩軸（各自透過平行 sub-agent）審查本次修改。

**工具權限：** `review`（Read, Glob, Grep, Bash, **Task**）—**不可修改任何檔案**
（`Task` 是必要的：`code-review` skill 需要平行呼叫 Standards / Spec 兩個 sub-agent）
**Timeout：** 600 秒（每次嘗試）

**Spec ↔ 測試追溯：由 Python 在呼叫 Claude 之前跑完（`_run_spec_trace_check()`）。** 抽出該 change
`specs/**/*.md` 裡所有 `#### Scenario:` 標題，逐一 `grep -r` 目標專案原始碼找完全相同的文字
（限常見原始碼副檔名，排除 `node_modules`／`dist`／`build`／`.next`）。這件事
原本是 `_SYSTEM` 的一條指示，要 Claude 自己列標題、自己 grep、自己把缺漏當成阻塞性問題——身為自然
語言指示，它完全依賴 Claude 真的照做，實測出現過「有 Scenario 根本沒有對應測試，卻仍回報
`Ready to merge? Yes`」的情況。搬到 Python 之後，結果是算出來的而不是請求來的。

結果分兩條路：

- **有 Scenario 缺測試**：**直接短路，這一輪完全不呼叫 Claude**，回傳 `review_blocking: True` +
  `review_level: "修補"`，`review_result` 裡列出缺哪幾個 Scenario，直接進下一輪 replan。這是
  `review_node` 唯一一條**不呼叫 Claude 就做出阻塞判定**的路徑（另外兩條不呼叫 Claude 的路徑
  ——找不到 `code-review` skill、找不到 change 目錄——分別是 SKIPPED 與 error，不是判定），
  也讓「`execute` 漏寫測試」的代價從「一份可能放水的報告」變成「一輪確定會補上的 replan」。
  注意這條路徑的 `review_result` 只有 `## Spec` 一段、沒有 Standards 軸，那是短路的正常產物，
  不是報告被截斷
- **全部都有對應測試**：把逐項的 ✅／❌ 清單以 `<<SPEC_TRACE_RESULT>>` 注入 prompt 供報告引用，
  `_SYSTEM` 的第 3 條指示因此改成「直接引用上方事前檢查結果，不要自己再 grep」

`_SYSTEM` 的 `Ready to merge?` 判準裡仍保留一條「Spec 追溯有缺漏一律 No，且優先於不影響功能正確性
的判斷」。實務上這條幾乎不會被觸發——真有缺漏時上面那條短路已經先回去了，注入的清單必定全為 ✅；
它留著是防 grep 比對到同名但其實不是測試的字串時，Claude 仍有依據判 No。

**完整性檢查與重試（`_is_well_formed_review()`）：** `claude -p` 是一次性、非互動呼叫，沒有「之後
再回來補完」這回事——但實測過（含一次真實失敗案例的 log 分析）發現 Claude 有機率把 Task sub-agent
或 Bash 測試指令視為可以延後處理，寫下「等測試結果回來後整合最終報告」之類的話就提前結束這輪回應，
而不是真的等到 tool_result。從實際失敗的 log 來看，兩個 sub-agent 本身確實是同步等到結果才繼續的，
斷點出現在後續「額外操作指示」要求跑的實際測試指令——Claude 在尚未拿到該指令的 tool_result 前就
寫出總結文字並結束回應。`_SYSTEM` 裡加了一段「完整性要求」明講不可以背景執行、不可以用「稍後」之類
的話結束回應，但這只是自然語言指示：實測證明**單靠這段指示不足以可靠防止問題**——一個經過完整
skill 全文、兩輪 sub-agent 往返、額外驗證步驟之後的深層決策點，指示的影響力會被稀釋，且 Claude
當下往往已經主觀認定「答案已經確認」而不覺得需要真的等測試跑完，所以指示留著只當作便宜的第一道
防線，不能單獨依賴。

真正可靠的是事後檢查：這種提前結束的回應缺少 code-review skill aggregate 步驟一定會產出的
`## Standards`／`## Spec` 標題，若不攔截，`has_blocking_issues()` 找不到「Ready to merge?」會
預設回傳 `True`（阻擋），`extract_review_level()` 找不到 `REVIEW_LEVEL:` 會預設回傳「修補」——
等於把這段不完整的文字當成一份「發現嚴重問題」的正常審查結果存檔、送進 replan，讓下一輪規劃收到
毫無意義的假回饋。`review_node()` 因此在拿到回應後先用 `_is_well_formed_review()`（檢查是否同時
有 `## Standards` 與 `## Spec`）判斷是否跑完整個流程；沒跑完就用 `--resume` 接續同一個 session
（不重新從頭跑一次 sub-agent／測試，省時間也省 token）丟 `_REVIEW_CONTINUE_PROMPT` 要求它真的等
結果、把報告寫完，最多重試 `_MAX_REVIEW_ATTEMPTS`（3）次；仍然不完整就回傳 `status: "error"`，
不讓這種回應進入正常的 blocking／replan 判斷。這個檢查不管 Claude 是為什麼提前結束都能攔下來，
不像 `_SYSTEM` 的指示得靠 Claude 自己遵守。

這整個補完迴圈被 `call_resuming()` 包在外層（見下方「跨程序接回：session 插槽」），所以 review
也能接回上次撞到用量上限而中斷的 session。接回失敗而退回完整 prompt 時，`_MAX_REVIEW_ATTEMPTS`
的額度會重新計算，不沿用接回那一輪已經用掉的次數。

**審查依據：**

異動與規格都以檔案為準，prompt **不**注入 `state["plan"]` 扁平清單，也 **不**注入 `execution_result`。fixed point（固定為 `HEAD`）與 spec 來源（OpenSpec change 資料夾）由本節點參數提供給 `code-review` skill，不經由 skill 自己詢問使用者或找 issue tracker——這兩步在 `AgentLoop/.claude/skills/code-review/SKILL.md` 這份專案內建副本裡已經直接拿掉（見下方「Skill 系統作為知識注入」的說明）。

- **Fixed point**：本次修改尚未 commit，固定為 `HEAD`（`git diff HEAD` 取得完整異動，不用三點 diff）
- **Spec 來源**：`<project_dir>/openspec/changes/<change_name>/`（`AgentState["project_dir"]`/`["change_name"]` 組成的路徑）——Read 讀取其下 proposal.md / tasks.md / specs/\*_/_.md（若有 design.md 一併讀取；小改動可能沒有此檔，不視為缺漏），也可用 `openspec show <change_name> --json` 快速確認結構；若該 change 已被前一輪迭代 archive，改讀 `<project_dir>/openspec/specs/` 下對應 domain 的 spec.md
- **Standards 來源**：依 `project_context.build_project_doc_hint_for(project_dir)` 指名的目標專案，讀取其 `CLAUDE.md` / `AGENT.md`，以及其中提及或專案根目錄下的 `CODING_STANDARDS.md` / `CONTRIBUTING.md`（若有）
- 其餘仍依 skill：Fowler smell baseline、平行 sub-agent、以 `## Standards` / `## Spec` 並陳報告

**額外操作指示：**

1. 確認 TASK 清單完整性：Read `tasks.md`，依其 checkbox 狀態（`- [x]` 已完成／`- [ ]` 未完成）逐項核對，列出未完成的 TASK 編號
2. 依偵測到的專案讀取其說明檔中列出的測試指令並實際用 Bash 執行測試（找不到則探索 `package.json` / `pyproject.toml`）；測試失敗計入 Standards 軸的問題
3. Spec ↔ 測試追溯：**直接引用** `<<SPEC_TRACE_RESULT>>` 的事前檢查結果納入 Spec 軸報告，不要自己再 grep（見上方「Spec ↔ 測試追溯」）。另外用自己的判斷檢查本次新增或改動的測試有無重複、情境可否合併，重複或高度重疊的以 `SUGGESTION` 列出——但**不得建議刪到讓任何 Scenario 完全沒有對應測試**

（原本還有一步「確認 docs/ 商業邏輯說明文件是否同步更新」，已從 `_SYSTEM` 移除——`execute`
自己已經有「文件同步要求」，review 端再重複檢查一次不是必要步驟，且步驟越多，Claude 在深層
agentic 流程中提前結束回應的風險越高，見上方「完整性檢查與重試」的說明。）

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

`Ready to merge? No` 保留給兩類情況：**嚴重影響功能**的問題（核心邏輯錯誤、功能無法正常運作、資料損毀或資安風險、架構根本偏差、TASK 大量未完成），以及**Spec 追溯發現任何 Scenario 缺少對應測試**（這一類通常在上方的事前檢查就已經短路返回「修補」，不會走到這裡）。兩者都一律自動判定為需要重新規劃，不詢問人工：

| 等級     | 觸發條件                                                              |
| -------- | --------------------------------------------------------------------- |
| **重寫** | 核心邏輯錯誤、架構根本偏差、多個互相關聯的根本性問題、TASK 大量未完成 |
| **修補** | 小 bug、測試失敗、遺漏文件同步、個別 TASK 未完成、小幅修正            |

其餘不影響功能正確性的問題（風格、可讀性、效能微調等）一律回答 `Yes`，改列在 `SUGGESTION n:` 建議清單中，交由人工決定：`review_node` 會逐條印出建議、在終端機提示輸入要修改的編號（`1,3`／`all`／直接 Enter 表示不修改）；非互動式環境預設不修改任何建議。人工選中至少一條時才視為需要重新規劃（`review_level` 一律標記「修補」，並把選中的建議附加在 `review_result` 末尾的「人工確認：選定修改的建議事項」小節，供 `analyze_plan` 重新規劃時只針對這些點 grill）；未選中任何建議或無建議可選時直接視為通過。

**路由結論：** 以上兩種情況（嚴重問題 / 人工選中建議）都會把 `review_blocking` 設為 `True`，交由 `route_after_review` 讀取決定是否重新規劃；其餘情況 `review_blocking` 為 `False`，直接結束流程。

**審查結果：** 完整的 `review_result` 字串隨 `state.json` 一併持久化（每次 review node 結束後由 `main.py` 的 `_save_state()` 寫入，不論通過或不通過），不再另存獨立的 review 報告檔案。

---

### 5. `archive_change`（收尾節點，`nodes/archive.py`）

**職責：** review 判定通過（`review_blocking=False`）後的機械式收尾動作——把這次的 OpenSpec change 併入目標專案持久的 `openspec/specs/`。這是「該不該 archive」的判斷（review 通過就 archive），不需要 Claude 的判斷力，因此**不呼叫 `call_claude()`**，純 Python 直接跑 `openspec` CLI，不佔用一次 Claude 呼叫、不耗費 token。

**觸發時機：** 只在 `route_after_review()` 判定 `review_blocking=False` 時進入；`status=="error"` 或 `review_blocking=True` 且已達 iteration 上限（放棄重試）時直接 END，不會進入這個節點——沒有通過審查的東西不併入持久 specs/。

**人工卡控：** 定位到 change 位置、（有需要時）checkout 完分支後，實際呼叫 `openspec archive` 前，`_ask_should_archive()` 在終端機問一次「是否要將此 change 併入 `<project_dir>/openspec/specs/`？[y/N]」——單層問法，答 `y` 才 archive，其餘（`N`、直接 Enter、非互動式環境、Ctrl-C/EOF）一律視為否、略過 archive 並印出手動指令，跟其他 archive 略過的情況一樣不讓整個工作流程失敗。CJK 提示文字改用 `print(..., end="")` 印出、`input()` 不帶 prompt 參數，避免重蹈 `human_confirm` 曾修過的「CJK readline 提示吃字元」問題（見 `f59edb4`）。

**執行內容：** 透過 `openspec_runner.archive_change(project_dir_abs, change_name)`（`openspec_runner.py`，跟 `claude_runner.py` 是「唯一跟 claude CLI 對話的地方」同樣的角色，這裡是唯一跟 `openspec` CLI 對話的地方）執行 `openspec archive <change_name> --yes --json`，把 change 的 spec delta 合併進 `openspec/specs/`、change 資料夾搬到 `openspec/changes/archive/YYYY-MM-DD-<name>/`。目標名稱的計算跟 OpenSpec CLI 一致：change 名稱已以 `YYYY-MM-DD-` 開頭就原樣使用（分支轉 kebab-case 時常如此），否則前置今天的本地日期。呼叫 CLI 前若該目標已存在（同一 change 被 archive 過後又改、再 archive），`vacate_existing_archive()` 會把舊資料夾改名為 `<name>-2` / `<name>-3` … 讓出原名——OpenSpec 拒絕覆寫既有 archive，也不提供 suffix / force 旗標；舊快照保留不刪。成功時結果帶 `vacated_as`，`archive_node` 會印出改名後的路徑。

**單獨執行：** `python -m AgentLoop.main --node archive`（不帶參數，從列出的 changes 選一個）。`change_name` 一律取 `AgentState["change_name"]`。`project_dir` 已在 state 裡就直接用；否則直接採用環境變數 `TARGET_PROJECT`（workspace 只支援單一目標專案），再依 `change_name` 的原值／kebab-case 兩種形式比對哪個資料夾實際存在。`branch_name` 仍可選，有填才 checkout。

**失敗處理：** 容錯解析 stdout 的 JSON 診斷（OpenSpec agent-contract 的 `status: StoreDiagnostic[]` 慣例），失敗（`openspec` 指令不存在、validate 沒過、change 不存在等）只印警告訊息並附上手動補跑指令，**不**讓整個 workflow 失敗——程式碼已經審查通過，archive 只是收尾，失敗頂多之後手動執行 `openspec archive <name> --yes`。

**回傳：** 不更動 `AgentState` 任何欄位（`{}`），純粹是收尾動作。

---

## 開發者搜尋工具：`search.py`

**用途：** 對目標專案的 `openspec/` 做語意向量搜尋，以自然語言提問，由 Claude 合成答案（RAG）。這是獨立的開發者工具，不屬於 LangGraph workflow，也不呼叫 `claude` CLI。

```bash
python -m AgentLoop.search "advanced protection 的規格是什麼？"
python -m AgentLoop.search --reindex "query"   # 強制重建索引後再搜尋
```

**所需 env var：** `TARGET_PROJECT`（同主流程）；`ANTHROPIC_API_KEY` 設定時用 Python SDK，未設定時 fallback 到容器 OAuth (`claude` CLI)。模型固定使用 `claude_runner.MODEL_IDS["haiku"]`，不再支援 `SEARCH_MODEL` 覆蓋。

**索引生命週期：**

索引儲存於目標專案的 `openspec/.vector_index/vector.db`（SQLite，由 `sqlite-vec` 擴充提供向量搜尋功能）。每次查詢前自動偵測是否需要重建：只要 `openspec/` 底下有任何 `.md` 檔案比 `vector.db` 新，就自動觸發 reindex。第一次執行（或容器重建後）會由 `fastembed` 自動下載 embedding 模型（`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，約 100 MB），下載後快取於容器的 `~/.cache/fastembed/`；容器重建後需重新下載。

**索引範圍：**

`openspec/specs/`（合併後的主規格，`doc_type=spec`）與 `openspec/changes/`（各 change 的 proposal / design / tasks / spec delta，`doc_type=change_*` 或 `archive_*`）全部索引，每份 `.md` 檔案為一個文件單元。

**搜尋與 RAG 流程：**

```
query
  │
  ▼
fastembed.query_embed()          ← paraphrase-multilingual-MiniLM-L12-v2 ONNX（本地推論）
  ▼
sqlite-vec KNN search            ← L2 distance，top 5 結果
  │  JOIN documents 取回 path + content
  ▼
_ask_claude()   ← ANTHROPIC_API_KEY 存在時用 SDK；否則 fallback 到 claude CLI
  │  僅允許依文件內容回答，不補充訓練資料
  ▼
自然語言答案 + Referenced files 清單
```

embedding 模型輸出 L2 正規化後的 384 維向量，存為 `float[384]` blob；查詢向量同樣正規化，L2 distance 等價於 cosine similarity 排序。

---

## 節點間協作機制

### 1. 狀態字典傳遞

每個節點讀取前一個節點填入的欄位，再將自己的輸出寫入對應欄位，例如：

- `analyze_plan` → 填入 `analysis`、`plan`、`change_name`、`branch_name`、`project_dir`、`domains`、`skip_specs`；
  調整模式另外改寫 `task`（附加「調整 N：」）並把 `iteration` 重設為 0
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

| 產出物          | 路徑                                                                                                                                                                              | 讀寫者                                                                                                                                            |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| OpenSpec Change | `<project_dir>/openspec/changes/<change_name>/`（`proposal.md`/`tasks.md`/`specs/**/*.md`，非小改動時另有 `design.md`；`<project_dir>`/`<change_name>` 為 `AgentState` 對應欄位） | `analyze_plan` 寫；`human_confirm` 讀 proposal.md + tasks.md 供顯示；`execute` 讀完整 change 後實作並勾選 tasks.md；`review`、`archive_change` 讀 |
| 持久規格        | `<project_dir>/openspec/specs/<domain>/spec.md`                                                                                                                                   | `archive_change` 呼叫 `openspec archive` 合併寫入，跨任務累積                                                                                     |
| 審查結果        | `<project_dir>/.agentloop/changes/<change_name>/state.json` 的 `review_result` 欄位                                                                                               | `review` 執行後由 `_save_state()` 寫入；`analyze_plan` 重新規劃時從 `AgentState` 讀取                                                             |
| AgentLoop State | `<project_dir>/.agentloop/changes/<change_name>/state.json`（`AgentState` 去除 `project_dir` 的 JSON 序列化；每個 node 結束後自動覆蓋）                                           | `main.py` 寫（`_save_state()`）；`--node` 模式下作為入口 state 載入，`project_dir` 在載入時由 `TARGET_PROJECT` 環境變數補回                       |
| 業務文件        | 各偵測到專案的 `docs/` 目錄                                                                                                                                                       | `execute` 寫，`review` 驗證                                                                                                                       |

### 4. Git Diff 作為稽核媒介

`review` 節點執行 `git diff HEAD` 取得所有實際變更，而非僅依賴執行節點的自述，確保審查基於事實。

### 5. Skill 系統作為知識注入

`skill_loader.py` 讀取 Claude Code Skill 文件，以完整內容或僅列名稱的方式注入系統提示。查找順序為專案內建的 `AgentLoop/.claude/skills/<name>/` 優先，找不到才 fallback 到使用者本機的 `~/.claude/skills/<name>/`。目前 `_FULL_CONTENT_SKILLS` 白名單完整注入的是 `grilling`、`domain-modeling`、`code-review`、`tdd`、`openspec-authoring`。

**為什麼 `tdd` 也一定要完整注入，不能只列名稱：** 實測過 `claude -p`（`claude_runner.py` 唯一呼叫 `claude` CLI 的地方）發現，Claude Code **原生**的 skill 探索機制（在系統提示的 `available skills` 清單、`Skill` 工具背後）只認執行者的 `$HOME/.claude/skills/`，跟 `claude_runner.py:165` 呼叫 subprocess 時設的 `cwd=REPO_ROOT` 完全無關——不管 cwd 指到哪裡，找到的永遠是同一份 `$HOME/.claude/skills/` 清單（曾用一個完全空的 cwd 目錄重複驗證過）。這代表 `AgentLoop/.claude/skills/` 底下隨版控帶著走的內建副本，原生機制**永遠不會發現**；只列名稱的 skill 能不能被 Claude 用到，完全取決於執行者自己的 `~/.claude/skills/` 剛好有沒有同名 skill——換一台機器、換一個沒有這些 skill 的使用者，就會失效，違反本檔案開頭「讓專案自帶所需 skill、不依賴使用者本機設定」的設計目標。白名單機制（Python 直接讀檔、逐字塞進 prompt）不經過原生探索，因此不受這個限制，是唯一能保證跨機器一致運作的方式。`openspec-authoring` 的情況更極端：它只存在於 `AgentLoop/.claude/skills/`，任何人的 `~/.claude/skills/` 都沒有同名 skill，只列名稱的話永遠解析不到，等於規格格式整段消失。

規格格式由 `openspec-authoring` skill 提供（原本寫死在 `analyze_plan` 的 `_OPENSPEC_ARTIFACT_RULES`，見上方「規劃 Agent」），執行流程寫在 `execute` 的 `_SYSTEM`。fallback 路徑（`~/.claude/skills/<name>/`）仍保留給其餘依技術棧動態選用、專案未內建的 skill（例如 `vue-best-practices`、`nuxt-vitest-msw`）——這些完全交給 Claude Code 自己原生的 skill 探索機制處理，不經過 `skill_loader.py`，所以確實受「執行者本機有沒有這個 skill」影響；這是刻意的設計取捨，因為 AgentLoop 不可能預先知道每個目標專案會用到哪些技術棧專屬的 skill。

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
| `plan`     | Read, Write, Glob, Grep             | 建立文件（`analyze_plan` 初始規劃，只新增檔案）                            |
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

### 語言政策

`LANGUAGE_POLICY` 是一段共用的提示區塊，注入 `analyze_plan`（三個 `_SYSTEM` 都有）、`execute`、`review` 的系統提示尾端，取代原本各自一行的「請用繁體中文回答。」。它把語言切成兩邊：

- **過程敘述用英文**：Claude 邊做邊說的文字，也就是上方執行流程第 3 步以 dimmed 格式印出的灰字。這些內容 `_log_event()` 只 print 不存（連終端也只顯示每段的第一行、截斷至 120 字），但整段都算 output token，而 output 比 input 貴；同樣語意的英文約只需中文一半的 token。
- **交付物維持繁體中文**：所有寫出的檔案（OpenSpec 文件、程式碼註解、`docs/nodes/review/` 報告）、對使用者說的話（含每個 `QUESTION:` 行），以及**最終回應**。

這條界線不是風格偏好，而是功能需求：最終回應會寫進 `state.json`（`execution_result`／`review_result`）、直接呈現給使用者，並被 `review.py` 的 `extract_review_level()` 以 `REVIEW_LEVEL:\s*(重寫|修補)` 解析——中文字面值換成英文會讓它抓不到而一律 fallback 成 `修補`。所以要省 token 只能省過程敘述，不能整體換語言。

### 互動式提問（grilling）支援

`ClaudeResult` 帶有 `session_id`；`_log_event()` 偵測到助理輸出以 `QUESTION_MARKER`（`"QUESTION:"`）開頭時，會用醒目格式即時印出提問內容。`call_claude()` 的 `resume` 參數可帶入先前呼叫回傳的 `session_id`，讓上層（目前僅 `analyze_plan._run_with_grilling()`）能以同一個 Claude session 延續多輪一問一答，不必每輪重新提供完整上下文。

### 用量上限暫停機制

`call_claude()` 包含一個 `while True` 重試迴圈：`is_usage_limit_error()` 判定錯誤屬於「等重置就會好」的用量上限時，**暫停工作流程**並在 terminal 提示使用者：

- 按 **Enter** → 等待用量重置後重新呼叫 Claude
- 輸入 **`q`** 後按 Enter → 中止程序並回傳原始錯誤結果

stdin 已關閉（非 TTY / pipe EOF）時自動中止，避免無限等待。

**判定方式是關鍵字清單＋句型比對兩層，缺一不可。** `_TOKEN_LIMIT_KEYWORDS`（`rate limit`、`429`、`credit balance`、`billing` 等）只涵蓋 API／計費類訊息；訂閱制（Pro / Max / Team 席位）印的是另一組句子，**一個關鍵字都對不上**：

```
You've hit your session limit · resets 3:45pm
You've hit your weekly limit · resets Mon 12:00am
You've hit your Opus limit · resets 3:45pm
```

漏判的後果不是重試失敗，而是整個節點直接以 `status: "error"` 收場（實際發生過：`execute` 在 1.8 秒內結束，`review` 跟著以「上游發生錯誤」跳過，工作流結束）。因此 `_LIMIT_MESSAGE_RE`（`hit your …… limit`）額外比對整句形狀，也涵蓋未來可能出現的其他 per-model 上限。反向排除 `context limit`——脈絡視窗滿了等重置也不會好（由 auto-compact 處理），不可停在等待人工按鍵的狀態。

**重試時接續原本的 session，不重開新的：** 中斷前那次呼叫若已經透過串流事件拿到 `session_id`（代表 Claude session 已經建立，中途才因限流被打斷），按 Enter 繼續時會改用 `--resume <session_id>` 接上同一個 session，並只送出一段簡短的接續指示（`RESUME_AFTER_INTERRUPT_PROMPT`：先確認目前檔案與 tasks.md 實際進度、不要重做已完成的部分、也不要假設中斷前最後一個動作一定完整），而不是重新送出原始的完整 prompt。這避免了「中斷前已經寫入的部分變更/已打勾的 checkbox，被一個完全沒有記憶的新 session 忽略或重做」的問題。只有在中斷發生得太早、連 `session_id` 都還沒拿到時，才會退回重送原始 prompt、開一個全新 session。

這個迴圈只在**程序還活著**時有用。使用者輸入 `q`、Ctrl-C，或節點回傳 error 讓工作流結束之後，就要靠下面的 session 插槽把 id 持久化到 `state.json` 才接得回去。

### 跨程序接回：session 插槽

`AgentState` 的 `session_node` / `session_id` 是一個**單一插槽**，`analyze_plan`、`execute`、`review` 三個節點共用，只透過 `core/session.py` 的 `take_session(state, node)` / `store_session(node, session_id)` 讀寫。

**為什麼是單一插槽而不是 node → id 的字典：** 每個 change 同時只會有一個中斷中的 session。節點撞到上限就讓整個工作流停下（`review` 看到上游 `status: "error"` 直接跳過、`route_after_review` 也在 error 時 END），不可能有第二個節點接著跑到一半又被中斷；節點正常產出結論時也會清掉自己的插槽。`store_session()` 因此是整份取代而非合併——換節點時舊的自然被丟掉，不會留下沒人清的殘留 id。

**插槽仍然記著 owner node**，因為 `--node` 可以從任一節點切入：`execute` 絕對不能去 `--resume` 一個 `analyze_plan` 留下的 session（工具權限 `plan` vs `full`、當時交辦的工作都不同）。`take_session()` 看到 owner 不符就回空字串，讓該節點開全新 session。

三個節點的行為一致，由 `claude_runner.call_resuming()` 統一處理：

- 中斷時存下 `ClaudeResult.session_id`；該次連 id 都沒拿到（上限發生在最開頭）則保留插槽原本的值，不覆蓋成空。`analyze_plan` 的 guard／前置步驟（切分支、`openspec init`）失敗時也保留，因為那時根本還沒呼叫 Claude
- 產出結論時**清掉**——之後再接回只會帶進過期脈絡（例如下一輪 `execute` 面對的規格可能已被 replan 改寫）
- 重跑（`--node <節點>` 選同一個 change）時用 `--resume` 接回，並只送 `RESUME_AFTER_INTERRUPT_PROMPT` 這段續作指示，**不重送完整 prompt**——沒有記憶的新 session 會重新探索、把做到一半的最後一項從頭來。execute 的 `_SYSTEM` 已要求略過核對過的 `- [x]`，冷啟動不再重做已完成項；接回仍能保住做到一半的脈絡，也避免再付一次完整探索
- session 已失效（換機器、`agent_home` volume 重建、Claude 端過期）時退回完整 prompt 重跑；但**接回後又撞上限不算失效**，維持回報以便再存一次 id，避免退回完整 prompt 而重做已完成的工作

`call_resuming()` 接收呼叫端提供的 `run(prompt, resume)`，因為各節點對 Claude 的呼叫包著不同的自有迴圈：`analyze_plan` 是 grilling 問答加 `openspec validate` 修正迴圈（後者自己也會撞上限，所以 `_run_with_validate()` 一併回傳最後的 session id），`review` 是「報告提前結束就要求補完」的重試迴圈（接回失敗而退回完整 prompt 時，補完次數的額度會重新計算）。`analyze_plan` 接回時還會**略過 domain 歸屬提問**——那個答案只用來組完整 prompt，接回時不會送出。

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

| 技術              | 版本     | 用途                                        |
| ----------------- | -------- | ------------------------------------------- |
| **LangGraph**     | ≥0.2.0   | StateGraph 工作流程編排、條件路由、節點串接 |
| **python-dotenv** | ≥1.0.0   | 讀取 `.env` 環境變數                        |
| **fastembed**     | ≥0.2.6   | 本地 ONNX embedding 推論（`search.py` 用）  |
| **sqlite-vec**    | ≥0.1.0   | SQLite 向量搜尋擴充（`search.py` 用）       |
| **anthropic**     | ≥0.40.0  | Anthropic Python SDK（`search.py` RAG 用）  |
| **fastapi**       | ≥0.115.0 | 網頁控制台 HTTP API（`web/app.py`）         |
| **uvicorn**       | ≥0.30.0  | ASGI 伺服器，容器 CMD 直接啟動              |
| **httpx**         | ≥0.27.0  | FastAPI `TestClient` 依賴                   |
| **Python**        | 3.11     | 執行環境                                    |

### Claude Code CLI 層

| 技術                                              | 說明                                                                                                                                                                                                                                                                     |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Claude Code CLI** (`@anthropic-ai/claude-code`) | 以 `claude -p` 啟動 Agent，使用本地身份驗證（不需要 API Key）；容器內有獨立於 host 的登入狀態，見下方「Claude 設定掛載」                                                                                                                                                 |
| **stream-json output**                            | 即時串流 JSON 事件，支援 `assistant`、`tool_use`、`tool_result`、`result` 類型                                                                                                                                                                                           |
| **Built-in Tools**                                | Read、Write、Edit、Bash、Glob、Grep、Task（Claude Code 原生工具）                                                                                                                                                                                                        |
| **Skill System**                                  | `AgentLoop/.claude/skills/`（專案內建，優先）或 `~/.claude/skills/`（fallback）中的 Markdown 文件，動態注入 Agent 系統提示                                                                                                                                               |
| **OpenSpec CLI** (`@fission-ai/openspec`)         | 規格文件遵照的 change/spec-delta 規則來源；`openspec_runner.py` 是唯一跟這個 CLI 對話的模組，`analyze_plan` 用它 `init`/`new change`/`validate`，`archive_change` 節點用它 `archive`——皆由 Python 直接呼叫，不透過 Claude 的 Bash 工具。同樣透過容器內的 Node.js 22 安裝 |

### 目標專案技術棧

系統本身不假設固定技術棧——透過 `project_context.py` 動態偵測工作區內各專案的 `CLAUDE.md` / `AGENT.md`，`execute` 與 `review` 節點再依偵測結果自行選用對應 skill（例如 `vue-best-practices`、`nuxt-vitest-msw`）。

### 容器化層：Docker outside of Docker（DooD）

AgentLoop 容器本身不跑 Docker daemon，而是讓容器內的 Docker CLI 透過掛載進來的 host `docker.sock` 直接操控**宿主**的 Docker engine——因此容器內執行的 `docker` / `docker compose` 指令，實際上是宿主 daemon 在執行，其建立的所有 bind mount 也以宿主上的路徑為準。這讓 Agent 能在容器內對任一目標專案執行 `docker compose up / exec` 等指令來啟動服務、跑測試，而不需要在 AgentLoop 容器內重新起一顆 daemon（DinD）。

| 技術                            | 說明                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Docker**                      | 以 `python:3.11-slim` 為基底，加裝 Node.js 22 執行 Claude Code CLI（`@anthropic-ai/claude-code@2.1.285`；`claude-opus-5-5` 等新模型要求 CLI ≥ 2.1.280，該版宣告 Node ≥ 22），並加裝 `docker-ce-cli` + `docker-compose-plugin`（僅 CLI，不含 daemon）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **Docker Compose 路徑掛載**     | 自 v0.5.0 起改掛載**整個工作區根目錄**（`${HOST_WORKSPACE_ROOT}:${HOST_WORKSPACE_ROOT}`），而非只掛 `AgentLoop/` 與單一 `TARGET_PROJECT`，讓網頁控制台能切換目標專案、用資料夾選擇器看到其他專案，不需要為此重建容器；路徑同樣用「與 host 相同的絕對路徑」，原因不變：宿主 daemon 幫目標專案建立 bind mount 時，用的是掛載路徑「字串本身」，該字串必須在宿主上真實存在，否則會掛到空目錄。目標專案改由網頁設定（`web/settings.py`，優先於 `.env` 的 `TARGET_PROJECT`）決定，`project_context.py` 的動態偵測邏輯本身不寫死任何專案名稱。仍只支援單一目標專案同時執行，不提供多專案並行的擴充方式                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **`/var/run/docker.sock` 掛載** | `- /var/run/docker.sock:/var/run/docker.sock`，讓容器內 Docker CLI 連上宿主 daemon（DooD 的核心）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **對外埠**                      | `ports: ["127.0.0.1:8000:8000"]`：網頁控制台只綁 host 的 `127.0.0.1`，不對外開放；容器內 `command` 為 `python -m uvicorn AgentLoop.web.app:app --host 0.0.0.0 --port 8000`，前端由映像的 `WEB_DIST_DIR` 建置產物提供                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **Claude 設定掛載**             | 分兩塊，刻意分開：(1) 登入狀態（`.claude/` 其餘內容、`.claude.json`）掛在容器專屬的 `agent_home` named volume（`- agent_home:/home/agent`），**不**與 host 共用——原因是若直接掛載 host 的 `~/.claude`，host 與容器內的 `claude` subprocess 會共用同一份 OAuth 憑證檔，兩邊同時使用時 token refresh 互搶，會導致容器內 node 執行到一半認證失效、或剛啟動時讀到寫入中的檔案顯示未登入；因此改為另外設定認證——首選在 host 執行 `claude setup-token`，將產出的 token 寫入 `.env` 的 `CLAUDE_CODE_OAUTH_TOKEN`（或改設 `ANTHROPIC_API_KEY`）；容器內互動式 `claude login` 仍可用但非首選，因為 `docker exec -it` 的嵌套 TTY 貼授權碼常因 paste 截斷或過期顯示 `Invalid code`。登入狀態隨 volume 持久化，容器重建不會遺失。(2) skills 內容：本專案用到的 skill 已直接複製進 `AgentLoop/.claude/skills/` 隨專案版控、不再依賴掛載即可運作；host 的 `${HOME}/.claude/skills:/home/agent/.claude/skills:ro` 與 `${HOME}/.agents:/home/agent/.agents:ro`（純靜態、無寫入需求）仍保留唯讀掛載，作為 `skill_loader.py` 的 fallback 來源，供 Agent 依偵測到的技術棧動態選用專案未內建的其他 skill（`~/.claude/skills` 底下多為指向 `~/.agents/skills` 的符號連結，需一併掛載才能解析）。`working_dir: ${HOST_WORKSPACE_ROOT}` |
| **非 root 使用者**              | `agent` 使用者執行 `claude --dangerously-skip-permissions`（Claude Code 安全要求，禁止 root 下執行），並設定 `NOPASSWD` sudo 僅限執行 `/usr/bin/docker`——因為宿主掛入的 `docker.sock` 擁有者/群組由宿主環境決定，非 root 使用者常無法單靠 group 權限連線，故一律透過 sudo 執行 docker 指令                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |

---

## CLI 入口：`main.py`

### 完整工作流程模式

```bash
python -m AgentLoop.main "幫我在後端新增一個 GET /tables/featured 端點"
```

### 單節點起點模式

```bash
# 列出目標專案的 changes 供選擇，跑完後繼續後面的完整流程
# 都不帶任務描述——任務描述取自選定 change 的 state
python -m AgentLoop.main --node analyze_plan
python -m AgentLoop.main --node execute
python -m AgentLoop.main --node review

# archive 是終點，跑完即止
python -m AgentLoop.main --node archive

# 搭配 --change <name>：直接載入指定 change 的 state.json，不顯示終端選單；
# 找不到該 change 就以錯誤結束（exit 1）。網頁控制台的重跑功能即透過這個組合呼叫，
# 讓 web/runner.py 的子行程不需要經過終端選單互動
python -m AgentLoop.main --node execute --change feat-login
```

`--node X` 的語意是「從 X 開始跑剩下的完整工作流程」：指定 node 跑完並存 state 後，透過 `_stream_and_save()` 以 `config={"configurable": {"start_from": <next_node>}}` 繼續執行剩餘 node（`workflow.py` 的 `_route_start` 讀取此 config 決定 entry point）。`review` 的 next_node 由 `_route_after_review()` 決定（通過 → `archive_change`；可重試 → `increment`；error/超限 → 直接結束），`analyze_plan` → `human_confirm`，`execute` → `review`。State 一律從 `<project_dir>/.agentloop/changes/<change_name>/state.json` 載入（列出已有 state.json 的 changes 供選擇），`project_dir` 由 `TARGET_PROJECT` 環境變數補回。`human_confirm` 不在 `--node` 可選清單中，只能作為完整工作流程的一部分執行。`--state-file` 已移除，state 只能來自 `.agentloop/`。

**`--node` 模式不接受任務描述**（傳了 `parser.error` 直接拒絕）：`task` 已經在選定 change 的 state 裡，CLI 再傳一份只會無條件覆蓋原值並被 `_save_state()` 寫回，實際造成過 state.json 裡的 `task` 被佔位字串或後續的單句指示取代。四個節點因此都**必須**選到一個既有的 change——原本 `analyze_plan` 找不到 change 時允許全新開始的路徑已移除，因為那時根本沒有任務描述可用；全新任務走完整工作流程模式。`archive` 原本「以 CLI 參數當 change 名稱、不需要 state」的用法也一併取消（`_list_and_select_change()` 對所有節點一視同仁，該參數早已無法傳達到 `archive_node`）。

---

## 網頁控制台（v0.5.0）

在不改變任何節點提示詞、路由與判定規則的前提下，容器內另外跑一個網頁服務，取代原本只能
`docker exec` 進容器下指令、以終端 `input()` 回覆提問的操作方式。架構決策見
`docs/adr/0001-web-gui-interaction-port-and-subprocess-run.md`。

### 架構圖

```
瀏覽器 (Vue 3 SPA, 每 2 秒輪詢)
   │  HTTP JSON
   ▼
uvicorn + FastAPI  (AgentLoop/web/app.py)      ← 容器 CMD，監聽 0.0.0.0:8000，compose 只綁 host 127.0.0.1:8000；靜態檔來自 WEB_DIST_DIR
   │  ├─ web/settings.py   設定檔讀寫、合併 .env、遮罩 secret、資料夾瀏覽
   │  ├─ web/runner.py     單一作用中執行（子行程、日誌、提問/回覆檔、中止、session 回寫）
   │  ├─ web/repo_view.py  讀 .agentloop/changes/*/state.json、openspec/changes(/archive)、openspec/specs
   │  └─ web/search_api.py 重用 search.py 的索引／檢索／回答函式
   ▼
子行程：python -m AgentLoop.main ...   (start_new_session=True，env 帶 AGENTLOOP_INTERACTION=web、AGENTLOOP_RUN_DIR、設定值)
   └─ nodes → lib/interaction.py（網頁實作）→ question.json / answer.json
```

### 互動埠：`lib/interaction.py`

節點內所有提問都改經 `interaction.ask(prompt, *, kind, stage, options=None, required=False,
multiline=False)` 與 `interaction.is_interactive()`，取代原本各自呼叫
`input()` / `sys.stdin.isatty()` / `sys.stdin.readline()`：

- **命令列模式**（未設定 `AGENTLOOP_INTERACTION`）：`ask()` 直接委派給 `input()`（`kind="pause"`
  委派 `sys.stdin.readline()`，`multiline=True` 委派一個連續兩個空行或 EOF 結束的多行讀取迴圈），
  `is_interactive()` 直接委派 `sys.stdin.isatty()`——既有測試對 `builtins.input` / `sys.stdin.isatty`
  的 patch 之所以依然有效，靠的是 `tests/conftest.py` 的 autouse fixture 在每個測試開始前清掉
  `AGENTLOOP_INTERACTION`／`AGENTLOOP_RUN_DIR`，確保測試套件不受外部 shell 殘留的網頁模式環境
  影響；而 `claude_runner._run_claude_once()` 啟動 `claude` 子行程時不把這兩個變數傳進去（見下方
  「用量上限暫停」段落後的說明），所以 agent 在 execute／review 中執行的 `pytest` 也不會誤入網頁
  模式。提示文字與分支邏輯不受影響：呼叫端照舊自己 `print()` 提示，`ask()` 的 `prompt` 參數在這個
  模式下不使用。
- **網頁模式**（`AGENTLOOP_INTERACTION=web`）：`is_interactive()` 一律回傳 `True`；`ask()` 把
  提問寫成 `$AGENTLOOP_RUN_DIR/question.json`（`{id, stage, kind, prompt, options, required,
multiline, created_at}`），每 0.5 秒輪詢同目錄的 `answer.json`，讀到 `id` 相符的回覆後刪除
  兩檔並回傳答案文字。必填檢查與「提問已結束」判斷在寫入 `answer.json` 的那一端
  （`web/runner.py` 的 `answer()`），`interaction.ask()` 本身只管問與等。
  用量上限暫停（`claude_runner.call_claude()`）有一個額外陷阱：網頁模式的「繼續」就是回傳空
  字串，跟命令列用空字串代表 stdin 已關閉（EOF）是同一個值、不同語意，`claude_runner.py` 因此
  用 `interaction.is_web_mode()` 把「空字串＝中止」這條判斷限定在命令列模式才生效。
  `claude_runner._run_claude_once()` 啟動 `claude` 子行程時，以 `os.environ` 複製一份、
  移除 `AGENTLOOP_INTERACTION`／`AGENTLOOP_RUN_DIR` 後才傳給 `subprocess.Popen` 的 `env=`：
  這兩個變數是「工作流行程↔web 控制台」之間的互動埠，`claude` 子行程及它執行的工具指令（例如
  execute／review 節點呼叫的 `pytest`）都不是提問方，繼承到的話會讓 `is_interactive()` 誤判為
  網頁模式、卡在輪詢一個不存在的 `answer.json`。父行程自己讀取 `AGENTLOOP_RUN_DIR` 寫
  `session.json` 的邏輯（見下）不受影響，因為那是父行程直接讀 `os.environ`，不經過傳給子行程的
  那份複製。

目前走互動埠的呼叫點：`analyze_plan` 的分支名稱／起點分支選擇（工作分支本地不存在時）／是否寫
spec／domain 選擇／新 domain 名稱／domain Purpose／grilling 提問、`human_confirm` 的 y/N 與修改意見、
`review` 的建議事項挑選、
`archive` 的是否併入 specs、`claude_runner.call_claude()` 的用量上限暫停（`kind="pause"`，
`stage` 取自 `core/stages.current_stage()`）。**新增任何提問點都必須走這裡**，否則網頁模式下
會卡住等不到回覆，命令列模式下則可能誤用非互動預設值。

選項題的「編號. 文字」清單統一由 `interaction.numbered(items)` 產生（回傳 `["1. a", "2.
b", ...]`，編號從 1 起算），`analyze_plan` 的 domain 歸屬提問與 `review` 的建議選擇題共用這份
清單餵給終端 `print()` 與 `ask(..., options=...)`，因此終端清單與網頁選項按鈕看到的編號永遠一致。

### 階段狀態：`core/stages.py` + `AgentState["stages"]`

`AgentState` 新增兩個欄位：`stages`（`analyze_plan`／`human_confirm`／`execute`／`review`／
`archive` 各自的狀態，值只有 `pending`／`running`／`done`／`error`）與 `stage_notes`（目前只有
`"使用者中止"`）。`core/stages.py` 提供：

- `start(state, stage)`：該階段記為 `running`，其後各階段重設為 `pending`、清掉該階段的
  note，印一行 `@@AGENTLOOP_STAGE <stage>@@`（供 `web/runner.py` 切分日誌），並通知已註冊的
  listener（見下）。「階段開始即把其後各階段重設為尚未開始」這一條規則同時涵蓋重跑與 review
  退回重新規劃兩種情境，不需要分別處理。
- `finish(state, stage, status, note=None)`：依 `status == "error"` 記為 `error`，否則記為 `done`；
  `note` 有值時一併寫入 `stage_notes[stage]`、回傳也含 `stage_notes`，不傳時回傳只有 `stages`，
  既有呼叫端（`_tracked()`、`run_node()`）不受影響。`stages`／`stage_notes` 的寫入一律經
  `start()`／`finish()`，`web/runner.py` 中止時也呼叫 `finish(state, stage, "error",
note="使用者中止")`（見下方「執行管理」），不在其他模組另外手刻一份複製改寫的邏輯。
- `current_stage()`：目前正在跑的階段名稱，供 `claude_runner` 的用量上限暫停提問標記 `stage`。
- `set_listener(cb)`：`main.py` 在 `run()` / `run_node()` 一開始註冊 `_save_state`，讓
  `start()` 在階段真正開始執行**之前**就能把「執行中」立即寫進 `state.json`——節點本身可能跑
  好幾分鐘，不能等它整個執行完、回傳後才讓使用者在網頁上看到階段已經開始。

`build_workflow()` 用 `_tracked(stage, fn)` 包裝五個節點（`archive_change` 對應 stage
`archive`）；`main.py` 的 `run_node()`（`--node` 直呼節點的路徑）呼叫同一組 `start()`/`finish()`，
行為跟走完整 LangGraph 一致。`_tracked()` 有一個例外：**上游已經是 `error` 時完全不記錄狀態
轉換**，直接呼叫原始節點函式——`human_confirm_node`／`review_node` 在上游錯誤時都會沿著既有
的無條件邊被呼叫一次、內部立刻短路回傳，並沒有真的執行這個階段的工作，所以該階段要維持
`pending` 而不是被標成 `running`/`error`。

### 執行管理：`web/runner.py`

同一目標專案同時只允許一個執行（模組層 `RunManager` + `threading.Lock`，`RunConflict` 例外
對應 API 的 409）：各節點會 `git checkout` 共用的工作目錄，兩個執行並行會互相切走分支，因此
不做排隊、只簡單拒絕。

- **啟動**：`subprocess.Popen([sys.executable, "-m", "AgentLoop.main", ...], cwd=REPO_ROOT,
start_new_session=True, env=合併設定＋AGENTLOOP_INTERACTION=web＋AGENTLOOP_RUN_DIR)`。新增
  任務帶 `"<task>"`；重跑帶 `--node <stage> --change <name>`（`stage` 限
  `analyze_plan`／`execute`／`review`／`archive`，`human_confirm` 不可單獨重跑，跟命令列
  `--node` 的限制一致）。
- **執行目錄**：`$AGENTLOOP_WEB_STATE_DIR/run/`（預設 `AgentLoop/.web/run/`），內含
  `meta.json`（run_id、kind、task、change_name、stage、started_at、pid）、`output.log`、
  `question.json`、`answer.json`、`session.json`。
- **change 名稱偵測**：新增任務時分支名稱決定前，`change_name` 還不知道——查詢執行狀態時用
  `task` 字串＋`state.json` 的 mtime（晚於 `started_at`）掃描 `<target>/.agentloop/changes/*/`，
  找到就寫回 `meta.json`，往後直接採用，不再重複掃描。
- **session 回寫**：`claude_runner._run_claude_once()` 讀到第一個 `session_id` 時，若設定了
  `AGENTLOOP_RUN_DIR` 就寫 `session.json`（`{stage, session_id}`）。
- **中止**：對 process group 送 `SIGTERM`，5 秒後仍存活再送 `SIGKILL`；之後讀該 change 的
  `state.json`，把目前執行中的階段（先看 `stages` 裡誰是 `running`，找不到才退回 `meta.json`
  的 `stage`）經 `stages.finish(state, stage, "error", note="使用者中止")` 記為 `error`＋
  附註，`session.json` 存在的話依 `core.session.store_session()` 覆寫 session 插槽，最後清空
  執行目錄——重跑該階段時會接回同一個 session，跟命令列 `q` 中止再 `--node` 重跑的行為一致。
  沒有 change 名稱（分支名稱尚未決定）或偵測不到 `state.json` 時，只結束 process group、清空
  執行目錄，不回寫狀態——新增任務後仍以暫時列呈現的執行走的就是這條路徑。
- **日誌**：執行結束時依 `@@AGENTLOOP_STAGE x@@` 標記切分 `output.log`、去 ANSI，覆寫到
  `<target>/.agentloop/changes/<name>/logs/<stage>.log`；執行中查詢日誌則直接即時切分
  `output.log`（`live_stage_log()`），不等執行結束。

### HTTP API：`web/app.py` + `web/repo_view.py` + `web/search_api.py`

FastAPI，前綴 `/api`；`repo_view.py` 純讀檔（`.agentloop/changes/*/state.json`、
`openspec/changes(/archive)/`、`openspec/specs/`），`search_api.py` 重用 `search.py` 的索引／
檢索／回答函式（呼叫前用 context manager 暫時覆寫 `os.environ` 套用網頁設定的有效值，並用一把
鎖序列化，因為暫時覆寫行程全域的 `os.environ` 不是執行緒安全的操作）。主要端點：

| Method   | Path                                                                  | 用途                                                                                           |
| -------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| GET      | `/changes`                                                            | 執行中任務列表（排除已封存；舊任務缺 `stages` 時一律視為 `pending`）                           |
| GET      | `/changes/{name}/stages/{stage}`                                      | 階段詳情：結果欄位、note、日誌最後 500 行（執行中即時切分、其餘讀持久化的 `logs/<stage>.log`） |
| GET      | `/changes/{name}/files[/{path}]`                                      | 規格文件瀏覽（`proposal.md`/`design.md`/`tasks.md` 排最前，其餘依路徑排序）                    |
| GET/POST | `/run`、`/runs`、`/changes/{name}/rerun`、`/run/answer`、`/run/abort` | 執行狀態查詢、啟動新任務、重跑、回覆提問、中止                                                 |
| GET      | `/archive`、`/archive/{dir}/files[/{path}]`                           | 已封存任務瀏覽                                                                                 |
| GET      | `/specs`、`/specs/{domain}`                                           | 既有 Spec 瀏覽                                                                                 |
| POST     | `/specs/search`                                                       | 語意搜尋（查無結果回固定訊息；失敗回 502）                                                     |
| GET/PUT  | `/settings`                                                           | 讀寫網頁設定；執行中禁止變更目標專案（409）                                                    |
| GET      | `/fs?path=`                                                           | 資料夾選擇器用的子資料夾列舉                                                                   |

所有「目標專案」相關路徑都以 `os.path.realpath()` 後比對是否仍在 workspace root 底下，防止
路徑穿越；`StaticFiles` 以 `html=True` 掛在 `/`（最後掛載，不蓋過 `/api/*`），`WEB_DIST_DIR`
未設定或目錄不存在時只提供 API，方便本機開發時前端另外用 Vite dev server。

### 前端：`web/frontend/`

Vue 3 + TypeScript + `<script setup>` + Vite，測試用 Vitest + `@vue/test-utils` + jsdom；不
引入 UI 元件庫，Markdown 以 `<pre>` 純文字呈現。階段詳情（`StageDetail`）與待回覆提問
（`QuestionForm`）顯示的使用者可讀輸出一律套用 `style.css` 的 `output-text` utility，保留原文
換行與空白、長字串在區塊寬度內強制折行。`src/api.ts` 集中封裝所有對 `/api/*` 的
`fetch`，元件測試用 `vi.mock('../api')` 取代；`composables/usePolling.ts` 提供 2 秒輪詢。
`src/components/` 依頁面分資料夾：`active-changes/`（`ActiveChanges`／`ChangeRow`／`StageCard`／
`StageDetail`／`QuestionForm`／`NewTaskDialog`）、`archived-changes/`（`ArchivedChanges`）、
`existing-specs/`（`ExistingSpecs`／`SpecSearch`）、`settings/`（`SettingsPanel`）、`utils/`
（跨頁共用的 `FileBrowser`／`FolderPicker`）；四個主分頁對應的元件都掛在 `App.vue` 底下，相對
import 路徑隨資料夾深度調整（例如 `../../api`）。

圖示使用 `@fortawesome/vue-fontawesome`（SVG 版，非 webfont）：`src/icons.ts` 匯出用到的
`free-solid-svg-icons` 清單，`main.ts` 以 `library.add(...)` 註冊並全域掛載
`FontAwesomeIcon`；測試另以 `src/__tests__/setup.ts`（由 `vite.config.ts` 的
`test.setupFiles` 載入）註冊同一份清單，確保 jsdom 掛載時能渲染出帶 `data-icon` 屬性的
`<svg>`，測試可據以斷言圖示種類。「關閉」「重跑」「檢視規格文件」「上一層」「收合／展開」五
個按鈕是純圖示（不顯示文字），以 `aria-label` 承載原文字供測試定位與無障礙朗讀、`title` 提供
滑鼠停留提示（「重跑」停用時 `title` 改顯示停用原因，`aria-label` 仍為「重跑」；「收合／展
開」依 `collapsed` 狀態切換文字與 `chevron-up`／`chevron-down` 圖示）；其餘主要操作、主分
頁、階段狀態徽章與清單項目則是圖示＋文字並存，文字不變，既有以 `.text()` 斷言這些文字的測
試不受影響。

樣式採 Tailwind CSS v4（`@tailwindcss/vite`，不寫 `tailwind.config.js` 或 PostCSS 設定檔），
整體為深色主題（不提供淺色／切換）：`vite.config.ts` 的 `plugins` 加入 `tailwindcss()`，
`src/style.css` 以 `@import "tailwindcss";` 後接 `@theme { --color-... }` 集中定義整個前端用到
的色彩 token，由 `main.ts` 匯入；三層底色由暗到亮遞增：`bg`（頁面背景）／`surface`（卡片、面
板、對話框）／`surface-muted`（卡片內嵌區塊：日誌、規格內文、`<pre>`、hover 底色），另有
`header`（頂部導覽列）、`line`（邊框）、`fg`／`fg-muted`（前景文字）、`on-accent`（主要／危
險按鈕與狀態徽章上的文字）、`overlay`（對話框遮罩）、`primary`／`primary-hover`、
`danger`／`warning`／`success`，以及四個階段狀態色 `stage-pending`／`stage-running`／
`stage-done`／`stage-error`（色碼固定）。`@theme` 另定義 `--animate-breathe`（搭配
`@keyframes breathe`，以 `stage-running` 色呼吸擴散的 `box-shadow`），供執行中的階段卡片套用
`animate-breathe motion-reduce:animate-none`。元件一律只引用這些 token 與動畫 utility（例如
`bg-stage-done`、`text-fg-muted`、`animate-breathe`），不寫任意色碼也不寫 `<style>` 區塊，換色
只需改 `style.css` 一處。`StageCard.vue` 以一張「狀態 → `{ bar, badge }`」對照表分別套用卡片
左側色條 `border-l-stage-*` 與狀態徽章 `bg-stage-*`，未知狀態退回 `stage-pending`；jsdom 不會
計算 Tailwind 產生的 CSS，相關測試因此斷言 class 名稱（色條、徽章、`animate-breathe`）而非實
際顏色，色碼本身以 `style.css` 的 `@theme` 為準。次要按鈕的外觀（邊框、底色、hover、disabled）
同樣集中在 `style.css`，以 Tailwind v4 的 `@utility btn-secondary` 定義一次，元件呼叫點只加尺
寸與版面 class（如 `px-2 py-1 text-sm`、`self-start`）與測試用語意 class（`view-files-button`、
`rerun-button`——後者的警示黃與 hover 色改直接寫在元件上，不再透過 `btn-secondary`），調整
`btn-secondary` 外觀只需改一處；純圖示的「關閉」按鈕不再有固定語意 class，測試一律以
`[aria-label="關閉"]` 定位；主要按鈕未收斂，仍各自重複寫 `rounded-md bg-primary ...`。

---

## 總結

| 面向         | 細節                                                                                                                        |
| ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| 架構模式     | LangGraph StateGraph + 3 個 Claude Agent 節點 + 人工確認閘 + 審查驅動的反饋迴圈 + 純 Python 收尾節點                        |
| 節點數量     | 5（規劃、人工確認、執行、審查、收尾 archive）                                                                               |
| 最大重試次數 | 3 次迭代後強制結束                                                                                                          |
| 執行模型     | 序列執行 + 迭代精修（審查驅動，重新規劃時只針對 review 結果 grill）                                                         |
| 語言         | Python 協調層 + 繁體中文提示（Claude 過程敘述為英文，見「語言政策」）                                                       |
| 目標架構     | 動態偵測，不假設固定技術棧（目前範例：Vue + Ant Design Vue）                                                                |
| 驅動方式     | Claude Code CLI（本地認證，非 API Key）+ OpenSpec CLI（規格文件格式與 archive）                                             |
| 狀態傳遞     | 不可變 TypedDict 流經整個工作流程                                                                                           |
| 產出物       | 目標專案下的 OpenSpec change（規格文件）、執行摘要、審查報告、程式碼變更、review 通過後合併進目標專案持久的 openspec/specs/ |

</content>
