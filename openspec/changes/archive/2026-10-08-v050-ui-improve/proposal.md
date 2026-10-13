# Proposal: 網頁控制台改為深色主題並強化元件樣式

## Intent

規範目的：把網頁控制台整體翻轉為深色主題，讓使用者在長時間盯著工作流進度時，一眼就分得出「頁面背景 → 卡片／面板 → 卡片內嵌區塊（日誌、規格內文）」三個層次，並讓每張階段卡片的狀態（尚未開始灰／執行中藍／完成綠／錯誤紅）在深色背景上仍清楚可辨、執行中的階段更醒目。

規範背景：目前前端只用了最基本的 Tailwind 樣式，頁面背景 `#f5f5f5` 與卡片 `#ffffff` 亮度只差約 4%，卡片幾乎融入背景；階段卡片以整張填滿狀態色呈現，灰色「尚未開始」卡片配深色字，與其他三種白字卡片風格不一致；按鈕、輸入框、對話框也缺少圓角、陰影、hover／focus 等回饋，整體看起來簡陋。

工作樹另外含有上一輪 web-gui 建置留下、尚未 commit 的後端改動（`web/*.py`、`core/stages.py`、`lib/interaction.py`、`nodes/*.py`、`main.py`、`docs/adr/0001-*` 與對應的後端測試等）。這些改動是本 change 的既有基線，不屬於本次驗收範圍。唯一例外是下方 In scope 列出的「測試在網頁模式環境下卡死」修正。

審查時發現的問題：web 控制台啟動工作流子行程時會設定 `AGENTLOOP_INTERACTION=web`／`AGENTLOOP_RUN_DIR`，`claude -p` 以及它在 execute／review 中執行的 `pytest` 都會繼承這兩個變數。結果 `is_interactive()` 一律回傳 True，`tests/test_human_confirm.py` 對 `sys.stdin.isatty` 的 patch 被架空，程式改走網頁提問並無限輪詢 `answer.json`，整個 `pytest` 因此卡死，從 web 控制台觸發的 review 也就永遠無法完成。

## Scope

In scope:

- 重新定義 `style.css` 的 `@theme` 色彩 token 為深色主題（深色頁面背景、較亮的深色卡片面、更亮一階的內嵌區塊、可辨識的邊框色、淺色前景文字）
- 階段卡片改為「較亮的深色卡片面 + 左側狀態色粗色條 + 狀態文字徽章著色」，執行中的卡片加上呼吸光暈動畫；灰／藍／綠／紅對應不變
- 所有元件（主分頁導覽列、任務列、階段詳情、提問表單、設定、資料夾選擇器、新增任務對話框、檔案瀏覽器、既有 Spec、規格搜尋、已封存任務）補上一致的樣式：圓角、陰影、間距、按鈕／輸入框的 hover／focus／disabled 狀態、對話框遮罩
- 把重複散落在各元件的「次要按鈕」外觀 class 收斂為 `style.css` 中單一的 `btn-secondary` utility，日後調整次要按鈕樣式只需改一處（畫面不變）
- 更新受影響的前端測試與 `ARCHITECTURE.md` 前端一節
- 修正測試在網頁模式環境下卡死：新增 `tests/conftest.py`，在每個測試開始前清除互動模式環境變數；`lib/claude_runner.py` 啟動 `claude` 子行程時，不把這兩個變數傳給子行程；補上對應測試，並同步修正 `CLAUDE.md`、`ARCHITECTURE.md` 與 `lib/interaction.py` 檔頭中「既有 patch 原封不動繼續生效」的描述。改動範圍僅限上述幾處

Out of scope:

- 主要按鈕 class 的收斂與其 focus 樣式統一（維持現狀）
- 次要按鈕的尺寸（padding、字級）統一

- 淺色／深色主題切換開關與跟隨系統偏好
- 引入 UI 元件庫或 icon 套件
- 任何文案、版面結構、互動流程的變更；web 控制台後端 HTTP API 與互動埠（`lib/interaction.py` 的判斷邏輯）的行為變更
- 工作樹中上一輪 web-gui 建置留下的後端改動（視為既有基線，不在本次驗收範圍）
- 把具體對比度數值（如 WCAG 比值）寫成規格驗收條件

## Approach

沿用既有慣例：Tailwind CSS v4，所有顏色集中於 `src/style.css` 的 `@theme`，元件只引用 token、不寫任意色碼與 `<style>` 區塊。先翻轉 token 色值為深色版本並新增需要的 token（如內嵌區塊、主要按鈕上的前景色、遮罩色），再逐一元件套用一致的樣式組合；呼吸光暈以 `@theme` 內的 `--animate-*` 搭配 `@keyframes` 定義，元件透過 `animate-*` utility 使用。細節見 `design.md`。
