# Tasks

## 1. 前端：暫時列 analyze_plan 詳情提供中止

- [x] 1.1 在 `web/frontend/src/__tests__/ActiveChanges.spec.ts` 新增測試，測試本體寫入 Scenario 標題原字串「新增任務的暫時列在 analyze_plan 執行中可中止並結束執行」：模擬 `getRun` 為 `active: true, change_name: ''`，展開暫時列、點 analyze_plan 卡片，斷言有「中止」按鈕；按下後 `window.confirm` 以「確定要中止這個階段嗎？」被呼叫、`postAbort` 被呼叫；把 `getRun` 改為閒置並推進輪詢後，暫時列消失、新增任務按鈕可用（先紅）
- [x] 1.2 修改 `ChangeRow.vue`，把暫時列資訊傳給 `StageDetail`；修改 `StageDetail.vue`，讓暫時列跳過 `getStageDetail`、以暫時列的 analyze_plan 執行中狀態顯示既有的「中止」按鈕，沿用同一個 `onAbort`（綠）
- [x] 1.3 補測試：暫時列按「中止」但 confirm 取消時不呼叫 `postAbort`；暫時列展開詳情時不會以空 change 名稱呼叫 `getStageDetail`
- [x] 1.4 執行 `cd AgentLoop/web/frontend && npx vitest run` 與 `npm run build`，確認全部通過

## 2. 後端：固定住暫時列中止的行為

- [x] 2.1 在 `tests/test_web_runner.py` 新增測試，測試本體寫入 Scenario 標題原字串「新增任務的暫時列在 analyze_plan 執行中可中止並結束執行」：以假子行程呼叫 `start_new_task()`，不建立 `state.json`，呼叫 `abort()`，斷言耗時 < 10 秒、`status()["active"] is False`、目標專案 `.agentloop/changes/` 底下沒有任何 `state.json`
- [x] 2.2 若 2.1 失敗才修改 `web/runner.py`；執行 `pytest AgentLoop/tests/ -v`，確認全部通過

## 3. 文件同步

- [x] 3.1 更新 `ARCHITECTURE.md`「前端：`web/frontend/`」段落：說明暫時列的 `StageDetail` 不查詢階段詳情，改以暫時列狀態顯示「中止」按鈕；並在「執行管理：`web/runner.py`」的中止說明補一句：沒有 change 名稱或 `state.json` 時只結束執行、清理執行目錄，不回寫狀態
