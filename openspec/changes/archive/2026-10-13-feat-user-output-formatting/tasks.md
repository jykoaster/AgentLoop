# Tasks

## 1. 共用呈現規則

- [x] 1.1 在 `web/frontend/src/style.css` 既有的 `@utility btn-secondary` 之後新增 `@utility output-text`（`white-space: pre-wrap; overflow-wrap: anywhere; min-width: 0;`），內容見 `design.md` Technical Approach §1

## 2. 待回覆提問的提示與選項（tdd 紅→綠）

- [x] 2.1 （紅）在 `web/frontend/src/__tests__/StageDetail.spec.ts` 新增測試 `待回覆提問的提示文字照原文換行顯示且選項可在區塊內折行`：以 `design.md` 測試矩陣的範例一（choice 題）mount `StageDetail`，斷言 `.question-prompt` 的 `element.textContent` 逐字等於原 prompt（含 `\n`），且帶有 `output-text` class；每個選項按鈕都帶有 `output-text` class。同一個測試內再以範例二（confirm 題，含 `\n\n` 與 `##`）重新 mount，斷言 `textContent` 逐字相同
- [x] 2.2 （綠）`web/frontend/src/components/active-changes/QuestionForm.vue`：`.question-prompt` 加上 `output-text`；choice 選項按鈕加上 `output-text max-w-full text-left`；根節點加上 `min-w-0 max-w-full`（見 `design.md` §3），讓 2.1 轉綠

## 3. 階段結果欄位與執行日誌（tdd 紅→綠）

- [x] 3.1 （紅）在 `StageDetail.spec.ts` 新增測試 `各階段結果欄位、執行計畫與執行日誌以使用者可讀輸出呈現`：用 `test.each` 依 stage 參數化（analyze_plan／human_confirm／execute／review，資料見 `design.md` 測試矩陣範例三與「各階段結果欄位」列），斷言每個結果欄位元素（`<pre>`／`<p>`）、執行計畫每個 `<li>`、`.log` 都帶有 `output-text` class；review 的審查報告 `<pre>` 另外斷言 `textContent` 逐字等於含長路徑的原字串
- [x] 3.2 （綠）`web/frontend/src/components/active-changes/StageDetail.vue`：依 `design.md` §2 對照表為各元素加上 `output-text`，並移除被取代的 `whitespace-pre-wrap`（`.log` 保留 `max-h-96 overflow-auto`）；根節點加上 `min-w-0`，讓 3.1 轉綠
- [x] 3.3 確認既有 `StageDetail.spec.ts` 四個測試（`點擊卡片後顯示該階段的執行結果與執行日誌`、`被使用者中止的階段在詳情顯示使用者中止`、`必填文字題送出空白時不送出並提示必填`、`提問已被回覆後再送出回覆時顯示提問已結束`）仍通過，不修改其斷言

## 4. 驗證

- [x] 4.1 在 `web/frontend/` 執行 `npx vitest run`，全部通過（`StageDetail.spec.ts` 全數通過；`ActiveChanges.spec.ts` 既有 12 個測試失敗與本次改動無關，修改前後結果相同，已核對）
- [x] 4.2 在 `web/frontend/` 執行 `npm run build`，確認 `vue-tsc` 與 Tailwind v4 能正常編譯 `@utility output-text`

## 5. 文件同步

- [x] 5.1 更新 `ARCHITECTURE.md`「前端：`web/frontend/`」段落：在「Markdown 以 `<pre>` 純文字呈現」之後補一句，說明階段詳情與待回覆提問的使用者可讀輸出統一使用 `style.css` 的 `output-text` utility，保留原文換行，長字串強制折行
