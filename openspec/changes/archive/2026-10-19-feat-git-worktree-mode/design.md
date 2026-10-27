# Design: 以 git worktree 讓多個任務同時執行

## Technical Approach

### 1. 任務工作目錄（`lib/git_ops.py`）

- `worktree_dir(project_dir, change_name) -> str`：回傳相對工作區根目錄（`REPO_ROOT`）的路徑 `.agentloop-worktrees/<project_dir>/<change_name>`。路徑完全由這兩個欄位決定，`AgentState` 不新增路徑欄位；`project_dir` 維持指向主工作目錄。`.agentloop-worktrees` 以點開頭，`project_context.list_project_docs()` 與 `web/settings.py` 的資料夾列舉都已略過點開頭目錄，不需修改。
- `ensure_worktree(project_dir, change_name, branch_name) -> (ok, msg)`（取代 `ensure_on_branch`）：
  1. 任務工作目錄已存在且是該 repo 的 worktree、簽出 `branch_name` → 成功，不做事。
  2. `branch_name` 是主工作目錄目前所在分支 → 失敗，訊息固定為「分支 <branch_name> 正在主工作目錄使用中，請先將主工作目錄切換到其他分支（未提交變更請先 commit 或 stash）」。
  3. `branch_name` 已被其他 worktree 簽出（`git worktree list --porcelain` 比對）→ 失敗並附 git 訊息。
  4. 本地已有 `branch_name` → `git worktree add <abs path> <branch_name>`；本地沒有 → 從目前主工作目錄 HEAD `git worktree add -b <branch_name> <abs path> HEAD`（維持原 `ensure_on_branch`「沒有就從 HEAD 建立」的語意）。
  - 建立前 `git worktree prune`，清掉被手動刪除資料夾留下的殘留紀錄。
- `create_worktree_from(project_dir, change_name, branch_name, base_branch) -> (ok, msg)`（取代 `create_branch_from`，主工作目錄不 checkout、不 pull）：
  1. 取 `base_branch` 的 upstream（`git rev-parse --abbrev-ref --symbolic-full-name <base>@{u}`）。沒有 upstream → 起點為本地 `base_branch`，訊息註明略過同步。
  2. 有 upstream（例如 `origin/main`）→ `git fetch <remote> <base 的遠端分支名>`。成功 → 起點為 `origin/main`。
  3. fetch 失敗（認證、網路、逾時皆同）但本地 `refs/remotes/origin/main` 存在 → 起點仍為 `origin/main`，訊息註明「容器內無法連線遠端、改用本地的遠端追蹤分支 origin/main」並附 git 錯誤。
  4. fetch 失敗且本地沒有該遠端追蹤 ref → 失敗，不建立分支與 worktree。
  5. `git worktree add --no-track -b <branch_name> <abs path> <起點>`。
- `rollback_except_openspec(project_dir, change_name)`：改在任務工作目錄執行（行為不變）。
- `commit_all(project_dir, change_name, message) -> (ok, msg)`：任務工作目錄 `git add -A` 後 `git commit -m <message>`；不 push。
- `remove_worktree(project_dir, change_name) -> (ok, msg)`：`git worktree remove <abs path>`（不加 `--force`，commit 後應已乾淨；若仍有殘留則失敗回報），工作分支保留。
- `list_branch_files()`／`read_branch_file()`／`list_local_branches()`／`branch_exists()` 維持在主工作目錄 repo 執行（refs 與所有 worktree 共用）。
- 移除 `ensure_on_branch()`、`create_branch_from()` 及其 `lib/__init__.py` 匯出。

### 2. 同一任務同時最多一個執行（`core/change_lock.py`，新檔）

- `acquire(project_dir, change_name) -> (ok, msg)`：對 `<主工作目錄>/.agentloop/changes/<change_name>/run.lock` 以 `fcntl.flock(LOCK_EX | LOCK_NB)` 上鎖，檔案描述子存在模組層，行程結束（含被 SIGKILL）時由 OS 自動釋放，不需清理。取不到鎖 → 失敗訊息「任務 <change_name> 已有執行進行中」。
- 上鎖時機：`main.py` 的 `run_node()` 載入 state 後立即上鎖；完整工作流的新任務在 `analyze_plan` 決定 change 名稱之後、建立 worktree 之前上鎖（同一行程重複呼叫視為成功）。取不到鎖 → 該節點回傳 `status: "error"` 結束。
- 這層同時保護 CLI 與網頁；網頁另在 `RunManager` 先擋（見下），讓按鈕即時停用、API 回 409。

### 3. 節點改在任務工作目錄操作

- 共同：`work_dir = worktree_dir(project_dir, change_name)`；原本 `os.path.join(REPO_ROOT, project_dir, "openspec", ...)`、`git diff HEAD`、`openspec` CLI 的 `cwd`、`build_project_doc_hint_for()` 一律改用 `work_dir`；`.agentloop/changes/...`（state、logs）仍用 `project_dir`。
- `analyze_plan`：初始規劃原本 `create_branch_from`／`ensure_on_branch` 的呼叫點改為上鎖 → `create_worktree_from`／`ensure_worktree`；其餘模式（human-revise／replan／adjustment）呼叫 `ensure_worktree`。prompt 中「目標專案目錄」與「OpenSpec Change 位置」改指 `work_dir`。已封存判定（`_is_archived`）改為：state 的 `archived` 為 True，或主工作目錄依舊規則判定已封存（相容舊任務）。
- `execute`：`ensure_worktree` 後執行。prompt 改指 `work_dir`，並告知主工作目錄路徑：由 Agent 視情況決定沿用主工作目錄的未追蹤相依檔（如符號連結 `node_modules`）或在 worktree 內重新安裝。另要求最後輸出一行 `COMMIT_MESSAGE: <訊息>`，訊息格式依該專案 `git log` 的慣例（例如 `feat: git worktree mode`），且不得自行 commit。節點以 `^COMMIT_MESSAGE:\s*(.+)$`（多行模式、取最後一個）解析：有值則寫入 `state["commit_message"]`；沒有則保留原值並印警告。依 CLAUDE.md「Keep prompts from growing」，新句子須與既有「目標專案路徑／分支」段落合併，並刪除同義舊句，`_SYSTEM` 實質長度不增加。
- `review`：`ensure_worktree` 後在 `work_dir` 跑 `git diff HEAD`；prompt 路徑改指 `work_dir`。
- `archive`（`nodes/archive.py`）：
  1. `ensure_worktree` 失敗 → 回傳 `status: "error"`。
  2. 詢問是否 archive（現有 `_ask_should_archive`），答否 → 與現行相同只印提示、階段完成，不 commit、不移除。
  3. 若 `is_change_archived(work_dir_abs, change_name)` 已為 True（前次 archive 成功但 commit 失敗）→ 略過 `openspec archive`，直接進第 4 步；否則呼叫 `archive_change(work_dir_abs, ...)`，失敗 → 與現行相同只印警告、階段完成。
  4. `state["commit_message"]` 為空 → 回傳 `status: "error"`，`stage_notes["archive"]`／日誌註明「沒有任務 commit 訊息，未 commit、保留任務工作目錄 <路徑>；請重跑 execute 產生 commit 訊息後再重跑 archive」。
  5. `commit_all` 失敗 → 回傳 `status: "error"` 並附 git 訊息，worktree 保留。
  6. `commit_all` 成功 → `remove_worktree`；不論移除成功與否都寫 `archived: True`（移除失敗只印警告並附路徑，因為變更已安全 commit）。
- `AgentState`（`core/state.py`）新增 `commit_message: str`（預設 ""）、`archived: bool`（預設 False）；`main.py` 的 `_empty_state()` 一併補上，舊 state.json 缺欄位時以預設值讀取。

### 4. 網頁多執行管理（`web/runner.py`）

- `RunManager` 由單一 `_handle` 改為 `dict[run_id, _RunHandle]`，仍以一把 `Lock` 保護。執行目錄改為 `$AGENTLOOP_WEB_STATE_DIR/runs/<run_id>/`（內容與現行 `run/` 相同）。
- `start_new_task(task)`：永不因其他執行而拒絕。
- `start_rerun(change_name, stage)`：若有任何執行的 `change_name` 等於它 → `RunConflict(change_name)`，API 回 409、`detail` 為「<change_name> 執行中」。
- change 名稱取得：子行程在 `main._save_state()` 時，若設有 `AGENTLOOP_RUN_DIR` 則寫 `<run_dir>/change.json`（`{"change_name": ...}`）；`RunManager` 讀此檔取得，取代以任務描述＋mtime 掃描的 `_detect_change_name`（兩個相同描述的新任務並行時舊方法會認錯）。
- `status()` → `runs()`：回傳所有執行中的清單 `[{run_id, change_name, task, stage, question}]`。
- `answer(run_id, question_id, text)`、`abort(run_id)`：只作用於指定執行；中止與日誌持久化邏輯不變，只是路徑來自該 run 的 handle。
- `live_stage_log(change_name, stage)`：在所有 handle 中找 `change_name` 相符者。
- `is_active()`：任一執行存在即 True（供設定頁禁止變更目標專案）。

### 5. HTTP API（`web/app.py`）

| 舊                     | 新                                          | 說明                                       |
| ---------------------- | ------------------------------------------- | ------------------------------------------ |
| `GET /run`             | `GET /runs`                                 | 回傳執行清單（陣列，空陣列＝沒有執行）     |
| `POST /runs`           | `POST /runs`（不變）                         | 新增任務不再回 409                         |
| `POST /changes/{name}/rerun` | 不變                                  | 只有同一任務已有執行時回 409              |
| `POST /run/answer`     | `POST /runs/{run_id}/answer`                | body 不變                                  |
| `POST /run/abort`      | `POST /runs/{run_id}/abort`                 |                                            |

`GET/PUT /settings` 的 `run_active` 語意不變（任一執行存在）。

### 6. 前端（`web/frontend/src`）

- `api.ts`：`RunStatus` 改為 `RunInfo { run_id, change_name, task, stage, question }`，`getRuns(): Promise<RunInfo[]>`；`postAnswer(runId, questionId, answer)`、`postAbort(runId)`。
- `ActiveChanges.vue`：輪詢 `getRuns()`；每個 `change_name` 為空的執行產生一列暫時列（以 `run_id` 為 key）；「新增任務」按鈕不再因執行而停用。每列傳入「屬於這列的執行」（依 `change_name` 對應；暫時列直接是該執行），沒有則為 null。
- `ChangeRow.vue`：prop 由 `runStatus` 改為 `run: RunInfo | null`；重跑停用條件改為「本列有執行」，停用原因「<change 名稱> 執行中」；待回覆提問、驚嘆號、呼吸光暈、中止都只看本列的 `run`，回覆與中止帶 `run.run_id`。
- `StageDetail.vue`／`QuestionForm.vue`：中止與回覆改用傳入的 `run_id`。

### 7. repo_view

- `list_active_changes()`：排除 state `archived` 為 True 者，以及主工作目錄依舊規則判定已封存者（舊任務）。
- `list_change_files()`／`read_change_file()`：讀取順序改為「任務工作目錄 → 主工作目錄（舊任務）→ 工作分支最新 commit（既有 git 唯讀後備）」。`_resolve_change_source` 先檢查 `<REPO_ROOT>/<worktree_dir>/openspec/changes/<change>/`，存在即回 `_WorktreeSource`；每次請求即時讀檔，不快取，因此能看到任務工作目錄中尚未 commit 的最新內容。日誌（`get_stage_detail`）路徑不變。
- 未合併封存任務（「已封存任務」分頁）：
  - `list_archive(project)` 每筆新增 `branch` 欄位（一般封存為 `""`）。先照舊列出主工作目錄 `openspec/changes/archive/` 的資料夾；再掃描 `.agentloop/changes/*/state.json` 中 `archived` 為 True、`branch_name` 非空且 `branch_exists` 的任務，對其工作分支呼叫 `list_branch_files(project, branch, "openspec/changes/archive")`，取出第一層資料夾名稱中符合 `_ARCHIVE_DIR_RE` 且 change 名稱等於該任務者；若主工作目錄已有同名資料夾（已合併）則略過，否則加入 `{"dir", "date", "name", "branch": <工作分支>}`。合併後依 `dir` 由新到舊排序（日期前綴決定順序）。工作分支不存在或 `ls-tree` 失敗時略過該任務、不拋錯。
  - `list_archive_files(project, dir_name)`／`read_archive_file(...)`：主工作目錄有該資料夾 → 照舊讀檔；否則以同上規則找出 `dir` 相符的未合併封存任務，改用 `list_branch_files`／`read_branch_file` 從其工作分支讀 `openspec/changes/archive/<dir>/`；找不到 → `NotFound(找不到封存：<dir>)`。檔案排序沿用 `_sort_markdown_paths`；讀取時 `rel_path` 必須在列出的檔案清單中，避免路徑穿越。
  - 前端 `api.ts` 的 `ArchiveRow` 新增 `branch: string`；`ArchivedChanges.vue` 在 `branch` 非空時於名稱後顯示標籤「未合併 · <branch>」；`FileBrowser` 與 HTTP 端點（`GET /archive`、`/archive/{dir}/files`、`/archive/{dir}/files/{path}`）不變。

### 8. 文件

- `ARCHITECTURE.md`：「已封存任務」未合併封存任務的列出與讀取規則、目錄結構（git_ops、runner、change_lock）、`AgentState` 欄位、「檔案系統作為共享記憶」表（OpenSpec Change 路徑改為任務工作目錄）、`git_ops` 說明、archive 節點與流程圖說明（commit＋移除 worktree）、「執行管理」（多執行、`runs/<run_id>/`、`change.json`）、HTTP API 表、前端段落、容器化層「仍只支援單一目標專案同時執行」一句改為「同一目標專案可多任務並行、仍只支援單一目標專案」、「Git Diff 作為稽核媒介」改為在任務工作目錄執行。
- `README.md` 安裝與使用：說明任務工作目錄位置、主工作目錄不被切換、多任務並行、archive 會 commit（不 push）並移除 worktree、未合併封存任務在「已封存任務」以「未合併 · <工作分支>」標示並可從工作分支閱讀文件。
- `CONTEXT.md`、`docs/adr/0002-change-worktree-and-commit-on-archive.md`：規劃階段已更新。

## Architecture Decisions

### Decision: 每個任務一律使用專屬 worktree，位置固定在工作區根目錄的隱藏資料夾

不提供開關，CLI 與網頁一致；放在 `<工作區根目錄>/.agentloop-worktrees/<目標專案>/<change 名稱>/`，避免要求目標專案 gitignore、也不被專案偵測與資料夾選擇器誤認。工作區根目錄已整個掛進容器，路徑與宿主相同，不需改 `docker-compose.yml`。見 ADR 0002。

### Decision: 執行狀態紀錄留在主工作目錄

網頁從單一位置列出所有任務；worktree 移除後紀錄仍在。worktree 路徑由 `project_dir` + `change_name` 推得，不另存欄位。

### Decision: execute 只擬 commit 訊息，archive 成功後才 commit 並移除 worktree

execute 沒有 commit 行為，移除 worktree 前必須 commit 才不丟成果；訊息由最了解改動內容的 execute Agent 依專案慣例產生。缺訊息或 commit 失敗時任務不算已封存、archive 記為錯誤，重跑 archive 只補做 commit 與移除。

### Decision: 未合併封存任務從工作分支唯讀顯示，與一般封存混排

任務工作目錄在封存後即移除，合併前主工作目錄看不到封存資料夾；與其讓任務留在「執行中任務」，改在「已封存任務」以「未合併 · <工作分支>」標籤列出，並沿用既有 `git ls-tree`／`git show` 唯讀讀取（不 checkout），API 路徑不變、只多一個 `branch` 欄位。合併後以主工作目錄為準去重。

### Decision: 同一任務的互斥以檔案鎖實作

網頁 `RunManager` 只知道自己啟動的執行，CLI 與網頁同時對同一任務啟動、或兩個新任務選了同一分支時都擋不到；`flock` 隨行程結束自動釋放，不會留下需人工清除的殘鎖。

### Decision: 起點分支只 fetch、不更新本地分支

主工作目錄永遠不切換分支，因此不能再 `checkout base && pull`；以遠端追蹤分支為起點即可取得最新版本。fetch 失敗時退回本地既有的遠端追蹤 ref（容器內常無遠端認證）。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫**：
  - `lib/git_ops.py` 的公開函式，對 `tmp_path` 下真實建立的 git repo（含一個 bare repo 當遠端）操作，斷言 `git worktree list`、分支、主工作目錄 HEAD 與檔案狀態（延續 `tests/test_git_ops.py` 做法）。
  - `web/runner.RunManager` 公開方法，以假的 `MAIN_CMD`（短命 Python 子行程）啟動多個執行（延續 `tests/test_web_runner.py`）。
  - `web/app.py` HTTP 端點（`TestClient`，延續 `tests/test_web_app.py`）。
  - 節點函式（`execute_node`、`archive_node`、`analyze_plan` 初始規劃）以 patch `call_claude`／`interaction.ask` 方式呼叫（延續 `tests/test_node_guards.py`、`tests/test_analyze_plan_base_branch.py`）。
  - 前端 `ActiveChanges`／`ChangeRow` 以 `vi.mock('../api')` 掛載（延續 `ActiveChanges.spec.ts`）。
- **次要接縫**：`core/change_lock.acquire()` 以兩個子行程驗證互斥與行程結束後自動釋放。

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| 範例 1：新任務、本地無 `feat/login`、起點 `main` 有 upstream 且 fetch 成功 | 建立 `.agentloop-worktrees/<proj>/feat-login`，簽出 `feat/login`，起點等於 `origin/main` 最新 commit；主工作目錄 HEAD 與未提交檔不變 | `create_worktree_from` 回 `(True, …)`；worktree HEAD == 遠端最新 sha；主目錄 `rev-parse --abbrev-ref HEAD` 不變 |
| 範例 4：fetch 失敗、本地有 `origin/main` | 以本地 `origin/main` 建立；訊息含「容器內無法連線遠端、改用本地的遠端追蹤分支 origin/main」 | 回 `(True, msg)`，`msg` 含該字串 |
| fetch 失敗、本地無遠端追蹤 ref | 不建立分支與 worktree | 回 `(False, …)`；`branch_exists` 為 False；worktree 目錄不存在 |
| 起點分支無 upstream | 直接以本地起點分支建立、不 fetch | 回 `(True, msg)`，msg 註明略過同步 |
| 範例 6：工作分支為主工作目錄目前分支 | 失敗，訊息為固定文字 | `ensure_worktree` 回 `(False, "分支 feat/old 正在主工作目錄使用中，請先將主工作目錄切換到其他分支（未提交變更請先 commit 或 stash）")` |
| 任務工作目錄已存在且簽出正確分支 | 成功、不重建 | 回 `(True, …)`；目錄內既有未提交檔仍在 |
| 分支已被其他 worktree 簽出 | 失敗 | 回 `(False, …)` |
| 範例 2：兩個新任務先後啟動 | 兩個執行同時存在、各有執行目錄；`runs()` 回兩筆 | `len(runs()) == 2`；第二次 `start_new_task` 不拋 `RunConflict` |
| 範例 2：`feat-login` 執行中再重跑 `feat-login` | 拒絕 | `RunConflict`；API 409，`detail` 為「feat-login 執行中」 |
| `feat-login` 執行中重跑 `fix-css` | 啟動成功 | 不拋例外，`runs()` 含兩筆 |
| 回覆／中止指定執行 | 只影響該 run；另一 run 的 question.json 與行程不受影響 | 另一 run 的子行程仍存活、其 question.json 仍在 |
| 子行程寫 `change.json` | `runs()` 該筆 `change_name` 即為檔案內容 | `runs()[i]["change_name"] == "feat-login"` |
| 同一任務第二個行程上鎖 | 失敗訊息「任務 feat-login 已有執行進行中」；第一個行程結束後可上鎖 | `acquire` 回值 |
| 範例 3：execute 輸出含 `COMMIT_MESSAGE: feat: login page` | state `commit_message == "feat: login page"` | `execute_node` 回傳 dict |
| execute 輸出無 COMMIT_MESSAGE、state 已有舊訊息 | 保留舊訊息 | 回傳 dict 不含或等於舊值 |
| 範例 3：archive 同意、openspec 成功、有訊息 | worktree 內 commit 一筆訊息相符；worktree 移除；分支仍在；`archived: True` | `git log -1 --format=%s feat/login`；目錄不存在；`branch_exists` |
| archive 同意、openspec 成功、無訊息 | 未 commit、worktree 保留、`archived` 非 True、`status: "error"` | 回傳 dict；worktree 目錄存在 |
| 前次已 archive 但未 commit，補上訊息後重跑 archive | 不再呼叫 `openspec archive`；commit 並移除；`archived: True` | `archive_change` mock 未被呼叫 |
| 使用者答不 archive | 不 commit、不移除、不標記 | worktree 存在；`archived` 非 True |
| `list_active_changes`：state `archived: True` | 不列出 | 回傳不含該 change |
| 範例 5：兩個任務各有任務工作目錄，`fix-css` 的 proposal.md 尚未 commit | 讀各自 worktree 的最新內容，互不混淆 | `GET /changes/fix-css/files/proposal.md` 回 fix-css worktree 內未 commit 的內容；`feat-login` 回其 worktree 內容 |
| 任務工作目錄已移除、主工作目錄也無 change 資料夾 | 退回讀工作分支最新 commit | `read_change_file` 回分支上的檔案內容 |
| 範例 3：state `archived: True`、工作分支上有 `openspec/changes/archive/2026-10-19-feat-login/`、主工作目錄沒有 | `GET /archive` 含 `{dir: "2026-10-19-feat-login", date: "2026-10-19", name: "feat-login", branch: "feat/login"}`，與一般封存列依日期由新到舊混排；`/archive/2026-10-19-feat-login/files` 列出分支上的檔案、可讀內容 | API 回傳陣列順序與欄位；檔案內容等於分支 commit 內容 |
| 範例 3：工作分支已合併（主工作目錄有同名封存資料夾） | 只出現一筆、`branch` 為 `""`，讀主工作目錄 | `GET /archive` 該 `dir` 只出現一次 |
| state `archived: True` 但工作分支已被刪除 | 不列出、不拋錯 | `GET /archive` 不含該任務；HTTP 200 |
| 前端：`ArchiveRow.branch` 為 `feat/login` | 名稱後顯示「未合併 · feat/login」；`branch` 為空的列無標籤 | DOM 文字斷言 |
| 前端：兩個執行（一個 `feat-login`、一個無 change 名稱「修正樣式」） | 顯示 `feat-login` 列與「修正樣式」暫時列；`feat-login` 重跑停用且 title 為「feat-login 執行中」；其他列重跑與「新增任務」可用 | DOM 斷言 |
| 前端：兩列各有待回覆提問 | 兩列各自驚嘆號；在一列回覆時以該列 `run_id` 呼叫 `postAnswer` | `postAnswer` 被呼叫參數 |

## Technical Debt & Follow-up Notes

- 本 change 依使用者決定 `skip_specs: true`，未更新 `openspec/specs/web-gui/spec.md`；其中 Requirement「同時只允許一個執行」（及其兩個 Scenario）、「新增任務」的「目前沒有執行進行中」前提、Scenario「已有執行進行中時其他啟動動作停用並顯示原因」等描述將與實作不符，需另開 change 修正既有 Spec。
- 目標專案若以固定容器名稱／埠跑 `docker compose`，並行任務仍會衝突。
- 執行狀態紀錄留在主工作目錄；工作分支合併前「既有 Spec」看不到剛封存任務併入的內容（「已封存任務」已以未合併封存任務呈現）。
- 未合併封存任務依賴 state.json 的 `archived` 與 `branch_name`；主工作目錄的 `.agentloop/` 被清除時就不會列出。
- 只有 analyze_plan 初始規劃與 `--node` 入口上鎖；archive 後的 worktree 移除失敗時需使用者手動 `git worktree remove`。
- 舊任務（本 change 前建立、程式碼改在主工作目錄未提交）重跑時會在新 worktree 從分支 commit 開始，主工作目錄的未提交改動不會被帶過去。
