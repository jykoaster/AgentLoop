# Design: analyze_plan 失敗後重跑時重新執行原本的規劃

## Technical Approach

根因一（初始規劃）：`nodes/analyze_plan.py` 的 `_fail()` 回傳 `"analysis": <錯誤訊息>`（供階段詳情顯示錯誤），而 `analyze_plan_node` 以 `analysis_state = state.get("analysis")` 非空判定「已完成規劃」（ARCHITECTURE 模式表順序 4／5），所以初始規劃失敗後重跑會命中順序 4 調整。

根因二（依審查結果重新規劃）：`_fail()` 保留 `review_result`／`review_blocking`，重跑時 `is_replan` 為真，但順序 3 只要 `is_rerun and not prior_session` 就呼叫 `_ask_rerun_mode()`，無法分辨「重新規劃失敗」與「達 `MAX_ITERATIONS` 後 `route_after_review` 回傳 end」，因此 Claude 失敗但沒有 session id、validate／rollback／讀不到規格文件等失敗後重跑都會跳出選擇題。

依人工意見調整／調整：`_fail()` 帶出 `human_feedback` 與已附加的 `task`，重跑命中順序 2，既有行為已正確，本次只以測試鎖住。

修改：

1. `core/state.py`：`AgentState` 新增 `planned: bool`（analyze_plan 至少成功完成過一次規劃；只由 analyze_plan 成功路徑寫入）與 `replan_failed: bool`（最近一次 analyze_plan 在依審查結果重新規劃途中失敗）。
2. `main.py` 建立初始 state 時加入 `"planned": False`、`"replan_failed": False`。
3. `nodes/analyze_plan.py`：
   - 新增 `_is_planned(state, project_dir, change_name) -> bool`：`state["planned"]` 為 bool 時直接回傳；缺欄位（舊 `state.json`）時回傳 `bool(state.get("plan"))` 或 `openspec/changes/<change>/tasks.md` 存在。
   - 模式判斷中以 `planned = _is_planned(...)` 取代 `analysis_state`（`elif is_rerun and not is_human_revise and planned` → 調整；`elif not is_human_revise and planned` → 報錯）。`analysis_state` 變數若無其他用途則刪除。
   - `_fail()` 回傳中加入 `"planned": planned`（帶出目前值，不重設）；成功回傳 `"planned": True`。
   - 讀入 `replan_failed = state.get("replan_failed") is True`（缺欄位視為 `False`，維持舊行為）。順序 3 改為 `if is_rerun and not prior_session and not replan_failed and _ask_rerun_mode() == "adjust"`。
   - `_fail()` 回傳 `"replan_failed": replan_failed`，其中區域變數 `replan_failed` 在模式判斷確定 `is_replan` 為真（未降級成調整）時設為 `True`；模式判斷前的 guard（已封存、`review_result` 為空）失敗時帶出讀入值。選了「輸入調整內容」降級成調整時設為 `False`（之後失敗由 `human_feedback` 命中順序 2）。成功回傳 `"replan_failed": False`。
   - 重新規劃等級為「重寫」時，重跑會再執行一次 `rollback_except_openspec()`；`openspec/` 以外的變更上次已 rollback，重跑再 rollback 結果相同，不需特別處理。
   - `_fail()` 維持把錯誤訊息寫進 `analysis`，階段詳情顯示不變。
4. 初始規劃重跑時：`branch_name`／`project_dir`／`change_name` 已由上次 `_fail()` 存進 state，不會重問分支；`_recover_skip_specs`、`_recover_domains` 沿用已回答的決定；`take_session` 取得中斷 session 時 `call_resuming` 接回——皆為既有行為，不需修改，只需測試鎖住。上次失敗若發生在分支尚未建立、或 spec／domain 尚未回答之前，未回答的問題照常詢問。
5. `ARCHITECTURE.md`：模式判斷表順序 4／5 的觸發條件由「`analysis` 非空」改為「已完成過規劃（`planned`）」，並說明 `_fail()` 會把錯誤訊息寫進 `analysis`、因此不能拿它判定；順序 3 選擇題說明補「`replan_failed` 為真時不提問，直接重新規劃」；`AgentState` 欄位說明補 `planned`、`replan_failed`。

## Architecture Decisions

### Decision: 以獨立的 `planned` 欄位判定「已完成過規劃」

替代方案：(a) 改讓 `_fail()` 不覆寫 `analysis`——階段詳情會失去錯誤訊息；(b) 以 change 資料夾下有沒有 `tasks.md` 判定——初始規劃中途撞用量上限時 Claude 可能已寫出部分檔案，仍會誤判成調整；(c) 讓 `_fail()` 保留舊 `plan` 並以 `plan` 非空判定——會改變失敗時階段詳情顯示的執行計畫。選擇新增欄位，語意明確且不影響顯示；(b)(c) 只作為舊 `state.json` 缺欄位時的推定。

### Decision: 以 `replan_failed` 欄位決定重新規劃失敗後重跑是否略過選擇題

替代方案：(a) 讀 `stages["analyze_plan"] == "error"`——`_tracked()`／`start()` 在呼叫 node 前已把階段改成 running，node 讀不到上次結果，且 `stages` 依規定只由 `core/stages.py` 寫入；(b) 一律略過選擇題——會拿掉達重試上限結束後讓使用者改走調整的能力。選擇由 analyze_plan 自己記錄失敗當下的模式。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫**：`analyze_plan_node(state)`，沿用 `tests/test_analyze_adjust.py` 的 patch 方式（`call_claude`／`ensure_on_branch`／`branch_exists`／`ensure_initialized`／`ensure_change_created`／`_run_with_validate`／`_read_change_artifacts`／`interaction.ask`／`interaction.is_interactive`），斷言 `interaction.ask` 的提問內容、送進 Claude 的 prompt 屬於初始規劃還是調整、回傳的 `status`／`planned`／`task`。
- **次要接縫**：無。

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| 主路徑：`planned=False`、`analysis="Claude 執行失敗：..."`、`plan=[]`、分支 `feat/login`、`skip_specs=False`、`domains=["auth"]`、`start_from="analyze_plan"`，Claude 成功 | 走初始規劃；不問調整內容、分支、spec、domain；成功後 `planned=True`、`status="pending"`、`task` 不含「調整 1：」 | Target：prompt 含初始規劃 `_SYSTEM`；Reject：`interaction.ask` 未以「請輸入本次要調整的內容」呼叫 |
| 初始規劃撞用量上限留下 session（`session_node="analyze_plan"`、`session_id="s1"`、`planned=False`）後重跑 | 接回 `s1`；不問調整、spec、domain | Target：Claude 以 `resume="s1"` 呼叫；Reject：沒有任何提問 |
| `planned=True`、上次調整因未提供調整內容而失敗（`analysis` 為錯誤訊息、`plan=[]`）後重跑 | 仍詢問「請輸入本次要調整的內容」 | Target：`interaction.ask` 第一個提問為調整內容 |
| 上次初始規劃失敗後再失敗 | `status="error"`、`planned=False` | Target：回傳 `planned is False` |
| 舊 state 無 `planned`、`plan` 非空 | 視為已完成規劃→調整 | Target：詢問調整內容 |
| 舊 state 無 `planned`、`plan=[]`、change 資料夾無 `tasks.md` | 視為未完成規劃→初始規劃 | Reject：未詢問調整內容 |
| 主路徑：`review_blocking=True`、`review_result` 非空、`review_level="修補"`、`replan_failed=True`、無 session、`start_from="analyze_plan"`，Claude 成功 | 直接重新規劃；無任何提問；成功後 `replan_failed=False`、`task` 不變 | Target：prompt 為重新規劃 `_SYSTEM`；Reject：`interaction.ask` 未被呼叫（無選擇題） |
| `review_blocking=True`、`review_result` 非空、`replan_failed=False`（達重試上限結束）、重跑 | 仍出現規劃方式選擇題 | Target：第一個提問為「此任務有尚未處理的審查退回，要如何重新規劃？」 |
| 依審查結果重新規劃時 Claude 失敗（無 session） | `status="error"`、`replan_failed=True`、`review_blocking` 維持 True | Target：回傳 `replan_failed is True` |
| 選擇題選「輸入調整內容」、輸入內容後 Claude 失敗 | `replan_failed=False`、`human_feedback` 為輸入內容 | Target：回傳 `replan_failed is False` |
| `human_feedback="密碼至少 12 碼"`、`planned=True`、上次依人工意見調整失敗後重跑 | 直接依人工意見調整，無提問、`task` 不變 | Target：prompt 含「密碼至少 12 碼」；Reject：`interaction.ask` 未被呼叫 |

## Technical Debt & Follow-up Notes

舊 `state.json`（無 `planned`）且初始規劃失敗時已寫出 `tasks.md` 的任務，仍會被推定為已完成規劃而進入調整；只影響本次改版前就已失敗的任務，成功跑過一次 analyze_plan 後即寫入正確的 `planned`。同理，本次改版前就已在重新規劃途中失敗的任務沒有 `replan_failed`，重跑時仍會出現選擇題（選「依審查結果重新規劃」即可）。
