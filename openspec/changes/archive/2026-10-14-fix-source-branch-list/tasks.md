# Tasks

## 1. 起點分支提問改為選項題

- [x] 1.1 以 tdd 紅-綠循環，在 `tests/test_analyze_plan_base_branch.py` 的 `test_lists_branches_and_creates_from_selected_branch`（Scenario: 工作分支不存在時列出本地分支並以使用者選的分支為起點）新增斷言 `mock_ask.call_args.kwargs["kind"] == "choice"`，先確認測試失敗
- [x] 1.2 `nodes/analyze_plan.py` 的 `_ask_base_branch()` 把 `_ask_or_default(...)` 的 `kind="text"` 改為 `kind="choice"`，`options`、答案解析、空白採目前分支、無效編號重問、中止與非互動式處理維持原樣；讓 1.1 通過
- [x] 1.3 執行 `pytest AgentLoop/tests/ -v` 確認全部通過（含 `test_blank_answer_uses_current_branch`、無效編號重問、中止等既有起點分支測試）

## 2. 文件同步

- [x] 2.1 更新 `ARCHITECTURE.md`「1. `analyze_plan`」起點分支段落第 1 點：寫明 `_ask_base_branch()` 以選項題（`kind="choice"`）提問，網頁上每個本地分支顯示為按鈕、另可自訂輸入（空白採目前分支）
