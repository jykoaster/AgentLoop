# Tasks

## 1. 互動埠與 review 節點

- [x] 1.1 以 tdd 紅-綠循環新增 pytest（建議新檔 `tests/test_review_suggestions.py`，沿用 `tests/test_node_guards.py` 的 patch 手法）：review 報告含多條 `SUGGESTION n:` 時，`interaction.ask` 以 `kind="multi_choice"`、帶編號選項被呼叫；回答「1,3」時回傳 `review_blocking=True`、`review_level="修補"`、`review_result` 末尾只列建議 1 與 3；回答空字串時 `review_blocking=False`。測試本體分別寫入 Scenario 標題原字串「勾選多條建議後按送出只針對勾選的建議重新規劃」「未勾選任何建議就送出時視為不修改並直接通過」
- [x] 1.2 `lib/interaction.py` 的 `Kind` 加入 `"multi_choice"`（命令列模式行為與 `choice` 相同）
- [x] 1.3 `nodes/review.py` 詢問修改建議時改用 `kind="multi_choice"`，其餘解析與回傳不變；確認 `pytest AgentLoop/tests/ -v` 全數通過

## 2. 網頁前端多選題

- [x] 2.1 以 tdd 紅-綠循環在 `web/frontend/src/__tests__/StageDetail.spec.ts` 新增測試：多選題介面組成（每選項一個勾選框、全選、送出、無自訂文字輸入框），測試本體寫入「多選題在詳情中以勾選框與送出按鈕呈現」
- [x] 2.2 新增測試：依序勾選第 3、第 1 條後，送出前 `postAnswer` 未被呼叫，送出後以「1,3」呼叫；測試本體寫入「勾選多條建議後按送出只針對勾選的建議重新規劃」
- [x] 2.3 新增測試：未勾選直接送出時以空字串呼叫 `postAnswer`；測試本體寫入「未勾選任何建議就送出時視為不修改並直接通過」
- [x] 2.4 新增測試：點「全選」後全部勾選並送出「1,2,3」，再點一次全部取消；測試本體寫入「點擊全選切換時勾選或取消全部建議」
- [x] 2.5 `web/frontend/src/api.ts` 的 `QuestionKind` 加入 `'multi_choice'`
- [x] 2.6 `QuestionForm.vue` 新增 `multi_choice` 區塊（勾選框清單、全選切換、送出按鈕；送出時編號遞增以半形逗號串接、未勾選送空字串；`question.id` 變更時清空勾選），確認 `npx vitest run` 全數通過

## 3. 文件同步

- [x] 3.1 更新 `ARCHITECTURE.md`：review 節點「嚴重程度分流」段說明網頁以多選題（勾選後按送出，未勾選＝不修改）回覆修改建議；互動埠段的提問種類加入多選題

## 4. 修改建議提示文字依通道分流（審查修補）

- [x] 4.1 以 tdd 紅-綠循環更新 `tests/test_review_suggestions.py`：`test_勾選多條建議後按送出只針對勾選的建議重新規劃` 額外 patch `interaction.is_web_mode` 回傳 True，並斷言 `interaction.ask` 收到的提示文字為「請勾選要修改的建議後按送出（未勾選＝不修改）」
- [x] 4.2 更新 `test_未勾選任何建議就送出時視為不修改並直接通過`：改用 `side_effect` 捕捉 `interaction.ask` 的參數，斷言 `kind="multi_choice"` 後回傳空字串
- [x] 4.3 在 `tests/test_review_suggestions.py` 新增測試（測試本體寫入 Scenario 標題原字串「以命令列回覆修改建議時終端機提示編號輸入格式」）：patch `interaction.is_web_mode` 回傳 False、`interaction.ask` 回傳「all」，斷言提示文字為「請輸入要修改的建議編號（例如 1,3；all=全部；留空＝不修改）」，且 `review_blocking=True`、`review_level="修補"`、`review_result` 末尾依序列出 SUGGESTION 1 與 2
- [x] 4.4 `nodes/review.py` 依 `interaction.is_web_mode()` 分流提示文字（網頁：「請勾選要修改的建議後按送出（未勾選＝不修改）」；命令列：原字串一字不改），兩段文字定義為模組層級常數；確認 `pytest AgentLoop/tests/ -v` 全數通過
- [x] 4.5 將 `web/frontend/src/__tests__/StageDetail.spec.ts` 多選題測試資料的 `prompt` 由「請輸入要修改的建議編號」改為「請勾選要修改的建議後按送出（未勾選＝不修改）」，並在「多選題在詳情中以勾選框與送出按鈕呈現」與「勾選多條建議後按送出只針對勾選的建議重新規劃」測試中斷言詳情顯示此提問全文；確認 `npx vitest run` 全數通過
- [x] 4.6 更新 `ARCHITECTURE.md` review 節點「嚴重程度分流」段：註明修改建議的提示文字依通道分流（網頁為勾選用語、終端機維持編號輸入用語）
