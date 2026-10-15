# Tasks

## 1. 深色主題色彩 token

- [x] 1.1 改寫 `web/frontend/src/style.css` 的 `@theme`：依 design.md 色表翻轉 `bg`／`surface`／`surface-muted`／`line`／`fg`／`fg-muted`／`primary`／`danger`／`warning`／`success`／`stage-*` 為深色值，新增 `header`、`on-accent`、`overlay` token
- [x] 1.2 在 `@theme` 定義 `--animate-breathe` 與 `@keyframes breathe`（以 `stage-running` 色的 box-shadow 呼吸擴散）
- [x] 1.3 讓 `html`／`body` 使用 `bg-bg` 背景、`text-fg` 前景並宣告 `color-scheme: dark`（`style.css` 或 `index.html`）

## 2. 階段卡片狀態呈現

- [x] 2.1 更新 `web/frontend/src/__tests__/ActiveChanges.spec.ts` 的測試 `執行中任務分頁為每個未封存的 change 顯示一列階段卡片`（紅燈）：改為斷言每張卡片的左側色條 `border-l-stage-*` class、`.stage-status` 徽章的 `bg-stage-*` class 與文字（完成／完成／執行中／尚未開始／尚未開始），以及只有 execute 卡片帶 `animate-breathe`
- [x] 2.2 改寫 `StageCard.vue`：卡片固定 `bg-surface` + 左側 `border-l-4` 狀態色條，狀態文字改為 `bg-stage-*` 徽章，執行中加 `animate-breathe motion-reduce:animate-none`，驚嘆號改為警示色圓形徽章、重跑按鈕改次要按鈕樣式；讓 2.1 轉綠

## 3. 其他元件樣式

- [x] 3.1 `App.vue`：導覽列改 `bg-header`、加「AgentLoop 控制台」標題、分頁 hover／選中樣式，`main` 加最大寬度置中
- [x] 3.2 `ChangeRow.vue`、`ActiveChanges.vue`（含階段詳情面板、新增任務按鈕）：卡片面板化（`bg-surface rounded-xl border shadow-lg`）與按鈕樣式統一
- [x] 3.3 `StageDetail.vue`、`QuestionForm.vue`：區塊標題、`<pre>` 內嵌區塊（日誌加 `max-h-96 overflow-auto`）、輸入框與按鈕樣式統一，`text-white` 改 `text-on-accent`
- [x] 3.4 `NewTaskDialog.vue`、`FolderPicker.vue`、`FileBrowser.vue`：遮罩改 `bg-overlay backdrop-blur-sm`，內框改 `bg-surface rounded-xl border shadow-2xl`，清單項目與按鈕樣式統一
- [x] 3.5 `SettingsPanel.vue`、`ExistingSpecs.vue`、`SpecSearch.vue`、`ArchivedChanges.vue`：面板化、輸入框／select／清單按鈕樣式統一
- [x] 3.6 全前端 grep 確認元件不再出現 `text-white`、`bg-black`、任意色碼或 `<style>` 區塊

## 4. 驗證

- [x] 4.1 在 `web/frontend/` 執行 `npx vitest run`，確認所有既有測試與 2.1 通過
- [x] 4.2 執行 `npm run build`，確認 `vue-tsc` 與 Tailwind 產出（含 `animate-breathe`、新 token utility）無誤

## 5. 文件

- [x] 5.1 更新 `ARCHITECTURE.md`「前端：`web/frontend/`」一節：改述深色主題 token 清單（含新增的 `header`／`on-accent`／`overlay`）、`animate-breathe` 定義位置，以及 `StageCard` 以色條 `border-l-stage-*` + 徽章 `bg-stage-*` 呈現狀態、測試斷言對應 class

## 6. 次要按鈕樣式收斂（審查修補）

- [x] 6.1 在 `web/frontend/src/style.css` 新增 `@utility btn-secondary`，內容為 `@apply rounded-md border border-line bg-surface-muted/0 text-fg transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50`（只含外觀，不含 padding／字級）
- [x] 6.2 將 11 處次要按鈕的外觀 class 換成 `btn-secondary`：`FolderPicker.vue`（「上一層」、「取消」）、`NewTaskDialog.vue`（取消）、`StageCard.vue`（`.rerun-button`）、`ChangeRow.vue`（`.view-files-button`）、`SettingsPanel.vue`、`QuestionForm.vue` ×3（選項、「否」、「中止」）、`FileBrowser.vue`（`.close-button`）、`ActiveChanges.vue`（階段詳情面板關閉）；尺寸、版面與語意 class 原樣保留，主要按鈕不動
- [x] 6.3 `grep -rn "border-line bg-surface-muted/0" web/frontend/src --include=*.vue` 確認無殘留；在 `web/frontend/` 執行 `npx vitest run` 與 `npm run build`，確認既有測試全過且 `btn-secondary` 被正確產出
- [x] 6.4 更新 `ARCHITECTURE.md`「前端：`web/frontend/`」一節：補述 `style.css` 以 `@utility btn-secondary` 集中定義次要按鈕外觀，元件只在呼叫點加尺寸 class

## 7. 測試在網頁模式環境下卡死（審查修補）

- [x] 7.1 （紅燈）在 `tests/test_interaction.py` 新增測試：以 `monkeypatch.setenv` 設定 `AGENTLOOP_INTERACTION=web` 與一個不存在的 `AGENTLOOP_RUN_DIR`，用 `subprocess.run([sys.executable, "-m", "pytest", "<repo>/tests/test_human_confirm.py", "-q"], timeout=60, cwd=<AgentLoop 的上層目錄>)` 執行子 pytest，斷言在逾時前結束且 returncode 為 0。修正前這個測試會因逾時而失敗（`subprocess.TimeoutExpired`）
- [x] 7.2 新增 `tests/conftest.py`：用 autouse fixture 在每個測試開始前 `monkeypatch.delenv("AGENTLOOP_INTERACTION", raising=False)` 與 `monkeypatch.delenv("AGENTLOOP_RUN_DIR", raising=False)`；需要網頁模式的既有測試照原本做法，在測試內自行 `monkeypatch.setenv`，不需修改。讓 7.1 轉綠
- [x] 7.3 （紅燈）在 `tests/test_usage_limit_resume.py` 新增測試：設定這兩個環境變數後呼叫 `_run_claude_once`，以 `unittest.mock.patch` 把 `subprocess.Popen` 換成回傳空 stdout 的假物件（不真的啟動 `claude`），斷言收到的 `env` 不含 `AGENTLOOP_INTERACTION`／`AGENTLOOP_RUN_DIR`，但仍保留其他環境變數（例如 `PATH`）
- [x] 7.4 修改 `lib/claude_runner.py` 的 `_run_claude_once`：以 `os.environ` 複製一份 env 並移除 `AGENTLOOP_INTERACTION`／`AGENTLOOP_RUN_DIR`，再以 `env=` 傳給 `subprocess.Popen`。父行程本身讀取 `AGENTLOOP_RUN_DIR` 的既有邏輯（記錄 session 的檔案）維持不變。讓 7.3 轉綠
- [x] 7.5 在已設定 `AGENTLOOP_INTERACTION=web`／`AGENTLOOP_RUN_DIR` 的 shell 中執行 `pytest AgentLoop/tests/ -v`，確認全數通過、沒有卡住；同時在未設定這兩個變數的 shell 再執行一次
- [x] 7.6 更新 `lib/interaction.py` 檔頭註解、`CLAUDE.md`（「CLI behavior is an exact passthrough…」那句）與 `ARCHITECTURE.md` 互動埠一節，改述為：既有測試對 `builtins.input`／`sys.stdin.isatty` 的 patch 之所以有效，靠的是 `tests/conftest.py` 清除互動模式環境變數；`claude_runner` 不把這兩個變數傳給 `claude` 子行程，因此 agent 執行的指令不會進入網頁模式
