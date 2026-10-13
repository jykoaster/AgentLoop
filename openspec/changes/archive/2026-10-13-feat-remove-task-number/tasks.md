# Tasks

## 1. CLI 與網頁確認文字（human_confirm）

- [x] 1.1 在 `tests/test_human_confirm.py` 新增測試（tdd 紅燈）：plan 為 `["1.1 撰寫測試", "1.2 實作功能", "2.1 更新 ARCHITECTURE.md"]` 時，以 `capsys` 斷言 CLI 輸出依序含 `  1.1 撰寫測試`、`  1.2 實作功能`、`  2.1 更新 ARCHITECTURE.md` 三行且不含 `TASK 1:` 等字樣；並 patch `interaction.ask` 擷取 confirm prompt，斷言其為 `## 執行計畫（共 3 個 TASK）\n\n1.1 撰寫測試\n1.2 實作功能\n2.1 更新 ARCHITECTURE.md\n\n繼續執行？` 開頭的確認文字（每行無 `1. ` 前綴）
- [x] 1.2 修改 `nodes/human_confirm.py`：CLI 列印改為 `print(f"  {task}")`，`confirm_prompt` 的計畫段改為 `"\n".join(plan)`，保留「執行計畫（共 N 個 TASK）」標題；讓 1.1 測試轉綠，並確認 `tests/test_human_confirm.py` 其餘測試仍通過

## 2. 網頁階段詳情（StageDetail）

- [x] 2.1 在 `web/frontend/src/__tests__/StageDetail.spec.ts` 的 analyze_plan 案例中（tdd 紅燈）：fields.plan 改用 `['1.1 撰寫測試', '1.2 實作功能']`，斷言 li 文字依序等於原文、清單元素不是 `ol` 且不帶 `list-decimal` 樣式；同檔 human_confirm 確認提問的 `confirmPrompt` 範例改為不帶 `1. 2. 3.` 前綴的格式（`## 執行計畫（共 3 個 TASK）\n\n1.1 a\n1.2 b\n2.1 c\n\n繼續執行？`）
- [x] 2.2 修改 `web/frontend/src/components/active-changes/StageDetail.vue`：執行計畫的 `<ol class="list-decimal pl-5">` 改為無項目符號的 `<ul class="list-none">`（保留 `li.output-text`），讓 2.1 測試轉綠；於 `web/frontend/` 執行 `npx vitest run` 與 `npm run build` 確認通過

## 3. 文件同步

- [x] 3.1 更新 `ARCHITECTURE.md` 的 `human_confirm` 行為描述：執行計畫以 tasks.md 原文逐行列出（沿用其 1.1、2.1 階層編號，不另加序號），並保留「含數量」說明
- [x] 3.2 執行 `pytest AgentLoop/tests/ -v` 確認全部通過
