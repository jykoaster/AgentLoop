# Tasks

## 1. 測試（紅）

- [x] 1.1 在 `tests/test_analyze_adjust.py`（或新檔 `tests/test_analyze_failed_retry.py`）以 `analyze_plan_node` 為接縫新增測試，本體含字串「初始規劃失敗後重跑 analyze_plan 重新執行初始規劃且不詢問調整內容」：state 為 `planned=False`、`analysis` 為錯誤訊息、`plan=[]`、`skip_specs=False`、`domains=["auth"]`、`start_from="analyze_plan"`，斷言未詢問調整內容／spec／domain、prompt 為初始規劃、回傳 `planned=True` 且 `task` 未附加「調整 1：」
- [x] 1.2 新增測試，本體含字串「初始規劃因用量上限中斷後重跑接回原 session 續作」：state 帶屬於 analyze_plan 的中斷 session 且 `planned=False`，斷言以該 session resume、無任何提問
- [x] 1.3 新增測試，本體含字串「已完成過規劃的任務調整失敗後重跑仍詢問調整內容」：state 為 `planned=True`、`analysis` 為錯誤訊息、`plan=[]`，斷言第一個提問為「請輸入本次要調整的內容」
- [x] 1.4 新增舊 state 推定測試：無 `planned` 且 `plan` 非空 → 進入調整；無 `planned`、`plan=[]` 且 change 資料夾無 `tasks.md` → 初始規劃
- [x] 1.5 新增測試：初始規劃失敗時回傳 `status="error"` 且 `planned` 維持 False；`planned=True` 時失敗回傳仍為 True
- [x] 1.6 新增測試，本體含字串「依審查結果重新規劃失敗後重跑 analyze_plan 直接重新規劃且不出現選擇題」：state 為 `review_blocking=True`、`review_result` 非空、`review_level="修補"`、`replan_failed=True`、無中斷 session、`start_from="analyze_plan"`，斷言 `interaction.ask` 未被呼叫、prompt 為重新規劃、回傳 `replan_failed=False` 且 `task` 不變
- [x] 1.7 新增測試：依審查結果重新規劃時 Claude 失敗（無 session）回傳 `status="error"`、`replan_failed=True`、`review_blocking` 仍為 True；選擇題選「輸入調整內容」並輸入內容後 Claude 失敗，回傳 `replan_failed=False`、`human_feedback` 為輸入內容
- [x] 1.8 確認 `tests/test_analyze_adjust.py` 中「審查退回後重跑 analyze_plan 選擇輸入調整內容」「審查退回後重跑 analyze_plan 選擇依審查結果重新規劃」兩個既有測試在 `replan_failed` 缺欄位或為 False 時仍出現選擇題並通過（標題原字串已在測試本體，不另開新測試）
- [x] 1.9 新增測試，本體含字串「依人工意見調整失敗後重跑 analyze_plan 以同一份修改意見重新執行」：state 為 `planned=True`、`human_feedback="密碼至少 12 碼"`、`analysis` 為錯誤訊息、`start_from="analyze_plan"`，斷言 `interaction.ask` 未被呼叫、prompt 含「密碼至少 12 碼」、`task` 未附加新的「調整 N：」

## 2. 實作（綠）

- [x] 2.1 `core/state.py` 的 `AgentState` 新增 `planned: bool`、`replan_failed: bool` 欄位與註解；`main.py` 初始 state 加入 `"planned": False`、`"replan_failed": False`
- [x] 2.2 `nodes/analyze_plan.py` 新增 `_is_planned(state, project_dir, change_name)`（欄位為 bool 直接用；缺欄位時以 `plan` 非空或 change 資料夾下 `tasks.md` 存在推定）
- [x] 2.3 `analyze_plan_node` 模式判斷順序 4（調整）與順序 5（已規劃但非重跑入口報錯）改用 `_is_planned(...)`，取代 `analysis` 非空；移除不再使用的 `analysis_state`
- [x] 2.4 `_fail()` 回傳帶出目前的 `planned` 值；成功回傳 `"planned": True`
- [x] 2.5 `analyze_plan_node` 讀入 `replan_failed`（非 `True` 視為 False）；順序 3 只在 `replan_failed` 為否時呼叫 `_ask_rerun_mode()`；模式確定為依審查結果重新規劃時把區域 `replan_failed` 設為 True、降級成調整時設為 False；`_fail()` 回傳帶出 `replan_failed`，成功回傳 `"replan_failed": False`
- [x] 2.6 確認既有測試（`tests/test_analyze_adjust.py`、`tests/test_node_guards.py`、`tests/test_usage_limit_resume.py`）在新判定下仍通過；必要時於其 `_base_state` 補 `planned`／`replan_failed`，不改變其斷言意圖
- [x] 2.7 執行 `pytest AgentLoop/tests/ -v` 全數通過

## 3. 文件同步

- [x] 3.1 更新 `ARCHITECTURE.md`「1. `analyze_plan`」模式判斷表：順序 4／5 觸發條件改為「已完成過規劃（`planned`）」，順序 3 選擇題說明補「`replan_failed` 為真（上次依審查結果重新規劃失敗）時不提問、直接重新規劃」，說明 `_fail()` 會把錯誤訊息寫入 `analysis` 故不以其判定、初始規劃失敗後重跑沿用分支／spec／domain 並接回 session；`AgentState` 欄位區塊補 `planned`、`replan_failed` 說明

## 4. 審查修補

- [x] 4.1 逐項核對 1.1–1.9 對應的測試已在 `tests/test_analyze_failed_retry.py`／`tests/test_analyze_adjust.py` 中、執行後通過，再勾選 1.1–1.9（1.1–1.9 原文不動）
- [x] 4.2 `tests/test_analyze_adjust.py` 的 `_mock_claude_result` 擴充為 `_mock_claude_result(text="完成", *, is_error=False, session_id=None)`，預設值與既有行為不變，既有呼叫端不需修改
- [x] 4.3 `tests/test_analyze_failed_retry.py` 刪除自己的 `_mock_claude_result`，改為 `from AgentLoop.tests.test_analyze_adjust import _mock_claude_result`（比照 `tests/test_review_suggestions.py` 匯入 `test_node_guards` helper 的先例）
- [x] 4.4 `tests/test_analyze_failed_retry.py` 的 `_base_state` 改為薄包裝：呼叫匯入的 `test_analyze_adjust._base_state`，覆寫本檔預設值（`analysis=""`、`plan=[]`、`session_node=""`、`session_id=""`、`planned=False`、`replan_failed=False`），再套用呼叫端的 overrides；各測試的斷言與 Scenario 標題原字串不變；同步修正檔頭 docstring 說明 helper 來源
- [x] 4.5 執行 `pytest AgentLoop/tests/ -v` 全數通過
