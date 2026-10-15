# Tasks

## 1. components 依頁面分資料夾

- [x] 1.1 建立 `web/frontend/src/components/{active-changes,archived-changes,existing-specs,settings,utils}/`，依 design.md 搬移元件：ActiveChanges／ChangeRow／StageCard／StageDetail／QuestionForm／NewTaskDialog → `active-changes/`；ArchivedChanges → `archived-changes/`；ExistingSpecs／SpecSearch → `existing-specs/`；SettingsPanel → `settings/`；FileBrowser／FolderPicker → `utils/`
- [x] 1.2 更新 `App.vue` 與各元件內的相對 import（`../api`、`../composables/usePolling` 改為 `../../...`）
- [x] 1.3 更新 `src/__tests__/*.spec.ts` 的 import 與 `vi.mock` 路徑（測試檔位置不動），執行 `npx vitest run` 與 `npm run build` 確認全綠

## 2. 移除搜尋模型（後端）

- [x] 2.1 更新 pytest（紅）：`tests/test_web_app.py` 的 `test_設定分頁顯示目前設定並可儲存` 改為斷言 `GET /api/settings` 只含 `target_project`、`oauth_token`、`api_key`（及 `workspace_root`、`run_active`），且 `PUT` 帶 `api_key` 後回傳末四碼；`tests/test_web_settings.py` 的 `test_認證欄位留空儲存時保留原本的值` 去掉 `search_model` 輸入與斷言；`TestEffectiveValuePrecedence.test_settings_file_overrides_env` 改以 `TARGET_PROJECT` 驗證優先序
- [x] 2.2 新增 pytest（紅）：於 `tests/test_web_app.py` 的 `TestSpecSearch` 或新的 search 單元測試，在既有 `test_輸入問題搜尋規格後顯示回答與參考檔案` 補一個斷言（或在 `search` 層級另寫同名測試）：即使環境變數 `SEARCH_MODEL=opus`，`search._ask_claude` 呼叫 `claude` 時帶入的 `--model` 仍為 `MODEL_IDS["haiku"]`（monkeypatch `subprocess.run` 觀察參數）
- [x] 2.3 `web/settings.py`：`_KEYS` 移除 `SEARCH_MODEL`、刪除 `_DEFAULT_SEARCH_MODEL`，`get_settings_view()` 不再回 `search_model`，`update_settings()` 刪除 `search_model` 分支並更新 docstring
- [x] 2.4 `web/app.py`：`SettingsBody` 刪除 `search_model`
- [x] 2.5 `search.py`：`_ask_claude()` 固定使用 haiku（`MODEL_IDS["haiku"]`），不再讀 `SEARCH_MODEL`；刪除模組 docstring 的 `SEARCH_MODEL` 行；`web/search_api.py` docstring 同步移除 `SEARCH_MODEL`
- [x] 2.6 清理測試 fixture 中已無意義的 `monkeypatch.delenv("SEARCH_MODEL", ...)`（`tests/test_web_app.py`、`tests/test_web_settings.py`、`tests/test_web_runner.py`），執行 `pytest AgentLoop/tests/ -v` 全綠

## 3. 移除搜尋模型（前端）

- [x] 3.1 更新 `src/__tests__/SettingsPanel.spec.ts` 的 `設定分頁顯示目前設定並可儲存`（紅）：斷言欄位依序只有「目標專案」「Claude OAuth token」「Anthropic API key」，輸入 API key 儲存後 `putSettings` 收到該值、畫面顯示「已儲存」與「已設定（末四碼 abcd）」；`有執行進行中時無法變更目標專案` 改斷言認證欄位仍可編輯；同時移除 `App.spec.ts`、`SettingsPanel.spec.ts` mock 資料中的 `search_model`
- [x] 3.2 `src/api.ts` 的 `SettingsView`／`SettingsUpdate` 刪除 `search_model`；`SettingsPanel.vue` 刪除搜尋模型欄位、`searchModel` 狀態與送出欄位，使 3.1 轉綠

## 4. 既有 Spec 版面

- [x] 4.1 更新 `src/__tests__/ExistingSpecs.spec.ts` 的 `既有 Spec 分頁列出每個 domain 並可檢視其規格內容`（紅）：新增斷言搜尋框在 DOM 順序上位於 domain 清單之前、規格全文位於清單之後
- [x] 4.2 `ExistingSpecs.vue` 調整模板順序為搜尋區 → domain 清單（或空狀態）→ 規格全文，使 4.1 轉綠

## 5. Font Awesome 與圖示

- [x] 5.1 安裝 `@fortawesome/fontawesome-svg-core`、`@fortawesome/free-solid-svg-icons`、`@fortawesome/vue-fontawesome`；新增 `src/icons.ts` 匯出 design.md 圖示對照表中的圖示並在 `main.ts` 以 `library.add` 註冊、全域註冊 `FontAwesomeIcon`；新增 vitest `setupFiles`（`src/__tests__/setup.ts`）以同一份清單註冊，讓測試掛載時能渲染圖示
- [x] 5.2 撰寫測試（紅）`純圖示按鈕以滑鼠停留提示與無障礙名稱呈現原本文字`（放在 `ActiveChanges.spec.ts`，資料夾選擇器的上一層部分可在 `App.spec.ts` 同名 `describe` 下補斷言）：重跑鈕 `aria-label`／`title` 為「重跑」、無可見文字、含 `rotate-right` 圖示與警示黃 class；檢視規格文件鈕 `aria-label`／`title` 為「檢視規格文件」；開啟詳情後關閉鈕 `aria-label`／`title` 為「關閉」、紅色 class、點擊後詳情消失；上一層鈕 `aria-label`／`title` 為「上一層」
- [x] 5.3 實作純圖示按鈕：StageCard 的重跑（`rotate-right`，`text-warning`）、ActiveChanges 詳情面板與 FileBrowser 的關閉（`xmark`，`text-danger`）、ChangeRow 的檢視規格文件（`file-lines`）、FolderPicker 的上一層（`arrow-up`），皆加 `aria-label` 與 `title`，使 5.2 轉綠
- [x] 5.4 撰寫測試（紅）`重跑按鈕停用時滑鼠停留提示顯示停用原因`（`ActiveChanges.spec.ts`）：執行中時 `fix-css` 重跑鈕 `title` 為「目前已有 feat-login 執行中」、`aria-label` 仍為「重跑」、仍只顯示圖示；實作使其轉綠（5.3 的 `disabledReason || '重跑'` 已涵蓋此分支，測試新增後直接綠燈，無需額外實作）
- [x] 5.5 更新既有測試以無障礙名稱定位改為純圖示的按鈕：`ActiveChanges.spec.ts` 的 `從任務列開啟該 change 的規格文件`、`重跑某階段時從該階段開始並接續後續流程`、`已有執行進行中時其他啟動動作停用並顯示原因`，以及任何以文字「關閉」「重跑」「檢視規格文件」「上一層」或 `.close-button` 找按鈕的測試，改用 `[aria-label="…"]`
- [x] 5.6 撰寫測試（紅）`主要操作與階段狀態徽章在文字旁顯示對應圖示`（`ActiveChanges.spec.ts`）：四個主分頁標籤各含 `svg[data-icon]` 且文字不變（主分頁部分可在 `App.spec.ts` 以同名測試驗證）、新增任務鈕含圖示、四種狀態徽章的 `data-icon` 彼此不同且文字為中文狀態名、有待回覆提問的卡片含驚嘆號圖示
- [x] 5.7 實作圖示＋文字：主分頁、新增任務、搜尋、儲存、選擇資料夾、中止、確定／取消、送出／是／否／繼續、階段狀態徽章（尚未開始 `clock`、執行中 `spinner` 旋轉且 `motion-reduce` 不轉、完成 `circle-check`、錯誤 `circle-xmark`）、待回覆驚嘆號改 `circle-exclamation`、清單前綴（domain `book`、檔案 `file-lines`、資料夾 `folder`、封存任務 `box-archive`），使 5.6 轉綠，並確認既有以 `.text()` 斷言標籤／徽章／清單文字的測試仍綠

## 6. 游標

- [x] 6.1 撰寫測試（紅）`滑鼠移到可點擊元素時顯示手指游標且停用按鈕顯示禁止游標`（`ActiveChanges.spec.ts` 或 `ExistingSpecs.spec.ts`）：domain 清單項目、階段卡片帶 `cursor-pointer`；執行中時已停用的重跑鈕帶 `disabled:cursor-not-allowed` 且為 `disabled`，點擊後不呼叫 `window.confirm`
- [x] 6.2 為所有可點擊元素補 `cursor-pointer`（主色按鈕、domain／檔案／資料夾清單按鈕、問答按鈕、對話框按鈕、搜尋／儲存／選擇資料夾等），可停用者補 `disabled:cursor-not-allowed`，使 6.1 轉綠

## 7. 刪除未使用 CSS

- [x] 7.1 以 grep 核對後刪除未被 `style.css` 與任何測試引用的語意 class（design.md 所列清單，測試有引用者保留）與冗餘 utility（`btn-secondary` 的 `bg-surface-muted/0`、class 字串尾端空白等）
- [x] 7.2 改版完成後 grep `style.css` 每個 `--color-*`／`--animate-*` 主題變數的引用，刪除不再使用者；執行 `npx vitest run` 與 `npm run build` 確認全綠（逐一 grep 後確認全部 19 個 token 皆仍被元件引用，無需刪除）

## 8. 文件同步

- [x] 8.1 `README.md`：第 33 行可寫在 `.env` 的設定清單移除 `SEARCH_MODEL`；第 76 行設定分頁欄位移除「搜尋模型」；第 176 行改為「搜尋一律使用 haiku」並註明 `SEARCH_MODEL` 已不再支援
- [x] 8.2 `ARCHITECTURE.md`：第 581 行搜尋 env var 說明改為固定 haiku；第 987 行附近前端元件說明改為依頁面分資料夾（`active-changes/`、`archived-changes/`、`existing-specs/`、`settings/`、`utils/`）並補上 Font Awesome 圖示與純圖示按鈕的約定

## 9. repo_view 去除重複程式碼（純重構，無行為變化）

- [x] 9.1 `web/repo_view.py`：刪除自行宣告的 `STAGES = ("analyze_plan", ...)`，改為 `from ..core.stages import STAGES`，`list_active_changes()` 內用法不變
- [x] 9.2 `web/repo_view.py`：新增 `_list_markdown(root, missing_msg)`（root 非資料夾時 `raise NotFound(missing_msg)`，否則回傳 `_sorted_markdown_files(root)`）與 `_read_markdown(root, rel_path)`（`_safe_join` 後非 `.md` 或非檔案時 `raise NotFound(f"找不到檔案：{rel_path}")`，否則讀出全文）；`list_change_files`／`read_change_file`／`list_archive_files`／`read_archive_file` 改為驗證名稱、計算 root 後呼叫輔助函式，名稱、簽章與錯誤訊息（「找不到 change：…」「找不到封存：…」「找不到檔案：…」）維持不變
- [x] 9.3 執行 `pytest AgentLoop/tests/ -v` 確認既有測試（含 `test_已封存任務分頁每個封存change一列並可瀏覽其文件`、`test_從任務列開啟該change的規格文件`、`test_執行中任務分頁為每個未封存的change顯示一列階段卡片`）全綠；`ARCHITECTURE.md` 若提及 `repo_view` 的函式結構或 `STAGES` 宣告位置則同步更新

## 10. 交付檔案納入版控

- [x] 10.1 逐一 `git add` 下列已被已追蹤程式碼引用、目前卻仍未追蹤（`??`）的交付檔案：`tests/conftest.py`（autouse fixture，清除 `AGENTLOOP_INTERACTION`／`AGENTLOOP_RUN_DIR`）、`tests/test_search.py`（task 2.2 的 `test_即使設定SEARCH_MODEL仍固定使用haiku`）、`web/frontend/src/icons.ts`（task 5.1，`main.ts` 引用）、`web/frontend/src/__tests__/setup.ts`（task 5.1，`vite.config.ts` 的 `test.setupFiles` 引用）
- [x] 10.2 執行 `git status --short`，確認沒有任何被已追蹤程式碼 import／引用、卻仍為 `??` 的檔案；`openspec/changes/archive/2026-10-08-v050-*/` 與 `openspec/specs/web-gui/` 依使用者決定維持未追蹤，不納入本次 `git add`
- [ ] 10.3 以只含暫存區內容的工作目錄驗證：執行 `git stash push -u --keep-index` 暫時移除未暫存與未追蹤的內容後，於 `AgentLoop/` 執行 `python3 -m pytest tests/ -v`，於 `web/frontend/` 執行 `npx vitest run` 與 `npm run build`，三者皆須全綠；驗證完成後執行 `git stash pop` 還原（若改用另開乾淨的 worktree，須先把暫存區內容 commit 到暫時分支，才能在 worktree 中取得）
