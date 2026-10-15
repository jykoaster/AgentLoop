# Proposal: 網頁控制台視覺與操作細節改版

## Intent

規範目的：讓網頁控制台「看得出哪裡能點、一眼認出每個動作」，同時把不再需要的設定與死碼清掉。具體目標：

1. 所有可點擊的元素（主分頁、按鈕、階段卡片、各種清單項目）滑鼠移上去都顯示手指游標；停用中的按鈕顯示禁止游標，使用者不用試點就知道能不能點。
2. 以 Font Awesome 圖示讓畫面更易辨識：「關閉」「重跑」「檢視規格文件」「上一層」改為純圖示按鈕（原文字改成滑鼠停留提示與無障礙名稱），「重跑」為警示黃、「關閉」為紅色，兩者一眼可分；其餘主要操作、主分頁、階段狀態徽章與清單項目在文字旁加上圖示。
3. 「既有 Spec」分頁把規格搜尋區移到 domain 清單上方，讓搜尋成為進入此分頁的第一個動作。
4. 移除「搜尋模型」設定：網頁欄位、設定 API 與命令列 `search.py` 的 `SEARCH_MODEL` 全部拿掉，規格搜尋一律固定使用 haiku。
5. 前端 components 依頁面分資料夾，共用元件集中在 `components/utils/`；刪除沒被樣式或測試引用的 class 與冗餘 utility。

規範背景：目前多數按鈕只有文字、部分清單項目（domain、檔案、資料夾）滑鼠移上沒有手指游標，「關閉」「重跑」都是同一種灰框樣式難以區分；搜尋框排在 domain 清單與規格全文之後，規格一長就得捲到底才找得到；搜尋模型可切換但實務上一律用 haiku，多一個欄位只增加設定負擔。

## Scope

In scope:

- 全部可點擊元素補上手指游標，停用按鈕維持禁止游標
- 引入 Font Awesome（Vue 元件版），「關閉」「重跑」「檢視規格文件」「上一層」改為純圖示按鈕並保留滑鼠停留提示與無障礙名稱；「重跑」警示黃、「關閉」紅色
- 主分頁、新增任務、搜尋、儲存、選擇資料夾、中止、問答回覆按鈕（送出／是／否／繼續）、四種階段狀態徽章、清單項目（domain、檔案、資料夾、封存任務）於文字旁加圖示；待回覆驚嘆號改用圖示呈現
- 「既有 Spec」分頁版面改為：搜尋區 → domain 清單 → 規格全文
- 移除搜尋模型：設定分頁欄位、設定 API 的讀寫欄位、`search.py` 讀取 `SEARCH_MODEL` 的邏輯，搜尋固定 haiku
- `web/frontend/src/components/` 依頁面拆為 `active-changes/`、`archived-changes/`、`existing-specs/`、`settings/`、`utils/`
- 刪除未被樣式或測試引用的語意 class 與冗餘 utility，改版後再清掉 `style.css` 不再使用的主題變數
- 同步更新測試、`README.md`、`ARCHITECTURE.md`
- 後端 `web/repo_view.py` 去除重複程式碼（無外部可觀察行為變化）：`STAGES` 改由 `core.stages` 匯入；change／封存的列檔與讀檔改用共用輔助函式

Out of scope:

- 新增主分頁或改變任何工作流節點行為、提問流程、路由
- 改變既有文字訊息內容（例如「目前已有 … 執行中」「（尚無資料）」）
- 淺色主題或整體配色重新設計（只新增「重跑」「關閉」的顏色）
- 其他 Claude 呼叫（工作流節點）的模型選擇

## Approach

- 安裝 `@fortawesome/fontawesome-svg-core`、`@fortawesome/free-solid-svg-icons`、`@fortawesome/vue-fontawesome`，在 `main.ts` 以 `library.add(...)` 只註冊用到的圖示並全域註冊 `FontAwesomeIcon`（tree-shaking，避免整包字型）。
- 純圖示按鈕以 `title`（滑鼠停留提示）+ `aria-label`（無障礙名稱）承載原文字；「重跑」停用時 `title` 顯示停用原因、`aria-label` 仍為「重跑」。顏色沿用 `style.css` 既有 `--color-warning`（重跑）與 `--color-danger`（關閉）。
- 游標統一由 `btn-secondary` utility 與各元件按鈕 class 提供 `cursor-pointer`／`disabled:cursor-not-allowed`。
- 後端：`web/settings.py` 的 `_KEYS` 移除 `SEARCH_MODEL`（舊 `settings.json` 殘留值會被 `_read_raw()` 過濾掉）、`get_settings_view()`／`update_settings()` 移除 `search_model`；`web/app.py` 的 `SettingsBody` 移除 `search_model`；`search.py` 直接用 `MODEL_IDS["haiku"]`。
- `web/repo_view.py` 純重構：刪除自行宣告的 `STAGES`，改為 `from ..core.stages import STAGES`；抽出 `_list_markdown(root, missing_msg)`、`_read_markdown(root, rel_path)`，四個公開函式名稱、簽章與錯誤訊息不變。
- 細節（圖示對照表、測試接縫）見 `design.md`。
