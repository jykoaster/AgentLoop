# Tasks

## 1. 重跑入口標記

- [x] 1.1 在 `tests/test_workflow_entrypoints.py` 新增測試：patch `analyze_plan_node` 與 `_stream_and_save`，呼叫 `main.run_node("analyze_plan", change_name=...)`，斷言傳入 node 的 state `start_from == "analyze_plan"`，且寫出的 `state.json` 不含 `start_from`（先紅）
- [x] 1.2 修改 `main.py` 的 `run_node()`：`node_name == "analyze_plan"` 時在呼叫 node 前設 `state["start_from"] = "analyze_plan"`（綠）

## 2. 調整模式判定與提問（`nodes/analyze_plan.py`）

- [x] 2.1 移除 `tests/test_node_guards.py` 的 `test_blocks_initial_plan_when_already_planned`（「此 change 已完成初始規劃」guard 已被調整模式取代），並檢查同檔其餘以 `analysis="existing analysis"` 為前提的測試是否仍成立
- [x] 2.2 新增測試（`tests/test_node_guards.py` 或新檔 `tests/test_analyze_adjust.py`），測試本體寫入 Scenario 標題原字串「對已通過審查的任務重跑 analyze_plan 並輸入調整內容後更新同一個 change」：依 design.md 測試矩陣主路徑斷言提問參數、無分支／spec／domain 提問、prompt 含調整內容、回傳 `iteration=0` 與附加後的 task（先紅）
- [x] 2.3 實作：`is_replan` 改為 `bool(review_result) and review_blocking`；移除「已完成初始規劃」guard；新增 `_append_adjustment()`、`_ask_adjustment()`；`analysis` 非空時進入調整，取得內容後設 `human_feedback`、清除 review 欄位並走既有 human-revise 路徑；成功回傳 `task` 與 `iteration: 0`（綠）
- [x] 2.4 新增測試，本體寫入「未提供調整內容時 analyze_plan 記為錯誤且任務紀錄不變」：`ask` 拋 `KeyboardInterrupt`、以及 `is_interactive()=False` 兩種輸入，斷言 `status="error"`、`analysis` 含「未提供調整內容，無法調整規劃」、未呼叫 `call_claude`、task 不變；再實作使其通過
- [x] 2.5 新增測試，本體寫入「第二次調整以下一個編號附加且保留先前的調整」：task 已含「調整 1：…」時附加為「調整 2：…」，中間以空行分隔；再實作使其通過
- [x] 2.6 修改 `_fail()`：回傳目前的 `task`、`human_feedback`、`review_result`、`review_blocking`、`review_level`，讓失敗時附加後的 task 與調整內容寫入 `state.json`
- [x] 2.7 新增測試，本體寫入「調整被中止後重跑 analyze_plan 接回原 session 且不重複附加調整」：第一次 `call_claude` 回 is_error 並帶 session `s-1`，以回傳 state 再跑一次，斷言第二次未呼叫 `ask`、以 `resume="s-1"` 呼叫、task 無「調整 3」；再實作使其通過

## 3. 審查退回時的模式選擇

- [x] 3.1 新增測試，本體寫入「審查退回後重跑 analyze_plan 選擇輸入調整內容」：`review_blocking=True`、`start_from="analyze_plan"`、無 prior session，第一次 `ask` 為 choice 且 options 依序「依審查結果重新規劃」「輸入調整內容」，選 2 後出現調整內容題、task 最後一行為「調整 1：改用簡訊驗證碼登入」、回傳 `review_result=""`（先紅）
- [x] 3.2 新增測試，本體寫入「審查退回後重跑 analyze_plan 選擇依審查結果重新規劃」：選 1 時只問一次、prompt 為 replan 版本、task 不變；並補邊界：`start_from` 不是 `analyze_plan`（工作流內部）時不呼叫 `ask` 直接 replan
- [x] 3.3 實作 `_ask_rerun_mode()`（`interaction.ask(kind="choice")`；非互動式或中止視為依審查結果重新規劃），接進 design.md §2 的判定順序（綠）

## 4. 已封存任務

- [x] 4.1 新增測試，本體寫入「對已封存任務重跑 analyze_plan 時記為錯誤並提示改用新任務」：`tmp_path` 下建立 `openspec/changes/archive/2026-10-13-feat-login/`、不建立 `openspec/changes/feat-login/`，`start_from="analyze_plan"`，斷言 `status="error"`、`analysis` 為「此 change 已封存，請以新任務進行後續修改」、未呼叫 `ask`（先紅）
- [x] 4.2 實作 `_is_archived_change()`（比照 `web/repo_view.py` 的 `_is_archived()` 規則），在任何提問之前判定（綠）

## 5. Prompt 調整

- [x] 5.1 新增測試，本體寫入「已執行過的任務調整後執行計畫同時列出已完成項目與新增的待辦項目」：斷言調整模式送進 `call_claude` 的 prompt 含「既有 `- [x]` 項目維持原文與勾選」規則與調整內容（先紅）
- [x] 5.2 修改 `_SYSTEM_HUMAN_REVISE`：背景句改為同時適用執行前／執行後的修改意見；步驟 4 併入保留 `- [x]` 的規則，取代原句同義描述，整體字數不增加（綠）
- [x] 5.3 更新 `core/state.py` 中 `human_feedback` 的註解：人工確認退回意見或調整內容

## 6. 驗證

- [x] 6.1 執行 `pytest AgentLoop/tests/ -v`，確認全部通過
- [x] 6.2 grep 本 change spec 中每個 `#### Scenario:` 標題，確認各自出現在對應測試本體內

## 7. 文件同步

- [x] 7.1 更新 `ARCHITECTURE.md`：`analyze_plan` 模式表新增「調整」模式與判定順序（含 `is_replan` 需 `review_blocking`、重跑入口 `start_from`、已封存報錯）、`human_feedback` 欄位說明、資料流段落
- [x] 7.2 更新 `CLAUDE.md`「`analyze_plan.py` has three distinct system prompts」段落：說明調整模式重用 human-revise prompt、以 `human_feedback` 承載調整內容，以及重跑時的判定
- [x] 7.3 更新 `README.md` 安裝與使用段：說明對已規劃任務重跑 analyze_plan 會詢問調整內容（網頁重跑按鈕與 `--node analyze_plan` 皆適用），已封存任務需以新任務進行

## 8. 審查修補：保留 `- [x]` 規則移至共用禁止事項

- [x] 8.1 更新 `tests/test_analyze_adjust.py` 中本體含「已執行過的任務調整後執行計畫同時列出已完成項目與新增的待辦項目」的測試：斷言改為 prompt 含「既有 `- [x]` 維持原文」且該字串在 prompt 中只出現一次；另新增一個 replan（修補）模式的斷言，確認 `_SYSTEM_REPLAN` 送出的 prompt 也含同一規則（先紅）
- [x] 8.2 依 design.md §5 修改 `nodes/analyze_plan.py`：`_ANALYZE_PROHIBITIONS` 既有「不得將 `- [ ]` 改為 `- [x]`」條目改寫為「不得變更 `tasks.md` 任何勾選狀態……既有 `- [x]` 維持原文，所需工作以新增或改寫 `- [ ]` 呈現」；刪除 `_SYSTEM_HUMAN_REVISE` 步驟 4 句尾的同義規則，整體字數不增加（綠）

## 9. 審查修補：調整模式需為重跑入口

- [x] 9.1 在 `tests/test_analyze_adjust.py` 新增測試：`analysis` 非空、`start_from=""`、無 `human_feedback`、`review_blocking=False`，斷言 `status="error"`、`analysis` 為「此 change 已完成規劃，請以重跑 analyze_plan 進行調整」、未呼叫 `interaction.ask` 與 `call_claude`、task 不變（先紅）
- [x] 9.2 依 design.md §2 第 5、6 條修改 `analyze_plan_node`：調整分支加上 `is_rerun` 條件，其後新增非重跑入口的 `_fail()` 分支（綠）

## 10. 審查修補：共用提問樣板

- [x] 10.1 依 design.md §8 新增 `_ask_or_default()`（含 `abort_default`、`interactive_msg=None` 不列印）
- [x] 10.2 依 design.md §8 對照表，讓 `nodes/analyze_plan.py` 全部 7 個 `_ask_*`（`_ask_skip_specs()`、`_ask_new_domain_name()`、`_ask_domain_selection()`、`_ask_domain_purpose()`、`_ask_adjustment()`、`_ask_rerun_mode()`、`_ask_branch_name()`）改用它；列印文案與配色、`ask()` 參數、非互動與中止的回傳值、重問迴圈皆不變
- [x] 10.3 執行 `tests/test_interaction.py`、`tests/test_analyze_adjust.py`、`tests/test_node_guards.py`、`tests/test_state_persistence.py`，確認既有斷言不修改即全數通過；並 grep `nodes/analyze_plan.py`，確認 `_ask_or_default()` 以外已無 `_ask_*` 自行呼叫 `interaction.is_interactive()` 或捕捉 `EOFError`／`KeyboardInterrupt`

## 11. 審查修補：共用封存判斷

- [x] 11.1 在 `tests/test_openspec_runner.py` 新增 `TestIsChangeArchived`，依 design.md 測試矩陣涵蓋：日期前綴封存目錄且 active 不存在為 True、無日期前綴同名封存目錄為 True、active 仍存在為 False、archive 目錄不存在或名稱不安全為 False（先紅）
- [x] 11.2 依 design.md §7 在 `lib/openspec_runner.py` 新增 `is_change_archived(project_dir_abs, change_name)`（綠）
- [x] 11.3 `nodes/analyze_plan.py` 的 `_is_archived_change()` 改為委派給 `is_change_archived()`；確認本體含「對已封存任務重跑 analyze_plan 時記為錯誤並提示改用新任務」的測試仍通過
- [x] 11.4 在 `tests/test_web_app.py` 新增測試：`feat-login` 有 state.json、active change 資料夾存在，archive 下有 `2026-09-01-feat-login`，斷言執行中任務列表仍包含 `feat-login`（先紅）；再把 `web/repo_view.py` 的 `_is_archived()` 改為委派給 `is_change_archived()`（綠）

## 12. 審查修補：驗證與文件同步

- [x] 12.1 執行 `pytest AgentLoop/tests/ -v`，確認全部通過；再 grep 本 change spec 中每個 `#### Scenario:` 標題，確認各自仍出現在對應測試本體內
- [x] 12.2 更新 `ARCHITECTURE.md`：analyze_plan 模式表加入「非重跑入口但已規劃 → 報錯」一列並把調整列標明需 `is_rerun`；「已封存任務」段改寫為委派 `lib/openspec_runner.is_change_archived()`（含網頁任務列共用同一規則）；`_SYSTEM_HUMAN_REVISE` 列移除保留 `- [x]` 的描述，改在 `_ANALYZE_PROHIBITIONS` 說明處記載雙向勾選限制
- [x] 12.3 更新 `CLAUDE.md`「`analyze_plan.py` has three distinct system prompts」段落：調整模式只在 `start_from == "analyze_plan"` 時進入，已規劃但非重跑入口時直接報錯；封存判斷改為 `lib/openspec_runner.is_change_archived()`
