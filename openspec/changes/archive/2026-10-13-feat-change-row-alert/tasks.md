# Tasks

## 1. 測試先行（tdd 紅燈）

- [x] 1.1 於 `web/frontend/src/__tests__/ActiveChanges.spec.ts` 新增測試 `有待回覆提問的任務列外框顯示警示光暈且收合展開皆可見並於回覆後消失`：兩列（`feat-login`、`fix-css`），`getRun` 回傳 `feat-login` 的 analyze_plan 待回覆提問；斷言 `feat-login` 的 `.change-row` 於收合狀態帶 `animate-breathe-warning` class、`fix-css` 不帶；點「展開」後仍帶且 analyze_plan 卡片有 `.question-mark`；把 `getRun` 改為無提問並推進 2 秒輪詢（fake timers）後，class 與驚嘆號都消失。另以 `getRun` 為 `active: true` 但 `change_name` 為其他任務的情況斷言 `feat-login` 不帶光暈。先確認測試失敗
- [x] 1.2 注意：`ChangeRow.vue` 目前 `collapsed` 預設為 `true`，既有測試多直接找 `.stage-card`；撰寫新測試前先執行一次 `npx vitest run` 確認既有測試基準狀態，新測試須明確操作收合／展開按鈕，不依賴預設值

## 2. 實作

- [x] 2.1 `web/frontend/src/style.css` 新增 `--animate-breathe-warning` 與 `@keyframes breathe-warning`（2 秒、`box-shadow` 使用 `--color-warning`），比照既有 `breathe`
- [x] 2.2 `web/frontend/src/components/active-changes/ChangeRow.vue` 新增「此任務列有待回覆提問」的 computed，並讓 `hasQuestion(stage)` 共用它；在根元素 `.change-row` 綁定 `animate-breathe-warning motion-reduce:animate-none`
- [x] 2.3 執行 `cd AgentLoop/web/frontend && npx vitest run` 確認 1.1 轉綠且既有測試無退步，再執行 `npm run build` 確認型別檢查與建置通過

## 3. 文件

- [x] 3.1 確認 `CONTEXT.md` 的「待回覆提問」詞彙已含「所屬任務列外框以警示色呼吸光暈標示」（analyze 階段已更新，若被改動則補回）
