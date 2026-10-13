# Design: 階段詳情的使用者可讀輸出保留換行並在畫面寬度內折行

## Technical Approach

### 1. 共用 utility：`output-text`

在 `web/frontend/src/style.css` 中，緊接既有的 `@utility btn-secondary` 之後新增：

```css
@utility output-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  min-width: 0;
}
```

- `white-space: pre-wrap`：保留原文的換行、連續空行與行首縮排，同時允許在空白處自動折行。
- `overflow-wrap: anywhere`：一段沒有空白的長字串（路徑、網址）比容器寬時，在字串中間強制折行；這個屬性也會計入 min-content 寬度，flex 子項目因此不會被長字串撐寬。
- `min-width: 0`：讓這個元素在 flex 容器（`StageDetail` 根節點是 `flex flex-col`、`QuestionForm` 是 `flex flex-col items-start`）裡可以縮到比內容窄，折行才會生效。

用 `@utility` 而不是在每個元素上各寫一組 Tailwind class，是為了讓「使用者可讀輸出」的呈現規則只定義一次，元件測試也能用同一個 class 名稱驗證。

### 2. `StageDetail.vue` 套用位置

以下元素都加上 `output-text`。原本有 `whitespace-pre-wrap` 的就移除，改由 utility 負責：

| 區塊         | 元素                                      | 內容                               |
| ------------ | ----------------------------------------- | ---------------------------------- |
| analyze_plan | 分析摘要 `<pre>`                          | `field('analysis')`                |
| analyze_plan | 執行計畫每個 `<li>`                       | `plan[i]`                          |
| human_confirm| 確認結果 `<p>`                            | `field('status')`                  |
| human_confirm| 修改意見 `<pre>`                          | `field('human_feedback')`          |
| execute      | 執行摘要 `<pre>`                          | `field('execution_result')`        |
| review       | 審查等級 `<p>`                            | `field('review_level')`            |
| review       | 審查報告 `<pre>`                          | `field('review_result')`           |
| 共用         | 執行日誌 `<pre class="log">`              | `detail?.log`，保留 `max-h-96 overflow-auto` |

根節點 `<div class="flex flex-col gap-3">` 加上 `min-w-0`，避免整個詳情區塊被子元素撐寬。
`（尚無資料）`、`使用者中止`、標題 `<h4>` 是固定的短文字，不套用。

### 3. `QuestionForm.vue` 套用位置

- 提示文字 `<p class="question-prompt …">{{ question.prompt }}</p>` 加上 `output-text`。這是本次唯一真正會把換行壓掉的地方：grilling 的 `result.text` 與 human_confirm 的 `confirm_prompt` 都是多行字串（見 `nodes/analyze_plan.py` `_run_with_grilling()`、`nodes/human_confirm.py`）。
- 選項按鈕（`question.kind === 'choice'` 的 `v-for="opt in question.options"`）加上 `output-text max-w-full text-left`。根節點是 `items-start`，按鈕寬度原本跟著內容走，所以要用 `max-w-full` 限制在提問區塊寬度內，`text-left` 讓折行後的多行文字靠左對齊。
- 根節點加上 `min-w-0 max-w-full`。
- 錯誤訊息（`此欄位為必填`、`externalError`）是短文字，不套用。

### 4. 不動的部分

- `ExistingSpecs.vue`、`FileBrowser.vue` 的 `<pre>` 不屬於階段詳情，本次不改（見 proposal Out of scope）。
- 後端 `web/repo_view.py` `get_stage_detail()`、`lib/claude_runner.py` `_log_event()` 不改，文字內容維持逐字相同。

## Architecture Decisions

### Decision: 純文字呈現，不轉譯 Markdown

使用者已決定維持 `ARCHITECTURE.md` 原本的「Markdown 以 `<pre>` 純文字呈現」原則：不新增 Markdown 解析與 HTML 過濾套件，避免引入 `v-html` 的 XSS 風險，也不會增加依賴。可讀性問題只靠「保留換行 + 強制折行」解決。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫**：`src/__tests__/StageDetail.spec.ts`。以既有的 `vi.mock('../api')` 模式 mock `getStageDetail` 後 mount `StageDetail`（`question` 由 props 傳入，所以會一併渲染真正的 `QuestionForm`）。斷言分兩種：(a) 輸出元素的 `textContent` 與輸入原文逐字相同，包含 `\n`；(b) 輸出元素帶有 `output-text` class。jsdom 不做版面計算，也不會載入 Tailwind 產生的 CSS，所以「實際折行」看不到。(b) 是這個 utility 的呈現契約：「保留換行 + 強制折行」的規則只在 `style.css` 的 `output-text` 定義一次，元件有套用這個 class，就代表遵守這個規則。
- **次要接縫**：`npm run build`（`vue-tsc -b && vite build`）確認 `@utility output-text` 能被 Tailwind v4 正常編譯；完成後再實際開啟網頁控制台目視確認一次（可用 `run` skill）。

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| ------------- | -------- | ------------------------ |
| 主路徑（範例一）：`question = { kind: 'choice', prompt: 'QUESTION: 這次要做到哪個程度？\n1. 純文字排版（建議）\n2. 轉譯 Markdown', options: ['1. 純文字排版（建議）', '2. 轉譯 Markdown'] }`，stage `analyze_plan` | 提示區照原文分三行；每個選項按鈕都能在區塊內折行 | `.question-prompt` 的 `element.textContent` 等於原 prompt 字串（含兩個 `\n`）且 `classes()` 含 `output-text`；每個選項按鈕 `classes()` 含 `output-text` |
| 範例二：`question = { kind: 'confirm', prompt: '## 執行計畫（共 3 個 TASK）\n\n1. a\n2. b\n3. c\n\n繼續執行？' }`，stage `human_confirm` | 空行與 `##` 照原文保留 | `.question-prompt` 的 `textContent` 逐字等於原 prompt（含 `\n\n`、`##`） |
| 範例三：stage `review`，`fields.review_result` 含 `` - `tests/unit/user/views/userManagement/userListContainer/UsersListContainer.spec.js`：新增 describe `` 與多行 `## Standards\n…` | 審查報告與審查等級、執行日誌都以使用者可讀輸出呈現 | 審查報告 `<pre>` 的 `textContent` 等於原字串、`classes()` 含 `output-text`；審查等級 `<p>`、`.log` 都含 `output-text` |
| 各階段結果欄位：stage `analyze_plan`（`analysis` + `plan` 兩項）、`human_confirm`（`status` + `human_feedback`）、`execute`（`execution_result`） | 每個結果欄位與執行計畫的每一項都以使用者可讀輸出呈現 | 對應 `<pre>`／`<p>`／每個 `<li>` 的 `classes()` 含 `output-text`（可用 `test.each` 依 stage 參數化，屬同一條規則） |

## Technical Debt & Follow-up Notes

- `ExistingSpecs.vue` 的 `.spec-content` 與 `FileBrowser.vue` 的 `.file-content` 也有長路徑撐寬的可能。不在本次範圍內；之後如需處理，可以直接改用同一個 `output-text` utility。
