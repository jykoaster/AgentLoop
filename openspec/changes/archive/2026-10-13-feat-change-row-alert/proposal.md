# Proposal: 任務列待回覆提問警示光暈

## Intent

規範目的：階段卡片在工作流等待使用者回覆時會顯示驚嘆號，但任務列收合後卡片被隱藏，使用者就看不到有提問在等待，工作流因此卡住。本改動讓「有待回覆提問的任務列」本身在外框持續閃爍警示色呼吸光暈，不論收合或展開都看得到，使用者一眼就能找到需要回覆的任務並展開回覆。

輸出要求（本 change 依使用者決定 `skip_specs: true`，不寫 specs delta，輸出要求記錄於此並由測試鎖定）：

- 判定條件：目前有執行進行中、該執行有待回覆提問、且該執行所屬的 change 名稱與任務列的 change 名稱相同；三者都成立時該任務列為「有待回覆提問」。
- 呈現：有待回覆提問的任務列外框 MUST 持續顯示黃色（警示色，與驚嘆號同色 `--color-warning`）呼吸光暈，週期與既有藍色「執行中」卡片光暈一致（2 秒）；任務列收合與展開兩種狀態都顯示。
- 只有一列會帶光暈：其他任務列不帶光暈（同時最多一個執行）。
- 消失時機：回覆送出、下一次狀態更新（每 2 秒）取得的執行不再帶待回覆提問後，光暈消失。
- 階段卡片的驚嘆號行為維持原樣，兩者同時存在。
- 使用者系統設定減少動態效果時，光暈不做動畫（與既有呼吸光暈同一作法）。

範例及解釋：

1. `feat-login` 任務列處於收合狀態（只見標題），analyze_plan 執行中。
2. Agent 輸出 grilling 提問「網頁服務要用什麼技術棧？」→ 系統登記為 `feat-login` 的 analyze_plan 待回覆提問。
3. 下一次 2 秒輪詢後，`feat-login` 任務列外框開始以黃色呼吸光暈閃爍；同頁的 `fix-css` 任務列沒有光暈。
4. 使用者點「展開」→ 五張階段卡片出現，analyze_plan 卡片顯示驚嘆號，任務列外框光暈仍持續。
5. 使用者點 analyze_plan 卡片並按選項 1 送出 → 下一次輪詢取得的執行已無待回覆提問 → 光暈與驚嘆號一起消失。

## Scope

In scope:

- 任務列依「有待回覆提問」判定加上 / 移除黃色呼吸光暈（收合、展開都生效）
- 新增警示色呼吸光暈動畫樣式
- 對應前端測試
- `CONTEXT.md` 的「待回覆提問」詞彙補上任務列光暈的標示方式

Out of scope:

- 階段卡片驚嘆號的既有行為與樣式
- 有提問時自動展開任務列、瀏覽器通知、音效等其他提醒方式
- 後端 API 與工作流節點

## Approach

- `web/frontend/src/style.css` 的 `@theme` 內，比照既有 `--animate-breathe` / `@keyframes breathe`，新增 `--animate-breathe-warning`（`breathe-warning 2s ease-in-out infinite`）與 `@keyframes breathe-warning`，`box-shadow` 改用 `var(--color-warning)`。
- `web/frontend/src/components/active-changes/ChangeRow.vue`：新增 computed（例如 `hasPendingQuestion`），條件為 `runStatus.active && runStatus.question` 且 `(runStatus.change_name || '') === (row.change_name || '')`；可與既有 `hasQuestion(stage)` 共用判斷（`hasQuestion` 改為 `hasPendingQuestion.value && question.stage === stage`）。在根元素 `.change-row` 上以 `:class` 綁定 `{ 'animate-breathe-warning motion-reduce:animate-none': hasPendingQuestion }`。光暈放在根元素、位於 `v-if="!collapsed"` 區塊之外，收合時仍顯示。
- 資料來源沿用 `ActiveChanges.vue` 既有每 2 秒輪詢的 `getRun()` 結果，不新增 API。
