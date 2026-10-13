# Proposal: 執行計畫移除額外流水號

## Intent

規範目的：讓使用者在審閱執行計畫時，看到的編號只有 tasks.md 自帶的階層編號（1.1、1.2、2.1…），不再被前置的「TASK 1、TASK 2…」或「1.、2.…」流水號干擾，避免同一項目出現兩套互相對不上的編號（例如「TASK 3: 2.1 撰寫測試」），也讓使用者回饋修改意見時能直接引用 tasks.md 的編號。

規範背景：執行計畫取自 tasks.md 的 checkbox 項目原文（openspec-authoring 規定一律寫成 `- [ ] N.M <任務>`），本身已帶階層編號；目前三個顯示處又各自加了一層從 1 起算的序號。

輸出要求（三處一致）：

- 每個執行計畫項目獨立一行，內容即 tasks.md checkbox 項目原文（去掉 `- [ ]`／`- [x]` 後的文字，例如「1.1 撰寫測試」），前面不加任何流水號或「TASK N:」字樣
- 項目順序與 tasks.md 相同
- 標題「執行計畫（共 N 個 TASK）」的總數照舊保留

範例及解釋：tasks.md 內容為

```
## 1. 實作
- [ ] 1.1 撰寫測試
- [ ] 1.2 實作功能
## 2. 文件
- [ ] 2.1 更新 ARCHITECTURE.md
```

→ analyze_plan 讀出執行計畫 `["1.1 撰寫測試", "1.2 實作功能", "2.1 更新 ARCHITECTURE.md"]`
→ CLI 人工確認印出「## 執行計畫（共 3 個 TASK）」，下面三行依序為 `  1.1 撰寫測試`、`  1.2 實作功能`、`  2.1 更新 ARCHITECTURE.md`（原本是 `  TASK 1: 1.1 撰寫測試`…）
→ 網頁待回覆提問的確認文字為 `## 執行計畫（共 3 個 TASK）\n\n1.1 撰寫測試\n1.2 實作功能\n2.1 更新 ARCHITECTURE.md\n\n繼續執行？`（原本每行前有 `1. `、`2. `、`3. `）
→ 網頁 analyze_plan 階段詳情的「執行計畫」區塊逐行顯示同樣三行文字，畫面上不再出現清單自動產生的「1. 2. 3.」序號。

本次為顯示層調整，無 OpenSpec 規格層級的外部行為契約變動（skip_specs: true）。

## Scope

In scope:

- `nodes/human_confirm.py`：CLI 終端機列印執行計畫時拿掉 `TASK {i}: ` 前綴
- `nodes/human_confirm.py`：送給網頁的確認提問文字拿掉每行 `{i}. ` 前綴
- `web/frontend/src/components/active-changes/StageDetail.vue`：analyze_plan 階段詳情的執行計畫改為不帶自動序號的清單
- 對應測試更新與 `ARCHITECTURE.md` 描述同步

Out of scope:

- tasks.md 的格式與 analyze_plan 讀取 checkbox 的方式（`_TASK_CHECKBOX_RE`）
- 「執行計畫（共 N 個 TASK）」標題與總數
- execute／review prompt 或審查報告中「TASK」字樣的使用

## Approach

- `human_confirm_node`：CLI 迴圈改為 `print(f"  {task}")`（不再需要 `enumerate`）；`confirm_prompt` 改為 `"\n".join(plan)`。
- `StageDetail.vue`：`<ol class="list-decimal pl-5">` 改為無序且無項目符號的清單（例如 `<ul class="list-none">`，保留 `li.output-text` 讓折行／照原文顯示規則不變）。
- 測試沿用既有 seam：`tests/test_human_confirm.py`（patch `builtins.input` + `capsys` 驗證 CLI 輸出；以 web 模式或 patch `interaction.ask` 擷取 confirm prompt）、`web/frontend/src/__tests__/StageDetail.spec.ts`（mount 後檢查 li 文字與清單無序號樣式）。依 tdd 紅-綠循環先寫失敗測試。
