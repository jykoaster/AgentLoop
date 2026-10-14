# Proposal: 起點分支提問在網頁上列出現有分支

## Intent

規範目的：初始規劃時，工作分支在目標專案本地不存在，系統會問「要從哪個分支建立 <工作分支>？」。網頁介面要把這一題呈現成可點選的分支清單，讓使用者不用記分支名稱或編號，直接點一個現有本地分支當起點分支。

規範背景：`feat-new-change-source-branch` 已讓 `_ask_base_branch()` 組出「編號. 分支名稱」選項，終端機也會印出清單。不過這一題以 `kind="text"` 提問，網頁的提問表單（`QuestionForm.vue`）只有 `kind="choice"` 會把 `options` 畫成按鈕，`text` 只畫一個空白輸入框。結果網頁上看不到任何分支，使用者只能盲打編號。

輸出要求：網頁上這一題 MUST 對每個本地分支各顯示一顆按鈕，文字為「編號. 分支名稱」，依分支名稱字母排序、編號從 1 起連續遞增，目前分支加註「（目前分支）」；按鈕下方保留自訂答案輸入框與送出鈕。點按鈕送出的答案是該選項的編號。終端機的提示與清單輸出不變。既有 `openspec/specs/analyze-plan/spec.md`「工作分支不存在時讓使用者選擇起點分支」已規範上述行為，本次只修正網頁上未依規格呈現的部分，所以不改 spec（`skip_specs: true`）。

範例及解釋：目標專案本地有 `develop`（目前分支）與 `main`，使用者在網頁新建任務、工作分支輸入 `feat/login`（本地不存在）→ 系統以選項題提問，選項為 `1. develop（目前分支）`、`2. main` → 網頁顯示這兩顆按鈕與自訂輸入框 → 使用者點「2. main」→ 前端送出答案 `2` → 系統以 `main` 為起點分支，同步後建立並切換到 `feat/login`。若使用者不點按鈕、在自訂輸入框留空直接送出，答案為空字串，系統以目前分支 `develop` 為起點（detached HEAD 時重問）；自訂輸入非清單內編號時提示後重問，與現行規則相同。

## Scope

In scope:

- `nodes/analyze_plan.py` 的 `_ask_base_branch()` 提問改為 `kind="choice"`（`options` 照舊傳入），答案解析、空白採目前分支、無效編號重問、中止與非互動式環境的處理都不變
- 更新 `tests/test_analyze_plan_base_branch.py`，斷言起點分支提問以選項題送出
- 同步 `ARCHITECTURE.md` 的 analyze_plan 起點分支段落，寫明以選項題（`kind="choice"`）提問

Out of scope:

- 網頁前端 `QuestionForm.vue` 的呈現方式（不讓文字題也顯示選項）
- 分支名稱提問、其他提問點的 kind
- 遠端分支列入選項

## Approach

只改後端提問種類：`_ask_or_default(..., kind="choice", options=options)`。網頁的選項題已經會把每個選項畫成按鈕，點按鈕時用 `parseOptionAnswer()` 送出開頭的編號；自訂輸入框送出的空字串不受 `required` 擋（這一題沒有 `required`），所以會落入既有「空白採目前分支」分支。終端機模式下 `interaction.ask()` 不使用 `kind`，行為完全不變。
