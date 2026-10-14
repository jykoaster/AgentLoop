# Design: review 修改建議改為多選後一次送出

## Technical Approach

- `lib/interaction.py`：`Kind` 擴充為 `Literal["text", "choice", "multi_choice", "confirm", "pause"]`。命令列模式 `_ask_cli` 對 `multi_choice` 與 `choice` 行為相同（讀一行文字），網頁模式照常寫 `question.json`（`kind: "multi_choice"`、`options` 為帶編號的建議清單、`required: false`）。
- `nodes/review.py`：詢問修改建議的 `interaction.ask(...)` 改傳 `kind="multi_choice"`；提示文字依 `interaction.is_web_mode()` 分流——網頁模式傳「請勾選要修改的建議後按送出（未勾選＝不修改）」，命令列模式維持原字串「請輸入要修改的建議編號（例如 1,3；all=全部；留空＝不修改）」一字不改（兩段文字宜定義為模組層級常數，供測試比對）；`_parse_suggestion_selection()`、非互動式預設不修改、`review_result` 附加「人工確認：選定修改的建議事項」小節皆不變。
- `web/frontend/src/api.ts`：`QuestionKind` 加入 `'multi_choice'`。
- `web/frontend/src/components/active-changes/QuestionForm.vue`：
  - 新增 `v-else-if="question.kind === 'multi_choice'"` 區塊：每個 option 一個 checkbox（label 為 option 原文，沿用 `output-text` 折行樣式）、一個「全選」checkbox、一個「送出」按鈕（paper-plane 圖示，與其他送出按鈕同樣式）；不放自訂答案輸入框。
  - 勾選狀態以已勾選的編號集合保存；編號沿用 `parseOptionAnswer()` 從「1. xxx」取出的數字。
  - 「全選」：全部已勾選時呈勾選狀態；點擊時若未全選則全部勾選，已全選則全部取消。
  - 送出：已勾選編號以數字遞增排序、以半形逗號 `,` 串接（無空白）後 `emit('submit', ...)`；未勾選時送出空字串 `''`。
  - `question.id` 變更時清空勾選集合（併入既有 watch）。
- `web/runner.py`：answer 寫入只檢查 `required`，多選題 `required=false`，空字串可送出，不需改動。
- `ARCHITECTURE.md`：review 節點「嚴重程度分流」段補上網頁以多選題（勾選後送出）回覆；互動埠段的提問種類列表加入多選題。

## Architecture Decisions

### Decision: 以新的提問種類 `multi_choice` 表達多選，而非在 `choice` 上加旗標

單選題（grilling）與多選題的回覆控制項、送出時機完全不同（點選即送 vs. 勾選後按送出、有無自訂答案框），以獨立 kind 分流讓 `QuestionForm.vue` 的模板分支清楚，也不影響既有 `choice` 的測試與行為。回答格式仍是純文字（與終端機相同的編號字串），因此互動埠的檔案協定與 `web/runner.py` 不需改動。

### Decision: 修改建議提示文字依通道分流，而非統一中性措辭

同一個 `question.prompt` 會原樣顯示在網頁詳情上，但網頁端只有勾選框與送出按鈕，無法「輸入」也打不出「all」。改用中性措辭會讓終端機失去「1,3」「all」的輸入格式說明，違反「命令列行為維持不變」；因此在 review 節點依 `interaction.is_web_mode()` 選擇提示文字，互動埠本身不需知道文案差異。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫**：前端 `StageDetail`（含 `QuestionForm`）元件測試（vitest + @vue/test-utils，mock `api.postAnswer`），從勾選／全選／送出的使用者操作斷言送出的回答字串。
- **次要接縫**：後端 `review_node()`（pytest，沿用 `tests/test_node_guards.py` 的 patch 手法：patch `REPO_ROOT`、`ensure_on_branch`、`build_skills_block`、`call_claude` 回傳含 `SUGGESTION n:` 的報告，並 patch `interaction.is_interactive`／`interaction.is_web_mode`／`interaction.ask`），斷言提示文字依通道分流、提問種類為 `multi_choice`、選項為帶編號建議清單，以及依回答產生的 `review_blocking`／`review_level`／`review_result`。

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| review 報告含 3 條建議，網頁模式 | 待回覆提問種類為多選題，選項為「1. …」「2. …」「3. …」 | `interaction.ask` 的 `kind == "multi_choice"`、`options` |
| 多選題 3 個選項，勾選 3 與 1 後按送出 | 送出「1,3」 | `postAnswer` 參數 `'1,3'` |
| review 收到「1,3」 | `review_blocking=True`、`review_level="修補"`，`review_result` 末尾只列 SUGGESTION 1 與 3 | 回傳 dict |
| 多選題未勾選任何項目直接送出 | 送出空字串；review 收到空字串後通過 | `postAnswer` 參數 `''`；`review_blocking=False` |
| 點「全選」後送出 | 全部勾選，送出「1,2,3」 | checkbox checked、`postAnswer('1,2,3')` |
| 全選狀態再點「全選」 | 全部取消勾選 | checkbox 皆未勾選 |
| 網頁模式下 review 詢問修改建議 | 提示文字為「請勾選要修改的建議後按送出（未勾選＝不修改）」，不含「輸入」「all」 | `interaction.ask` 第一個參數（`is_web_mode=True`） |
| 命令列模式下 review 詢問修改建議 | 提示文字為「請輸入要修改的建議編號（例如 1,3；all=全部；留空＝不修改）」 | `interaction.ask` 第一個參數（`is_web_mode=False`） |
| 多選題未勾選直接送出（後端） | 同樣以 `kind="multi_choice"` 詢問，回答空字串後通過 | `interaction.ask` kwargs `kind`；`review_blocking=False` |
| 多選題介面組成 | 每選項一個勾選框、一個全選、一個送出按鈕、無自訂答案輸入框 | DOM 查詢 |

## Technical Debt & Follow-up Notes

無
