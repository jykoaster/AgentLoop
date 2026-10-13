# Design: 網頁圖形化控制台（v0.5.0）

## Technical Approach

### 整體架構

```
瀏覽器 (Vue 3 SPA, 每 2 秒輪詢)
   │  HTTP JSON
   ▼
uvicorn + FastAPI  (AgentLoop/web/app.py)      ← 容器 CMD，監聽 0.0.0.0:8000，compose 只綁 host 127.0.0.1:8000
   │  ├─ web/settings.py   設定檔讀寫、合併 .env、遮罩 secret、資料夾瀏覽
   │  ├─ web/runner.py     單一作用中執行（子行程、日誌、提問/回覆檔、中止、session 回寫）
   │  ├─ web/repo_view.py  讀 .agentloop/changes/*/state.json、openspec/changes(/archive)、openspec/specs
   │  └─ web/search_api.py 重用 search.py 的 _resolve/_is_stale/_build_index/_search/_ask_claude
   ▼
子行程：python -m AgentLoop.main ...   (start_new_session=True，env 帶 AGENTLOOP_INTERACTION=web、AGENTLOOP_RUN_DIR、設定值)
   └─ nodes → lib/interaction.py（網頁實作）→ question.json / answer.json
```

### 1. 互動埠 `lib/interaction.py`

```python
Kind = Literal["text", "choice", "confirm", "pause"]
def is_interactive() -> bool          # CLI：sys.stdin.isatty()；web：True
def ask(prompt: str, *, kind: Kind, stage: str, options: list[str] | None = None,
        required: bool = False, multiline: bool = False) -> str
    # CLI：維持各呼叫點原本的 print + input()；EOF / KeyboardInterrupt 一律重新 raise 同型例外，
    #      讓呼叫點既有 except 分支照舊處理（行為與提示文字完全不變）
    # web：寫 {id, stage, kind, prompt, options, required, created_at} 到 $AGENTLOOP_RUN_DIR/question.json，
    #      每 0.5 秒輪詢 answer.json（{id, answer}，id 須相符），讀到後刪除兩檔並回傳 answer
```

- 由 `AGENTLOOP_INTERACTION=web` 選擇網頁實作；未設定即 CLI 實作。
- 需改走互動埠的呼叫點（只換 I/O，不改提示文字、預設值與分支邏輯）：

| 呼叫點 | stage | kind | 備註 |
| --- | --- | --- | --- |
| `analyze_plan._ask_branch_name` | analyze_plan | text, required | 空白由 API 層拒絕（必填） |
| `analyze_plan._ask_skip_specs` | analyze_plan | confirm | 回 `y`／`n` |
| `analyze_plan._ask_domain_selection` | analyze_plan | choice | options＝既有 domain＋「以上皆非」；允許逗號多選，自訂文字照送 |
| `analyze_plan._ask_new_domain_name` | analyze_plan | text | 可空白 |
| `analyze_plan._ask_domain_purpose` | analyze_plan | text, multiline | web 模式不需 `_drain_stdin()` |
| `analyze_plan._run_with_grilling` | analyze_plan | choice | prompt＝QUESTION 全文；options 由 `^\d+\.\s` 行解析；空白＝採用建議答案 |
| `human_confirm_node`（y/N、修改意見） | human_confirm | confirm → text | 兩個連續提問；確認提問的 prompt 帶分析摘要與計畫清單 |
| `review_node` 建議挑選 | review | choice | options＝SUGGESTION 清單；回編號字串（可逗號多選）或空白 |
| `archive._ask_should_archive` | archive | confirm | |
| `claude_runner.call_claude` 用量上限暫停 | 目前 stage | pause | 「繼續」回 `""`、「中止」回 `q`；prompt 帶錯誤訊息 |

- 所有 `sys.stdin.isatty()` 判斷改用 `interaction.is_interactive()`（`grep -n isatty nodes lib main.py` 共 9 處）。
- `main._list_and_select_change()` 不經互動埠；網頁改用新的 `--change` 參數。
- 目前 stage 由 `core/stages.py` 的模組層 `current_stage()` 提供給 claude_runner 的暫停提問使用。

### 2. 階段狀態 `core/stages.py`＋`AgentState`

- `AgentState` 新增 `stages: dict[str, str]`（值：`pending`／`running`／`done`／`error`）與 `stage_notes: dict[str, str]`（目前只有 `"使用者中止"`）。
  `main._empty_state()` 補兩個空 dict；舊 state.json 缺欄位時一律視為 `pending`。
- `STAGES = ("analyze_plan", "human_confirm", "execute", "review", "archive")`；graph 節點 `archive_change` 對應 stage `archive`，`increment` 不是 stage。
- `build_workflow()` 以 `_tracked(stage, fn)` 包裝五個節點：開始時呼叫 `stages.start(state, stage)`（該 stage→running、之後各 stage→pending、清該 stage 的 note），
  透過 `stages.set_listener(cb)` 讓 `main.py` 在開始當下就 `_save_state()`；結束時依回傳 `status == "error"` 設 `error`／否則 `done`，併入回傳的 update。
  `run_node()` 直接呼叫 node 函式的路徑也要走同樣的 start/finish。
- `finish(state, stage, status, note=None)`：`note` 有值時一併寫入 `stage_notes[stage]`，回傳 `{"stages", "stage_notes"}`；未傳 `note` 時只回傳 `{"stages"}`，
  既有呼叫端（`_tracked()`、`run_node()`）行為不變。`stages`／`stage_notes` 的寫入一律經 `start()`／`finish()`，包含 runner 的中止（見 4. 執行管理），不在其他模組手刻。
- 開始時另印一行日誌標記 `@@AGENTLOOP_STAGE <stage>@@`（stdout，flush），供 runner 切分各階段日誌。
- 包裝函式只碰 `stages`／`stage_notes`，不改節點回傳的其他欄位，因此 `route_after_*` 與 `tests/test_workflow_entrypoints.py` 行為不變。

### 3. `main.py` 新增 `--change <name>`

`--node X --change <name>` 直接載入 `<target>/.agentloop/changes/<name>/state.json`，不顯示終端選單；名稱不存在時以錯誤結束（exit 1）。

### 4. 執行管理 `web/runner.py`

- 作用中執行只有一個（模組層 `RunManager` 單例＋`threading.Lock`）；啟動時若已有作用中執行 → 拋 `RunConflict(label)`，API 回 409。
- 執行目錄：`$AGENTLOOP_WEB_STATE_DIR/run/`（預設 `AgentLoop/.web/run/`，加入 `.gitignore`），內含 `meta.json`（run_id、kind、task、change_name、started_at、pid）、`output.log`、`question.json`、`answer.json`、`session.json`。
- 啟動：`subprocess.Popen([sys.executable, "-m", "AgentLoop.main", ...], cwd=REPO_ROOT, start_new_session=True, stdout=log, stderr=STDOUT, env=合併後設定＋AGENTLOOP_INTERACTION=web＋AGENTLOOP_RUN_DIR＋PYTHONUNBUFFERED=1)`。
  - 新增任務：`main "<task>"`；重跑：`main --node <stage> --change <name>`。
- change 名稱在新增任務時一開始未知：runner 定期掃描 `.agentloop/changes/*/state.json` 中 `task` 與 meta 相同、mtime 晚於 started_at 的 change 寫回 meta；在此之前列表以任務描述顯示暫時列。
- `claude_runner._run_claude_once` 在讀到第一個帶 `session_id` 的事件時，若設定了 `AGENTLOOP_RUN_DIR`，寫 `session.json`（`{stage, session_id}`）。
- 中止：`os.killpg(pgid, SIGTERM)`，5 秒後仍存在則 `SIGKILL`（總時限 10 秒內）；之後 runner 讀該 change 的 state.json，以 `state.update(stages.finish(state, 目前 stage, "error", note="使用者中止"))` 記錄錯誤與中止註記（不自行複製、改寫 `stages`／`stage_notes`），
  若 `session.json` 存在則依 `core.session.store_session(stage, id)` 覆寫 session 插槽，寫回 state.json，最後清空執行目錄。
- 執行結束（含正常結束）時：依 `@@AGENTLOOP_STAGE x@@` 標記切分 `output.log`，每段去 ANSI 後覆寫到 `<target>/.agentloop/changes/<name>/logs/<stage>.log`。
  執行中查詢日誌時直接從 `output.log` 即時切分。
- 回覆：`answer(question_id, text)`；無 question.json 或 id 不符 → `QuestionGone`（API 回 410）；`required` 且空白 → 422。

### 5. HTTP API（`web/app.py`，前綴 `/api`）

| Method | Path | 用途 |
| --- | --- | --- |
| GET | `/changes` | 執行中任務列表：`[{change_name, branch_name, task, iteration, stages, stage_notes}]`（排除 archive 內已有 `*-<name>` 資料夾者） |
| GET | `/changes/{name}/stages/{stage}` | 階段詳情：結果欄位（analysis、plan、human_feedback、status、execution_result、review_result、review_level）、note、日誌最後 500 行 |
| GET | `/changes/{name}/files`、`/changes/{name}/files/{path:path}` | 檢視 change 規格文件（限制在該 change 資料夾內，`.md`） |
| GET | `/run` | 作用中執行：`{active, run_id, label, change_name, task, stage, question}`；無則 `{active:false}` |
| POST | `/runs` | 新增任務 `{task}`（空白 → 422；衝突 → 409） |
| POST | `/changes/{name}/rerun` | `{stage}`，stage ∈ analyze_plan/execute/review/archive（其他 → 422；衝突 → 409） |
| POST | `/run/answer` | `{question_id, answer}`（410／422） |
| POST | `/run/abort` | 中止作用中執行 |
| GET | `/archive`、`/archive/{dir}/files`、`/archive/{dir}/files/{path:path}` | 已封存任務（資料夾名 `YYYY-MM-DD-<name>` 拆日期與名稱，名稱倒序） |
| GET | `/specs`、`/specs/{domain}` | 既有 Spec |
| POST | `/specs/search` | `{query}` → `{answer, references:[{path, doc_type}]}`；查無文件 → `{answer:"規格文件中沒有找到相關內容。", references:[]}`；失敗 → 502 `{detail}` |
| GET / PUT | `/settings` | GET 回 `{target_project, search_model, oauth_token:{set, last4}, api_key:{set, last4}, workspace_root, run_active}`；PUT secret 為空字串＝不變更；執行中改 target → 409 |
| GET | `/fs?path=<rel>` | 列出工作區根目錄下 `<rel>` 的子資料夾（排除 `.` 開頭）；解析後不在根目錄內 → 400「只能選擇工作區根目錄底下的資料夾」 |

- 所有「目標專案」相關路徑以 `Path.resolve()` 後 `is_relative_to(root)` 檢查，防止路徑穿越。
- FastAPI 以 `StaticFiles(directory=$WEB_DIST_DIR, html=True)` 提供前端；未設定或不存在時只提供 API。

### 6. 設定 `web/settings.py`

- 檔案：`AgentLoop/.web/settings.json`（權限 0600，`.web/` 加入 `.gitignore`）。鍵：`TARGET_PROJECT`、`SEARCH_MODEL`、`CLAUDE_CODE_OAUTH_TOKEN`、`ANTHROPIC_API_KEY`。
- 有效值＝settings.json 有值者優先，否則 `os.environ`（`.env` 已由 compose 的 env_file 注入）。啟動子行程與執行搜尋前把有效值放進 env（搜尋在網頁服務行程內執行時，以暫時覆寫 `os.environ` 的 context manager 呼叫 search 函式，並在 runner 鎖外以獨立鎖序列化）。
- `HOST_WORKSPACE_ROOT` 不可由網頁修改；工作區根目錄＝`lib.project_context.REPO_ROOT`。

### 7. 前端 `web/frontend/`

- Vue 3＋TypeScript＋`<script setup>`＋Vite；不引入 UI 元件庫，Markdown 以 `<pre>` 純文字呈現。
- 樣式：Tailwind CSS v4（devDependencies 加 `tailwindcss`、`@tailwindcss/vite`，`vite.config.ts` 的 `plugins` 加入 `tailwindcss()`），不寫 `tailwind.config.js`、不用 PostCSS 設定檔。
  新增 `src/style.css`：`@import "tailwindcss";` 後以 `@theme { --color-... }` 定義整個前端用到的完整色盤，由 `main.ts` 匯入。
  所有元件只能使用 theme 定義的色彩 token（例如 `bg-surface`、`text-fg`、`border-line`），不寫任意色碼（`bg-[#...]`）也不寫 `<style>` 區塊。色盤至少包含：
  - 主色：`primary`、`primary-hover`（分頁選中、主要按鈕）
  - 文字：`fg`（內文）、`fg-muted`（次要文字、說明、停用）
  - 背景：`bg`（頁面）、`surface`（卡片、對話框、詳情面板）、`surface-muted`（`<pre>` 日誌／規格全文區）
  - 邊框：`line`
  - 語意：`danger`（錯誤訊息、「使用者中止」註記、中止按鈕）、`warning`（等待回覆的驚嘆號）、`success`（「已儲存」）
  - 階段狀態：`stage-pending` `#9e9e9e`、`stage-running` `#1e88e5`、`stage-done` `#43a047`、`stage-error` `#e53935`（色碼固定、不可調整）
  其他 token 的色碼由實作決定，但須維持可讀對比。
- 全部元件（`App`、`ActiveChanges`、`ChangeRow`、`StageCard`、`StageDetail`、`QuestionForm`、`NewTaskDialog`、`FileBrowser`、`ArchivedChanges`、`ExistingSpecs`、`SpecSearch`、`SettingsPanel`、`FolderPicker`）
  都改用 Tailwind utility class 排版與上色；既有語意 class（如 `stage-card`、`error`、`aborted-note`、`question-mark`、`tab-button`、`active`）與 `data-*` 屬性保留，因為既有測試以它們定位元素。
- 結構：`src/api.ts`（所有 fetch，測試時以 `vi.mock` 取代）、`src/App.vue`（四個主分頁、未設定目標專案時自動開資料夾選擇器）、
  `components/ActiveChanges.vue`、`ChangeRow.vue`、`StageCard.vue`、`StageDetail.vue`、`QuestionForm.vue`、`NewTaskDialog.vue`、`FileBrowser.vue`、
  `ArchivedChanges.vue`、`ExistingSpecs.vue`、`SpecSearch.vue`、`SettingsPanel.vue`、`FolderPicker.vue`；`composables/usePolling.ts`（2 秒）。
- 狀態顏色：pending 灰 `#9e9e9e`、running 藍 `#1e88e5`、done 綠 `#43a047`、error 紅 `#e53935`（即 theme 的 `--color-stage-*`）。
  `StageCard.vue` 以一張「狀態 → class」對照表套用 `bg-stage-pending`／`bg-stage-running`／`bg-stage-done`／`bg-stage-error`（卡片文字用對比色），
  未知狀態退回 `bg-stage-pending`；卡片同時保留 `data-status` 屬性方便測試。
- 驚嘆號：`/run` 的 `question.stage` 與該列 change 相符（或暫時列）時，在對應卡片顯示。

### 8. 容器

- docker-compose：兩個目標相關掛載改為 `${HOST_WORKSPACE_ROOT}:${HOST_WORKSPACE_ROOT}`（同絕對路徑）；新增 `ports: ["127.0.0.1:8000:8000"]`；
  `command: python -m uvicorn AgentLoop.web.app:app --host 0.0.0.0 --port 8000`；`TARGET_PROJECT` 改為選填。
- Dockerfile：複製 `web/frontend` 到 `/opt/agentloop-web-src`，`npm ci && npm run build` 輸出到 `/opt/agentloop-web/dist`，設 `ENV WEB_DIST_DIR=/opt/agentloop-web/dist`
  （不能建在 AgentLoop 目錄內，因為執行時 AgentLoop 會被 bind mount 蓋掉）；`requirements.txt` 加 `fastapi`、`uvicorn[standard]`、`httpx`（TestClient 需要）。

## Architecture Decisions

### Decision: 以互動埠＋子行程執行接上既有工作流

見 `docs/adr/0001-web-gui-interaction-port-and-subprocess-run.md`。節點只換 I/O 出入口，提示詞、路由與判定規則不動；子行程讓中止可靠（kill process group）。

### Decision: 階段狀態寫進 state.json，由 workflow 包裝函式更新

命令列與網頁執行都會留下相同的階段紀錄，網頁不需推算。「階段開始即把其後各階段重設為尚未開始」一條規則同時涵蓋重跑與 review 退回重新規劃。

### Decision: 掛載整個工作區根目錄、設定檔優先於 .env

切換目標專案不需重建容器，資料夾選擇器才看得到其他專案；`HOST_WORKSPACE_ROOT` 必須在容器啟動前已知，所以留在 `.env`。

### Decision: 前端以 Tailwind CSS v4＋`@theme` 色盤統一樣式

原本前端完全沒有樣式，導致規格要求的四色階段狀態沒有做出來。改採 Tailwind v4，因為 `@tailwindcss/vite` 不需要 PostCSS／config 檔；所有色彩集中在 `src/style.css` 的 `@theme`，
元件只引用 token，換色只改一處，design 指定的四個狀態色碼也只在這裡出現一次。jsdom 不會計算 Tailwind 產生的 CSS，所以測試改斷言狀態對應的 class，色碼本身以 `@theme` 對照本文件。

### Decision: 中止的階段狀態寫入經 `stages.finish()`

`stages`／`stage_notes` 的單一事實來源是 `core/stages.py`。runner 中止時與 workflow 包裝函式一樣呼叫 `finish()`，並以新增的 `note` 參數寫入「使用者中止」，
避免 runner 另外手刻一份「複製後改寫」的邏輯，日後 `finish()` 規則改變時兩邊不一致。

### Decision: 同一目標專案同時只允許一個執行

各節點會 `git checkout` 共用的工作目錄，兩個執行並行會互相切走分支。不做排隊以維持簡單。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫（後端）**：FastAPI `TestClient` 打 `/api/*`，以 `tmp_path` 建立假的工作區根目錄（假 target、`.agentloop/changes/*/state.json`、`openspec/...`），
  執行子行程以假的 `python -m` 替身（測試用小腳本，模擬寫 question.json、輸出 stage 標記、睡眠等待被中止）取代真正的 workflow；search 的 `_ask_claude`／`_search` 以 monkeypatch 取代。
- **首選接縫（工作流）**：`build_workflow()` 編出的 app＋mock node（沿用 `tests/test_workflow_entrypoints.py` 的 `_tracker` 手法）驗證 `stages` 變化；
  `lib.interaction.ask` 以 monkeypatch `builtins.input`／`sys.stdin.isatty` 驗證 CLI 模式，以 tmp 執行目錄驗證 web 模式。
- **首選接縫（前端）**：Vitest＋@vue/test-utils 掛載 `App.vue` 或分頁元件，`vi.mock('../api')` 回傳固定資料，`vi.useFakeTimers()` 控制輪詢，斷言畫面文字、`data-status`、階段狀態色 class（`bg-stage-*`）、按鈕 disabled。
- **首選接縫（階段狀態寫入）**：`core/stages.py` 的 `finish()` 直接以 dict 呼叫，驗證帶 `note` 時回傳的 `stages`／`stage_notes`；runner 中止的端到端結果仍由既有假子行程測試驗證。
- **測試命名**：每個 Scenario 標題必須原字串出現在一個測試中（review 的追溯檢查以 grep 原字串比對）：Vitest 用 `test('<Scenario 標題>', ...)`；
  pytest 函式名無法含中文空白，改把 Scenario 標題放在該測試函式 docstring 的第一行。
- **次要接縫**：無（不做瀏覽器 E2E；容器啟動以手動 `docker compose up` 驗證）。

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| 開啟網頁後顯示四個主分頁且預設選中執行中任務 | 四標籤依序、預設選中、點設定可切換 | Vitest `App.vue`：標籤文字順序、active class |
| 執行中任務分頁為每個未封存的 change 顯示一列階段卡片（feat-login 執行中、fix-typo 已封存） | 一列、五卡片顏色依序 綠/綠/藍/灰/灰（done/done/running/pending/pending） | pytest `/api/changes` 只回 feat-login；Vitest `ActiveChanges.vue` 的 `data-status` 與 class 依序含 `bg-stage-done`/`bg-stage-done`/`bg-stage-running`/`bg-stage-pending`/`bg-stage-pending` |
| 沒有任何執行中任務時顯示空狀態與新增任務入口 | 「目前沒有執行中的任務」＋新增任務按鈕 | Vitest |
| 工作流推進時各階段狀態依序由尚未開始轉為執行中再轉為完成 | listener 收到 running→done 序列並存檔 | pytest workflow＋mock node |
| 階段結束且結果為錯誤時該階段記為錯誤且後續階段維持尚未開始 | execute=error，review/archive=pending | pytest |
| review 退回重新規劃時 analyze_plan 之後的階段重設為尚未開始 | 第二次 analyze_plan 開始時後四階段 pending、iteration+1 | pytest |
| 沒有階段狀態紀錄的舊任務以尚未開始顯示所有階段 | 缺 `stages` → 全 pending，四張卡有重跑 | pytest `/api/changes`；Vitest 卡片 |
| 點擊卡片後顯示該階段的執行結果與執行日誌（800 行含 ANSI） | 回 301–800 行、無 `\x1b` | pytest `/api/changes/{n}/stages/review`；Vitest 顯示審查等級 |
| 被使用者中止的階段在詳情顯示使用者中止 | 頂端「使用者中止」、空欄位「（尚無資料）」 | Vitest `StageDetail.vue` |
| 從任務列開啟該 change 的規格文件 | 檔案排序 proposal→tasks→specs/...、顯示全文 | pytest files API 排序；Vitest `FileBrowser.vue` |
| 階段等待人工回覆時卡片顯示驚嘆號並可在詳情中回覆（選項 1） | 驚嘆號→點選項 1→`answer("1")`→驚嘆號消失 | Vitest；pytest web 互動埠收到 "1" |
| 人工確認關卡可在網頁確認執行或送出修改意見 | 否＋「改用 Flask」→ needs_revision；是 → confirmed | pytest：web 互動埠＋`human_confirm_node` 回傳值 |
| 用量上限暫停時可在網頁選擇繼續或中止 | 「繼續」→ 以 session 續跑；顯示錯誤訊息 | pytest：mock `_run_claude_once` 先回 limit error，web 回覆 `""` 後第二次 cmd 含 `--resume` |
| 以命令列執行工作流時提問仍在終端回覆 | CLI 模式 `input()` 被呼叫、提示文字同原本、無 question.json | pytest |
| 必填文字題送出空白時不送出並提示必填 | API 422、answer.json 未建立；畫面「此欄位為必填」 | pytest＋Vitest `QuestionForm.vue` |
| 提問已被回覆後再送出回覆時顯示提問已結束 | API 410；畫面「此提問已結束，請重新整理」 | pytest＋Vitest |
| 使用者中止執行中的階段後該階段標為錯誤並保留 session 供重跑接回 | 10 秒內 pid 消失、stages.execute=error、note、session 插槽=execute/abc123 | pytest runner＋假子行程；pytest `stages.finish(state, "execute", "error", note="使用者中止")` 回傳 `stages.execute=error`、`stage_notes.execute="使用者中止"`，且不帶 note 時回傳不含 `stage_notes` |
| 重跑某階段時從該階段開始並接續後續流程 | 子行程參數 `--node execute --change feat-login`；只有四張卡有重跑 | pytest rerun API；Vitest 重跑按鈕位置 |
| 已有執行進行中時其他啟動動作停用並顯示原因 | 所有重跑與新增任務 disabled、title 文字 | Vitest |
| 執行進行中再送出啟動要求時系統拒絕 | 409、原子行程仍在；畫面顯示原因 | pytest＋Vitest |
| 新增任務後以 analyze_plan 卡片引導初始提問 | 暫時列以任務描述為標題、驚嘆號、找到 change 後標題變 feat-login | pytest runner change 偵測；Vitest 暫時列 |
| 任務描述為空白時無法送出新增任務 | 送出按鈕 disabled；API 對空白回 422 | Vitest＋pytest |
| 已封存任務分頁每個封存 change 一列並可瀏覽其文件 | 日期/名稱拆解、倒序、檔案排序 | pytest `/api/archive`；Vitest |
| 沒有任何封存任務時顯示空狀態 | 「目前沒有已封存的任務」 | Vitest |
| 既有 Spec 分頁列出每個 domain 並可檢視其規格內容 | auth、billing 排序與全文 | pytest `/api/specs`；Vitest |
| 輸入問題搜尋規格後顯示回答與參考檔案 | 搜尋中狀態、回答、≤5 參考 | pytest（monkeypatch search）；Vitest |
| 規格中找不到相關內容時顯示查無結果訊息 | 固定訊息、未呼叫 `_ask_claude` | pytest＋Vitest |
| 搜尋失敗時顯示錯誤訊息並保留查詢文字 | 502＋「搜尋失敗：…」、輸入框保留 | pytest＋Vitest |
| 設定分頁顯示目前設定並可儲存 | 合併優先序、末四碼、PUT 後 GET 反映、搜尋 env 用新值 | pytest settings API；Vitest |
| 認證欄位留空儲存時保留原本的值 | PUT 空字串後 last4 不變 | pytest |
| 有執行進行中時無法變更目標專案 | PUT target 409；欄位 disabled＋說明 | pytest＋Vitest |
| 尚未指定目標專案時開啟資料夾選擇器並以選定資料夾作為目標專案 | `/api/fs` 排除 `.cache`；自動開啟選擇器、確定後 PUT | pytest＋Vitest `App.vue` |
| 選擇工作區根目錄以外的路徑時拒絕並提示 | `../etc` → 400 與固定訊息、設定未寫入 | pytest |

## Technical Debt & Follow-up Notes

- 以輪詢取代 WebSocket；日誌量大時每 2 秒重讀檔案尾端，之後可改 SSE。
- 搜尋在網頁服務行程內以暫時覆寫 `os.environ` 執行（search.py 讀環境變數），需序列化；之後可把 search.py 改成接收參數的函式介面。
- 新增任務時以 `task` 字串＋mtime 比對找出 change 名稱，屬於推測式關聯；之後可讓 analyze_plan 把 change 名稱寫進執行目錄。
- 無登入驗證，安全性完全依賴 compose 只綁定 127.0.0.1；若要開放遠端存取必須先補驗證。
- 中止使用 SIGTERM/SIGKILL，節點中途被殺可能留下半套的檔案修改（與 CLI 按 Ctrl-C 相同風險）。
- 顏色只能由 class 斷言間接驗證（jsdom 不計算 Tailwind CSS），實際呈現仍需在 `npm run build` 後以瀏覽器目視確認。
