# Proposal: 網頁圖形化控制台（v0.5.0）

## Intent

規範目的：在不改變任何節點（analyze_plan、human_confirm、execute、review、archive）的提示詞、路由與判定規則的前提下，
於現有容器內提供一個網頁控制台，讓使用者不必進終端、不必記指令，就能：

1. 一眼看出每個任務（change）走到哪個工作階段、每個階段是尚未開始／執行中／完成／錯誤；
2. 在網頁上回覆工作流的所有提問（分支名稱、是否寫 spec、domain、grilling、人工確認、review 建議挑選、archive 確認、用量上限暫停），
   並能中止目前階段或從可單獨執行的階段重跑；
3. 瀏覽已封存的任務與目標專案的既有 Spec，並以語意搜尋查詢規格；
4. 在網頁上設定目標專案、搜尋模型與 Claude 認證，未指定目標專案時以資料夾選擇器挑選。

規範背景：目前所有操作都靠 `docker exec` 進容器下 `python -m AgentLoop.main` 指令，提問以終端 `input()` 回覆，
`.env` 決定目標專案且只掛載單一資料夾；state.json 只記整體 `status`，沒有各工作階段各自的狀態，
所以使用者難以掌握多個任務的進度。命令列用法必須維持可用，網頁只是另一個操作入口。

## Scope

In scope:

- 新增網頁服務（FastAPI 後端＋Vue 3／Vite 前端），容器啟動即提供，僅綁定 host 的 `127.0.0.1:8000`
- 最外層四個分頁：執行中任務、已封存任務、既有 Spec、設定
- 執行中任務：每個未封存 change 一列、每個工作階段一張卡片（四色狀態、等待回覆驚嘆號、重跑、中止、檢視 change 規格文件），
  卡片詳情顯示該階段結果與執行日誌；新增任務入口
- 「互動埠」：所有節點提問改經單一介面，命令列行為不變、網頁模式改為待回覆提問
- 各工作階段狀態寫進 state.json（命令列與網頁執行共用）
- 執行管理：同一目標專案同時只允許一個執行、以子行程執行工作流、中止時保存 Claude session 供重跑接回
- 已封存任務：列出目標專案 `openspec/changes/archive/` 的每個封存 change，可唯讀瀏覽其文件
- 既有 Spec：列出 `openspec/specs/` 各 domain 並可檢視，提供呼叫 search 的語意搜尋
- 設定：接管 `TARGET_PROJECT`、`SEARCH_MODEL`、`CLAUDE_CODE_OAUTH_TOKEN`、`ANTHROPIC_API_KEY`（設定檔優先於 `.env`），
  未指定目標專案時開啟資料夾選擇器；`HOST_WORKSPACE_ROOT` 仍留在 `.env`
- docker-compose 改掛載整個工作區根目錄、對外埠與啟動指令；Dockerfile 加前端建置
- `main.py` 新增 `--change <name>` 讓 `--node` 可不經終端選單直接指定 change
- 同步更新 ARCHITECTURE.md、README.md、CLAUDE.md

Out of scope:

- 任何節點的 `_SYSTEM` 提示詞、grilling／review 判定、LangGraph 路由規則的修改
- 登入驗證、多使用者、遠端（非本機）存取
- 多個目標專案同時執行、執行排隊
- 在網頁上編輯 OpenSpec 文件或程式碼
- WebSocket 即時推送（以輪詢更新）

## Approach

- **互動埠**（`lib/interaction.py`）：`ask(kind, prompt, options, stage, ...)`；命令列實作逐字保留現有提示與 `input()`／EOF／非 TTY 行為，
  網頁實作（環境變數 `AGENTLOOP_INTERACTION=web`）把提問寫成執行目錄下的 `question.json`、輪詢 `answer.json` 取得回覆。
  節點內所有 `input()` 與 `sys.stdin.isatty()` 改呼叫互動埠，提問文字與預設值規則原封不動。見 `docs/adr/0001-...`。
- **階段狀態**：`build_workflow()` 以包裝函式在每個節點開始／結束時更新 state 的 `stages`，由 `main.py` 既有的存檔流程寫入 state.json；
  一個階段開始時，其後各階段重設為尚未開始（同時涵蓋重跑與 review 退回重新規劃）。
- **執行管理**（`web/runner.py`）：以 `subprocess.Popen(start_new_session=True)` 執行 `python -m AgentLoop.main`，輸出寫入執行日誌；
  中止時對 process group 送 SIGTERM（逾時再 SIGKILL），並把 claude_runner 即時記下的 session id 依 `core/session.py` 的單一插槽規則寫回 state.json。
- **HTTP API**（`web/app.py`，FastAPI＋uvicorn）提供列表、詳情、執行、回覆、中止、重跑、檔案瀏覽、搜尋、設定、資料夾瀏覽；同時提供前端靜態檔。
- **前端**（`web/frontend/`，Vue 3＋TypeScript＋`<script setup>`＋Vite，測試用 Vitest＋@vue/test-utils），每 2 秒輪詢；
  樣式採 Tailwind CSS v4，整個前端用到的色盤（含四個階段狀態色）集中定義在 `@theme`，元件只引用 theme token。
- **搜尋**：重用 `search.py` 的索引／檢索／回答函式，回傳回答文字與參考檔案清單。
- 詳細技術方案、API 清單與測試接縫見 `design.md`。
