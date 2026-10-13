# Design: 新增任務的初始 analyze_plan 可從網頁中止

## Technical Approach

根因：新增任務走 `main.run()` → `_stream_and_save()`。`stages.start()` 雖然會呼叫 listener `_save_state`，但這時 `state["change_name"]` 仍為空字串，`_save_state` 會直接 return。分支名稱是在 `analyze_plan_node` 內部才決定的，而 `state.json` 要等 analyze_plan 節點回傳、`_stream_and_save` 存檔時才第一次寫出。這段期間 `/api/run` 回傳的 `change_name` 為空字串，`ActiveChanges` 只渲染 `tempRow`。`StageDetail` 以空的 `changeName` 呼叫 `getStageDetail('', 'analyze_plan')` 會失敗，`detail` 變成 `null`，`isRunning` 為 false，所以「中止」按鈕不渲染。

修改（只動前端）：

1. `ChangeRow.vue`：渲染 `StageDetail` 時多傳 `:temporary="temporary"`；也可以改傳該階段目前的狀態 `:stage-status="row.stages[selectedStage]"`，二擇一，以能讓 `StageDetail` 得知「暫時列且 analyze_plan 執行中」為準。
2. `StageDetail.vue`：
   - 新增選填 prop（例如 `temporary?: boolean`）。暫時列時跳過 `getStageDetail` 呼叫（沒有 change 名稱，不要對後端送出必然失敗的請求），`isRunning` 改用暫時列的 analyze_plan 狀態（`tempRow` 固定為 `running`）判定。
   - 「中止」按鈕的模板、class、圖示、`onAbort()`（`window.confirm('確定要中止這個階段嗎？')` → `api.postAbort()`）完全沿用，不另寫一份。暫時列時 `onAbort` 之後的 `load()` 同樣跳過。
3. 中止後，`ActiveChanges` 的 2 秒輪詢拿到 `getRun()` 為 `{ active: false }`，`tempRow` computed 變成 `null`，暫時列自然消失，`disabledReason` 清空，「新增任務」恢復可用。不需要額外程式碼。

後端（不修改、只補測試）：`RunManager.abort()` → `_mark_aborted_locked()` 在 `change_name` 無法偵測（`_detect_change_name` 找不到 `state.json`）時直接 return；`_finalize_locked()` 在沒有 `change_name` 時略過切分日誌，只關閉 log、刪除執行目錄。process group 一樣以 SIGTERM／SIGKILL 結束。

## Architecture Decisions

### Decision: 只補暫時列的中止入口，不提早寫出執行狀態紀錄

使用者決定只讓暫時列能中止，不在分支名稱決定後提早寫出 `state.json`。代價是：中止暫時列不會留下「使用者中止」註記，也不會保存 Claude session（`session.json` 會隨執行目錄一起刪除）；之後要重新規劃，只能重新新增任務。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫**：`ActiveChanges` 元件（`web/frontend/src/__tests__/ActiveChanges.spec.ts`），以 `vi.mock('../api')` 模擬 `getChanges`／`getRun`／`postAbort`，`vi.spyOn(window, 'confirm')`。從使用者視角操作：展開暫時列 → 點 analyze_plan 卡片 → 按中止 → 斷言 confirm 文案、`postAbort` 被呼叫；把 `getRun` 改回閒置、推進輪詢後，暫時列消失、新增任務按鈕可用。
- **次要接縫**：`RunManager`（`tests/test_web_runner.py`），以假子行程 `start_new_task()`，不建立任何 `state.json`，呼叫 `abort()`：斷言 10 秒內結束、`status()["active"] is False`、`<target>/.agentloop/changes/` 底下沒有產生任何 change 紀錄。

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| 主路徑：新增任務「新增登入頁」後 `getRun` 回傳 `active: true, change_name: ''`，展開暫時列、點 analyze_plan 卡片 | analyze_plan 詳情底部顯示「中止」按鈕 | 暫時列內存在文字為「中止」、帶 stop 圖示的按鈕 |
| 承上，按「中止」，confirm 回傳 true | 呼叫中止 API | `window.confirm` 以「確定要中止這個階段嗎？」被呼叫；`postAbort` 被呼叫 1 次 |
| 承上，之後 `getRun` 回傳 `{ active: false }`、`getChanges` 為空，推進輪詢 | 暫時列消失，新增任務入口可用 | `[data-change-name="(temp)"]` 不存在；新增任務按鈕未停用 |
| 按「中止」但 confirm 回傳 false | 不中止 | `postAbort` 未被呼叫 |
| 暫時列展開 analyze_plan 詳情 | 不向後端查詢階段詳情 | `getStageDetail` 未以空 change 名稱被呼叫 |
| 後端：`start_new_task` 的假子行程持續執行、無 `state.json`，呼叫 `abort()` | 10 秒內結束，沒有留下紀錄 | 耗時 < 10s；`status()["active"] is False`；changes 目錄下無 `state.json` |

## Technical Debt & Follow-up Notes

- 暫時列中止後，analyze_plan 可能已經建立 git 分支、執行過 `openspec init`，或寫出一部分 openspec change 資料夾，但因為沒有 `state.json`，列表不會顯示該任務，也無法重跑。若要能保留紀錄、讓重跑接回 session，需要另開 change，在分支名稱決定後提早寫出執行狀態紀錄。
- 現行 spec「新增任務」寫明「分支名稱決定後，該列標題改為 change 名稱」，但實際上要等 analyze_plan 結束才會改。這與上一點同屬「狀態紀錄寫出太晚」的問題，本次不處理。
- 暫時列 analyze_plan 詳情的執行日誌目前也看不到（同樣因為沒有 change 名稱），本次不處理。
