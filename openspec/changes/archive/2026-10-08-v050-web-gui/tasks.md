# Tasks

> 測試命名規則：每個 Scenario 標題必須原字串出現在一個測試中。Vitest 用 `test('<Scenario 標題>', ...)`；
> pytest 把 Scenario 標題放在測試函式 docstring 第一行。各測試任務依 tdd skill 以紅→綠循環進行，接縫見 design.md「Testing Strategy」。

## 1. 互動埠

- [x] 1.1 新增 `lib/interaction.py`：`is_interactive()` 與 `ask(prompt, kind, stage, options, required, multiline)`，CLI 實作重現原本 `print`＋`input()` 與 EOF／KeyboardInterrupt 例外；web 實作（`AGENTLOOP_INTERACTION=web`）寫 `question.json`、輪詢 `answer.json`
- [x] 1.2 將 design.md「互動埠」表格列出的所有呼叫點（analyze_plan 的分支名稱／skip_specs／domain 選擇／新 domain 名稱／domain Purpose／grilling、human_confirm、review 建議挑選、archive 確認、claude_runner 用量上限暫停）改走 `interaction.ask`，提示文字、預設值與分支邏輯保持原樣
- [x] 1.3 將 nodes、lib、main.py 中所有 `sys.stdin.isatty()` 判斷改為 `interaction.is_interactive()`
- [x] 1.4 新增 `core/stages.py` 的 `current_stage()` 供 claude_runner 暫停提問標記所屬階段（與 2.x 共用）
- [x] 1.5 撰寫 pytest：`以命令列執行工作流時提問仍在終端回覆`、`人工確認關卡可在網頁確認執行或送出修改意見`、`用量上限暫停時可在網頁選擇繼續或中止`（web 互動埠＋mock `_run_claude_once`）
- [x] 1.6 確認既有 `tests/test_human_confirm.py`、`tests/test_state_persistence.py`、`tests/test_usage_limit_resume.py` 中對 `input`／`isatty`／`stdin` 的 patch 在互動埠下仍生效；若需改 patch 目標，只改 patch 位置、不改斷言

## 2. 工作階段狀態紀錄

- [x] 2.1 `AgentState` 新增 `stages`、`stage_notes`；`main._empty_state()` 補預設空 dict
- [x] 2.2 `core/stages.py`：`STAGES`、`start()`（該階段 running、其後重設 pending、清 note、印 `@@AGENTLOOP_STAGE <stage>@@`）、`finish()`（依 status 設 done／error）、`set_listener()`
- [x] 2.3 `build_workflow()` 以 `_tracked()` 包裝五個節點（`archive_change` 對應 `archive`），`main.py` 註冊 listener 於階段開始時存檔；`run_node()` 直呼節點的路徑同樣呼叫 start／finish
- [x] 2.4 `main.py` 新增 `--change <name>`：搭配 `--node` 直接載入指定 change 的 state.json，不存在時 exit 1
- [x] 2.5 撰寫 pytest：`工作流推進時各階段狀態依序由尚未開始轉為執行中再轉為完成`、`階段結束且結果為錯誤時該階段記為錯誤且後續階段維持尚未開始`、`review 退回重新規劃時 analyze_plan 之後的階段重設為尚未開始`，並確認 `tests/test_workflow_entrypoints.py` 全數通過

## 3. 設定與容器

- [x] 3.1 `requirements.txt` 加入 `fastapi`、`uvicorn[standard]`、`httpx`；`.gitignore` 加入 `.web/` 與 `web/frontend/node_modules/`、`web/frontend/dist/`
- [x] 3.2 新增 `web/settings.py`：`.web/settings.json`（0600）讀寫、設定檔優先於環境變數的合併、secret 末四碼遮罩、空字串不變更、`/fs` 資料夾列舉與工作區根目錄邊界檢查
- [x] 3.3 docker-compose：改掛載整個 `${HOST_WORKSPACE_ROOT}`（同絕對路徑）、`ports: ["127.0.0.1:8000:8000"]`、`command` 改啟動 uvicorn；`TARGET_PROJECT` 改為選填
- [x] 3.4 Dockerfile：建置前端到 `/opt/agentloop-web/dist` 並設定 `WEB_DIST_DIR`；保留既有 CLI 用法
- [x] 3.5 撰寫 pytest：`認證欄位留空儲存時保留原本的值`、`選擇工作區根目錄以外的路徑時拒絕並提示`

## 4. 執行管理

- [x] 4.1 新增 `web/runner.py`：單一作用中執行（鎖＋`RunConflict`）、以 `start_new_session=True` 啟動 `python -m AgentLoop.main`（新增任務／`--node --change` 重跑）、輸出寫 `output.log`、合併設定進子行程 env
- [x] 4.2 新增任務時依 `task`＋mtime 偵測 change 名稱寫回 `meta.json`
- [x] 4.3 回覆待回覆提問：id 比對（不符／不存在 → `QuestionGone`）、必填空白拒絕
- [x] 4.4 `claude_runner._run_claude_once` 取得 session_id 時，若有 `AGENTLOOP_RUN_DIR` 寫入 `session.json`（`{stage, session_id}`）
- [x] 4.5 中止：killpg SIGTERM→5 秒後 SIGKILL；把目前階段寫成 error＋「使用者中止」，依 `core.session.store_session` 寫回 session 插槽，清空執行目錄
- [x] 4.6 執行結束時依階段標記切分日誌、去 ANSI，寫到 `<target>/.agentloop/changes/<name>/logs/<stage>.log`
- [x] 4.7 撰寫 pytest（假子行程替身）：`使用者中止執行中的階段後該階段標為錯誤並保留 session 供重跑接回`、`執行進行中再送出啟動要求時系統拒絕`、`提問已被回覆後再送出回覆時顯示提問已結束`、`必填文字題送出空白時不送出並提示必填`（API 422 部分）

## 5. HTTP API

- [x] 5.1 新增 `web/app.py`（FastAPI）與 `web/repo_view.py`，實作 design.md「HTTP API」表格所有端點，含路徑穿越檢查與 `StaticFiles` 提供前端
- [x] 5.2 新增 `web/search_api.py`：重用 search.py 的索引／檢索／回答函式，以暫時覆寫環境變數的方式套用設定並序列化
- [x] 5.3 撰寫 pytest（TestClient＋tmp 工作區）：`執行中任務分頁為每個未封存的 change 顯示一列階段卡片`、`沒有階段狀態紀錄的舊任務以尚未開始顯示所有階段`、`點擊卡片後顯示該階段的執行結果與執行日誌`、`重跑某階段時從該階段開始並接續後續流程`、`新增任務後以 analyze_plan 卡片引導初始提問`（change 偵測部分）、`已封存任務分頁每個封存 change 一列並可瀏覽其文件`、`既有 Spec 分頁列出每個 domain 並可檢視其規格內容`、`從任務列開啟該 change 的規格文件`（檔案排序）、`輸入問題搜尋規格後顯示回答與參考檔案`、`規格中找不到相關內容時顯示查無結果訊息`、`搜尋失敗時顯示錯誤訊息並保留查詢文字`（502 部分）、`設定分頁顯示目前設定並可儲存`、`有執行進行中時無法變更目標專案`（409 部分）、`尚未指定目標專案時開啟資料夾選擇器並以選定資料夾作為目標專案`（`/fs` 部分）、`任務描述為空白時無法送出新增任務`（API 422 部分）；同一標題已由前端測試命名時，pytest 端以 `<標題>（API）` 形式命名避免重複

## 6. 前端

- [x] 6.1 建立 `web/frontend/`（Vue 3＋TypeScript＋Vite＋Vitest＋@vue/test-utils＋jsdom），`src/api.ts` 封裝所有 API 呼叫，`usePolling` 2 秒輪詢
- [x] 6.2 `App.vue` 四個主分頁、未設定目標專案時自動開啟 `FolderPicker` 並在其他分頁顯示「請先在設定選擇目標專案」
- [x] 6.3 執行中任務：`ActiveChanges`／`ChangeRow`／`StageCard`（四色、驚嘆號、重跑按鈕僅四個階段、執行中時停用並顯示原因）、暫時列、空狀態、`NewTaskDialog`
- [x] 6.4 `StageDetail`（各階段結果欄位、「（尚無資料）」、「使用者中止」、日誌、中止按鈕＋確認）與 `QuestionForm`（選項題／是非題／文字題／暫停四種控制項、必填與提問已結束錯誤訊息）
- [x] 6.5 `FileBrowser`（change 與封存共用）、`ArchivedChanges`、`ExistingSpecs`、`SpecSearch`（搜尋中狀態、查無結果、錯誤保留查詢）
- [x] 6.6 `SettingsPanel`（四欄位、末四碼、留空不變更、執行中停用目標專案）與 `FolderPicker`（進入子資料夾、返回上一層、確定）
- [x] 6.7 撰寫 Vitest：`開啟網頁後顯示四個主分頁且預設選中執行中任務`、`執行中任務分頁為每個未封存的 change 顯示一列階段卡片`、`沒有任何執行中任務時顯示空狀態與新增任務入口`、`沒有階段狀態紀錄的舊任務以尚未開始顯示所有階段`、`點擊卡片後顯示該階段的執行結果與執行日誌`、`被使用者中止的階段在詳情顯示使用者中止`、`從任務列開啟該 change 的規格文件`、`階段等待人工回覆時卡片顯示驚嘆號並可在詳情中回覆`、`必填文字題送出空白時不送出並提示必填`、`提問已被回覆後再送出回覆時顯示提問已結束`、`重跑某階段時從該階段開始並接續後續流程`、`已有執行進行中時其他啟動動作停用並顯示原因`、`執行進行中再送出啟動要求時系統拒絕`、`新增任務後以 analyze_plan 卡片引導初始提問`、`任務描述為空白時無法送出新增任務`、`已封存任務分頁每個封存 change 一列並可瀏覽其文件`、`沒有任何封存任務時顯示空狀態`、`既有 Spec 分頁列出每個 domain 並可檢視其規格內容`、`輸入問題搜尋規格後顯示回答與參考檔案`、`規格中找不到相關內容時顯示查無結果訊息`、`搜尋失敗時顯示錯誤訊息並保留查詢文字`、`設定分頁顯示目前設定並可儲存`、`有執行進行中時無法變更目標專案`、`尚未指定目標專案時開啟資料夾選擇器並以選定資料夾作為目標專案`
- [x] 6.8 執行 `pytest AgentLoop/tests/ -v` 與前端 `npx vitest run`，全部通過

## 7. 文件同步

- [x] 7.1 ARCHITECTURE.md：新增「網頁控制台」章節（架構圖、互動埠、階段狀態、執行管理、API），更新 `AgentState` 欄位、目錄結構、容器化層／DooD（整個工作區根目錄掛載、對外埠）與 CLI 入口（`--change`）
- [x] 7.2 README.md「安裝與使用」：`.env` 只需 `HOST_WORKSPACE_ROOT`（`TARGET_PROJECT` 等可改在網頁設定）、開啟 `http://127.0.0.1:8000`、網頁操作說明，保留 CLI 用法
- [x] 7.3 CLAUDE.md：Commands 補上網頁服務啟動、`--change` 與前端測試指令；Architecture 補一段互動埠（新增提問點必須走互動埠）與階段狀態包裝的陷阱說明

## 8. 審查修補：階段狀態色與中止寫入路徑

- [x] 8.1 前端導入 Tailwind CSS v4：`web/frontend` devDependencies 加入 `tailwindcss`、`@tailwindcss/vite`（同步更新 `package-lock.json`，Dockerfile 的 `npm ci` 才能裝到），`vite.config.ts` 的 `plugins` 加入 `tailwindcss()`；新增 `src/style.css`（`@import "tailwindcss";`＋`@theme` 完整色盤，token 見 design.md「7. 前端」），由 `main.ts` 匯入
- [x] 8.2 更新 Vitest（依 tdd 先紅後綠）：在既有 `執行中任務分頁為每個未封存的 change 顯示一列階段卡片` 測試中，追加斷言五張卡片的 class 依序含 `bg-stage-done`、`bg-stage-done`、`bg-stage-running`、`bg-stage-pending`、`bg-stage-pending`（保留既有 `data-status` 斷言，不另開新測試）
- [x] 8.3 `StageCard.vue` 以「狀態 → class」對照表套用 `bg-stage-*`（未知狀態退回 `bg-stage-pending`），保留 `data-status` 與既有 class，讓 8.2 轉綠
- [x] 8.4 其餘元件（`App`、`ActiveChanges`、`ChangeRow`、`StageDetail`、`QuestionForm`、`NewTaskDialog`、`FileBrowser`、`ArchivedChanges`、`ExistingSpecs`、`SpecSearch`、`SettingsPanel`、`FolderPicker`）改用 Tailwind utility class 排版與上色，只引用 `@theme` token，不寫任意色碼或 `<style>`；保留既有語意 class 與 `data-*` 屬性，畫面文字與行為不變
- [x] 8.5 撰寫 pytest（依 tdd 先紅後綠，放在 `tests/test_stages.py`）：`stages.finish()` 帶 `note` 時回傳 `stages[stage]` 與 `stage_notes[stage]`、不帶 `note` 時回傳只有 `stages`
- [x] 8.6 `core/stages.py` 的 `finish()` 新增 `note: str | None = None` 參數並更新 docstring，讓 8.5 轉綠；既有呼叫端不改
- [x] 8.7 `web/runner.py` 的 `_mark_aborted_locked()` 移除手刻的 `stages_map`／`notes_map` 複製與改寫，改為 `state.update(stages.finish(state, stage, "error", note=ABORT_NOTE))`；確認既有 `使用者中止執行中的階段後該階段標為錯誤並保留 session 供重跑接回` 測試不改斷言仍通過
- [x] 8.8 執行 `pytest AgentLoop/tests/ -v`、前端 `npx vitest run` 與 `npm run build`（`vue-tsc -b && vite build`），全部通過
- [x] 8.9 文件同步：ARCHITECTURE.md 的網頁控制台／階段狀態段落補上 `finish()` 的 `note` 參數與「runner 中止也經 `finish()` 寫入」、前端改用 Tailwind v4＋`@theme` 色盤；CLAUDE.md「Stage status」陷阱說明補一句 runner 中止同樣經 `stages.finish()`、Commands 前端段落不需新增指令則不改
