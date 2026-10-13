# Design: 網頁控制台視覺與操作細節改版

## Technical Approach

### Font Awesome 引入

- 套件：`@fortawesome/fontawesome-svg-core`、`@fortawesome/free-solid-svg-icons`、`@fortawesome/vue-fontawesome`（Vue 3 版）。
- `src/main.ts`：`library.add(...)` 只加入下表用到的圖示，`app.component('FontAwesomeIcon', FontAwesomeIcon)` 全域註冊。測試以 `mount()` 時需在 `global.components` 註冊同一元件，或在 vitest `setupFiles` 統一註冊（建議新增 `src/__tests__/setup.ts` 並於 `vite.config.ts` 的 `test.setupFiles` 指向它，同時在其中 `library.add` 同一份圖示清單；圖示清單抽成 `src/icons.ts` 匯出，`main.ts` 與 setup 共用）。
- 圖示以 SVG 呈現，`<svg>` 帶 `data-icon="<名稱>"` 屬性，測試可據以斷言。

### 圖示對照表

| 位置 | 呈現 | 圖示（free-solid） | 顏色 |
| --- | --- | --- | --- |
| 「關閉」（階段詳情面板、規格文件瀏覽器） | 純圖示 | `xmark` | `text-danger`，hover 時 `bg-danger/15` |
| 「重跑」（階段卡片） | 純圖示 | `rotate-right` | `text-warning`，hover 時 `bg-warning/15` |
| 「檢視規格文件」（任務列） | 純圖示 | `file-lines` | 次要按鈕樣式 |
| 「上一層」（資料夾選擇器） | 純圖示 | `arrow-up` | 次要按鈕樣式 |
| 待回覆驚嘆號（階段卡片） | 純圖示 | `circle-exclamation` | `text-warning` |
| 主分頁：執行中任務／已封存任務／既有 Spec／設定 | 圖示＋文字 | `list-check`／`box-archive`／`book`／`gear` | 沿用分頁文字色 |
| 新增任務 | 圖示＋文字 | `plus` | 沿用 |
| 搜尋 | 圖示＋文字 | `magnifying-glass` | 沿用 |
| 儲存 | 圖示＋文字 | `floppy-disk` | 沿用 |
| 選擇資料夾 | 圖示＋文字 | `folder-open` | 沿用 |
| 中止（階段詳情、用量暫停） | 圖示＋文字 | `stop` | 沿用 |
| 送出／是／否／繼續 | 圖示＋文字 | `paper-plane`／`check`／`xmark`／`play` | 沿用 |
| 確定／取消（對話框） | 圖示＋文字 | `check`／`xmark` | 沿用 |
| 階段狀態徽章：尚未開始／執行中／完成／錯誤 | 圖示＋文字 | `clock`／`spinner`（`spin`，`motion-reduce` 時不轉）／`circle-check`／`circle-xmark` | 沿用徽章色 |
| 清單項目前綴：domain／檔案／資料夾／封存任務 | 圖示＋文字 | `book`／`file-lines`／`folder`／`box-archive` | `text-fg-muted` |

- 純圖示按鈕：`aria-label` 固定為原文字；`title` 平時為原文字，「重跑」停用時改為停用原因（`目前已有 … 執行中`）。圖示本身加 `aria-hidden`（vue-fontawesome 預設即是）。
- 圖示＋文字：文字仍是按鈕內的可見文字，因此既有以 `.text()` 斷言的測試（主分頁標籤、徽章文字、清單項目文字）不受影響。

### 游標

- `@utility btn-secondary` 已含 `cursor-pointer` 與 `disabled:cursor-not-allowed`；其他以 class 直接組樣式的按鈕（主色按鈕、清單項目按鈕、domain／檔案／資料夾清單按鈕、對話框按鈕）逐一補上 `cursor-pointer`，可停用者補 `disabled:cursor-not-allowed`。
- 階段卡片已有 `cursor-pointer`，保留。

### 既有 Spec 版面

`ExistingSpecs.vue` 模板順序改為：`<SpecSearch />` → domain 清單（或「目前沒有既有 Spec」）→ 規格全文。

### components 目錄

```
src/components/
├── active-changes/   ActiveChanges、ChangeRow、StageCard、StageDetail、QuestionForm、NewTaskDialog
├── archived-changes/ ArchivedChanges
├── existing-specs/   ExistingSpecs、SpecSearch
├── settings/         SettingsPanel
└── utils/            FileBrowser、FolderPicker
```

`App.vue` 與各元件的相對 import、`src/__tests__/*.spec.ts` 的 import 路徑隨之更新；測試檔位置不動。

### 刪除未使用 CSS

- 刪除未被 `style.css`、也未被任何測試引用的語意 class：`app-title`、`change-row-title`、`stage-cards`、`stage-name`、`close-button`、`custom-answer`、`existing-specs`、`archived-changes`、`active-changes`、`api-key`、`oauth-token`、`search-model`（隨欄位一併刪）、`branch-name`、`stage-detail`、`stage-detail-panel`、`external-error`、`saved-message`（實作時再以 grep 核對一次：凡測試有引用就保留）。
- 冗餘 utility：`btn-secondary` 內無效果的 `bg-surface-muted/0`、`grid-cols-5 gap-2 ` 尾端空白等。
- 改版完成後 grep `style.css` 每個 `--color-*`／`--animate-*` 是否仍被引用，未引用者刪除。

### 移除搜尋模型

- `web/settings.py`：`_KEYS` 移除 `SEARCH_MODEL`、刪 `_DEFAULT_SEARCH_MODEL`；`get_settings_view()` 不再回 `search_model`；`update_settings()` 刪 `search_model` 分支並更新 docstring。舊 `settings.json` 若殘留 `SEARCH_MODEL`，`_read_raw()` 依 `_KEYS` 過濾即忽略，下一次儲存時自然被覆寫掉，不需遷移。
- `web/app.py`：`SettingsBody` 刪 `search_model`。
- `web/search_api.py`：模組 docstring 移除 `SEARCH_MODEL` 描述。
- `search.py`：`_ask_claude()` 改用 `model = MODEL_IDS["haiku"]`（或保留 `_DEFAULT_MODEL = "haiku"` 常數直接查表），不再讀 `os.environ["SEARCH_MODEL"]`；模組 docstring 刪 `SEARCH_MODEL` 行。
- `web/frontend/src/api.ts`：`SettingsView`／`SettingsUpdate` 刪 `search_model`。

### repo_view 去除重複程式碼

- `STAGES`：刪除 `web/repo_view.py` 自行宣告的 `STAGES = (...)`，改為 `from ..core.stages import STAGES`；`list_active_changes()` 內的 `STAGES` 用法不變。`web/runner.py` 已從 `..core` 匯入，不會造成循環匯入。
- 列檔／讀檔：新增兩個模組內私有輔助函式
  - `_list_markdown(root: str, missing_msg: str) -> list[str]`：`root` 不是資料夾時 `raise NotFound(missing_msg)`，否則回傳 `_sorted_markdown_files(root)`。
  - `_read_markdown(root: str, rel_path: str) -> str`：`_safe_join(root, rel_path)` 後，不是 `.md` 或不是檔案時 `raise NotFound(f"找不到檔案：{rel_path}")`，否則以 UTF-8 讀出全文。
- 四個公開函式名稱、簽章、錯誤訊息全部不變，只負責驗證名稱並算出 root，再交給輔助函式：
  - `list_change_files`：`_require_safe_name(change_name, "change")` → `_list_markdown(_openspec_change_dir(...), f"找不到 change：{change_name}")`
  - `read_change_file`：`_require_safe_name(change_name, "change")` → `_read_markdown(_openspec_change_dir(...), rel_path)`
  - `list_archive_files`：`_require_safe_name(dir_name, "封存")` → `_list_markdown(os.path.join(_archive_root(project), dir_name), f"找不到封存：{dir_name}")`
  - `read_archive_file`：`_require_safe_name(dir_name, "封存")` → `_read_markdown(os.path.join(_archive_root(project), dir_name), rel_path)`
- 無外部可觀察行為變化，由既有 pytest（`test_已封存任務分頁每個封存change一列並可瀏覽其文件`、`test_從任務列開啟該change的規格文件`、`test_執行中任務分頁為每個未封存的change顯示一列階段卡片`）把關，不另寫新測試。

## Architecture Decisions

### Decision: 純圖示按鈕以 `title` + `aria-label` 保留原文字

只顯示圖示會失去可讀性與可測試性。以 `aria-label` 固定原文字，測試可用 `[aria-label="重跑"]` 定位，螢幕閱讀器也能讀出；`title` 提供滑鼠停留提示，並沿用原本「停用時顯示原因」的行為。

### Decision: 使用 vue-fontawesome（SVG）而非 CSS webfont

SVG 元件可只打包用到的圖示、在 jsdom 測試中也能渲染出帶 `data-icon` 的節點；webfont 版需載入整包字型且測試只能看到 `<i class>`。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫**：Vitest + `@vue/test-utils` 掛載各頁面頂層元件（`App`、`ActiveChanges`、`ExistingSpecs`、`SettingsPanel`、`StageDetail`），沿用既有 `vi.mock('../api')` 的作法，從畫面上可觀察的結果斷言：按鈕的 `aria-label`／`title`、圖示 `svg[data-icon]`、按鈕可見文字、元素順序。游標以 class 斷言（jsdom 不解析 Tailwind，故以 `cursor-pointer`／`disabled:cursor-not-allowed` class 存在作為可觀察代理）。
- **次要接縫**：pytest 對 `/api/settings` 與 `web.settings` 公開函式（`get_settings_view`／`update_settings`）、`search._ask_claude` 呼叫參數（monkeypatch `subprocess.run` 觀察 `--model`）。

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| 任務 `feat-login` 一列、無執行中；滑鼠移到 execute 卡片的重跑鈕 | 只顯示 `rotate-right` 圖示、無可見文字；提示與無障礙名稱皆「重跑」；黃色 | `[aria-label="重跑"]` 的 `title`、`text()` 為空、含 `svg[data-icon="rotate-right"]`、class 含 `text-warning` |
| 開啟 review 詳情後的關閉鈕 | `xmark` 圖示、提示「關閉」、紅色；點擊後詳情關閉 | `[aria-label="關閉"]`、`text-danger`、點擊後 `.stage-detail-panel` 消失（若該 class 被刪則改以詳情內容消失斷言） |
| 任務列「檢視規格文件」鈕 | `file-lines` 圖示、提示「檢視規格文件」 | `[aria-label="檢視規格文件"]` |
| 資料夾選擇器「上一層」 | `arrow-up` 圖示、提示「上一層」，在根目錄時停用 | `[aria-label="上一層"]`、`disabled` |
| `feat-login` 執行中時滑到 `fix-css` 的重跑鈕 | 停用、提示「目前已有 feat-login 執行中」、無障礙名稱仍「重跑」 | `title`、`aria-label`、`disabled` |
| 四階段狀態各一張卡片 | 徽章依序含 `clock`／`spinner`／`circle-check`／`circle-xmark` 與中文文字 | `.stage-status svg[data-icon]`、`.stage-status` 文字 |
| 開啟控制台 | 四個主分頁標籤各有圖示，文字不變 | `.tab-button svg[data-icon]`、`.text()` |
| 各頁可點元素 | 皆有 `cursor-pointer`；停用按鈕有 `disabled:cursor-not-allowed` | class |
| 開啟「既有 Spec」分頁（domain `auth`、`billing`） | 搜尋框在 domain 清單之前；清單 `auth`、`billing` | DOM 順序（`compareDocumentPosition`） |
| 送出搜尋（API） | `claude` 呼叫帶 haiku 模型 ID | monkeypatch `subprocess.run` 參數 |
| 開啟設定分頁 | 只有目標專案、OAuth token、API key 三欄 | 欄位 label 文字清單 |
| `PUT /api/settings` 帶 API key | 回傳只含目標專案與兩個認證狀態，API key 顯示末四碼 | response JSON |
| repo_view 重構後列出／讀取 change 與封存文件（既有 pytest） | 檔案清單順序、內容、找不到時的錯誤訊息與重構前相同 | 既有 `test_已封存任務分頁…`、`test_從任務列開啟該change的規格文件` 全綠 |

## Technical Debt & Follow-up Notes

- 舊 `.web/settings.json` 可能殘留 `SEARCH_MODEL`，被讀取時過濾忽略，下一次儲存會寫回不含此鍵的內容；不另寫遷移。
- `.env` 若仍寫有 `SEARCH_MODEL` 將不再有任何作用；README 需註明已移除。
