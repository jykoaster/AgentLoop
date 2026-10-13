# Tasks

## 1. 測試先行（紅燈）

- [x] 1.1 在 `tests/test_state_persistence.py` 的 `TestAskDomainSelection` 新增測試：patch `AgentLoop.nodes.analyze_plan.interaction.ask` 模擬網頁回覆（`is_interactive` 回傳 True），第一題回「2」、第二題回「billing」，斷言第一次呼叫的 `options` 為 `["1. web-gui", "2. 以上皆非，建立新 domain"]`、第二次呼叫是新 domain 名稱文字題、回傳值為 `([], "billing")`；測試本體（docstring 或註解）須含 Scenario 標題原字串「點擊建立新 domain 選項後接著詢問新 domain 名稱」
- [x] 1.2 同一類別新增測試：既有 domain 為 `["auth", "billing"]`，回覆「2」，斷言 `options` 依序為「1. auth」「2. billing」「3. 以上皆非，建立新 domain」、回傳 `(["billing"], "")`，且只呼叫 `ask` 一次；測試本體須含「點擊既有 domain 選項後以該 domain 繼續規劃」
- [x] 1.3 既有 `test_select_multiple_existing_domains` 已涵蓋逗號複選行為，在其本體補上 Scenario 標題原字串「以自訂文字輸入多個編號同時選擇多個既有 domain」，不另開新測試
- [x] 1.4 執行 `pytest AgentLoop/tests/test_state_persistence.py -v`，確認 1.1、1.2 為紅燈（options 尚未帶編號）

## 2. 修正實作（綠燈）

- [x] 2.1 `nodes/analyze_plan.py` 的 `_ask_domain_selection()`：送給 `interaction.ask` 的 `options` 改成 `[f"{i}. {d}" for i, d in enumerate(domains, 1)] + [f"{new_idx}. 以上皆非，建立新 domain"]`；終端 `print()` 與答案解析邏輯不變
- [x] 2.2 執行 `pytest AgentLoop/tests/ -v` 與 `cd AgentLoop/web/frontend && npx vitest run`，確認全部通過（含既有命令列輸入測試）

## 3. 共用編號組字 helper（純重構，行為不變）

- [x] 3.1 在 `tests/test_interaction.py` 新增 `numbered()` 單元測試（紅燈）：`numbered(["auth", "billing", "以上皆非，建立新 domain"])` 回傳 `["1. auth", "2. billing", "3. 以上皆非，建立新 domain"]`；`numbered([])` 回傳 `[]`
- [x] 3.2 在 `lib/interaction.py` 新增公開函式 `numbered(items: list[str]) -> list[str]`，回傳以 1 起算、「N. 文字」格式的清單，讓 3.1 轉綠
- [x] 3.3 `nodes/analyze_plan.py` 的 `_ask_domain_selection()`：以 `interaction.numbered(domains + ["以上皆非，建立新 domain"])` 產生清單，`options=` 直接使用；終端 `print()` 迴圈改成走訪這份清單並套用原本的 `_YELLOW` 顏色與兩格縮排（印出文字與現狀逐字相同）；`new_idx` 與答案解析邏輯不變
- [x] 3.4 `nodes/review.py` 的建議選擇題：以 `interaction.numbered(suggestions)` 產生清單，終端 `print(f"  {line}")` 與 `options=` 共用；印出文字、提示文字與 `_parse_suggestion_selection()` 選擇邏輯不變
- [x] 3.5 執行 `pytest AgentLoop/tests/ -v` 與 `cd AgentLoop/web/frontend && npx vitest run`，確認全部通過（含 1.1、1.2 的網頁路徑測試與既有 review 建議選擇測試）

## 4. 文件同步

- [x] 4.1 依 CLAUDE.md「Keep docs in sync」規定，更新 `ARCHITECTURE.md` 描述 `_ask_domain_selection()` 的段落（約第 249–253 行），補充：網頁模式的選項以「N. 」編號格式送出，好讓網頁選項按鈕把編號交給工作流
- [x] 4.2 依 CLAUDE.md「Keep docs in sync」規定，更新 `ARCHITECTURE.md` 的「互動埠：`lib/interaction.py`」段落，補一句說明 `numbered()`：選項題的「編號. 文字」清單統一由它產生，analyze_plan 的 domain 歸屬提問與 review 的建議選擇題共用，終端清單與網頁選項按鈕的編號因此一致
