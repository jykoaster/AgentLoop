# Tasks

## 1. 任務工作目錄（lib/git_ops.py）

- [x] 1.1 以 tdd 紅-綠循環在 `tests/test_git_ops.py`（tmp_path 真實 repo＋bare 遠端）撰寫 `worktree_dir`／`ensure_worktree` 測試：已存在且分支正確時不重建、本地有分支時建立 worktree、本地無分支時從主工作目錄 HEAD 建立、分支為主工作目錄目前分支時回傳固定錯誤訊息「分支 <名稱> 正在主工作目錄使用中，請先將主工作目錄切換到其他分支（未提交變更請先 commit 或 stash）」、分支已被其他 worktree 簽出時失敗；每案都斷言主工作目錄 HEAD 與未提交檔不變
- [x] 1.2 實作 `worktree_dir()`、`ensure_worktree()`（含 `git worktree prune`），路徑為 `<REPO_ROOT>/.agentloop-worktrees/<project_dir>/<change_name>`
- [x] 1.3 以 tdd 撰寫 `create_worktree_from` 測試：fetch 成功時以遠端追蹤分支最新 commit 為起點；fetch 失敗但本地有遠端追蹤 ref 時以它為起點且訊息含「容器內無法連線遠端、改用本地的遠端追蹤分支 <ref>」；fetch 失敗且無該 ref 時不建立分支與 worktree；起點分支無 upstream 時以本地起點分支建立；主工作目錄 HEAD 與本地起點分支皆不變
- [x] 1.4 實作 `create_worktree_from()`（只 `git fetch`、`git worktree add --no-track -b`，不 checkout、不 pull）
- [x] 1.5 以 tdd 撰寫並實作 `commit_all()`（任務工作目錄 `git add -A` + `git commit -m`，不 push）與 `remove_worktree()`（不加 `--force`、分支保留）
- [x] 1.6 `rollback_except_openspec()` 改在任務工作目錄執行（簽名加 `change_name`），更新既有測試
- [x] 1.7 移除 `ensure_on_branch()`、`create_branch_from()` 及 `lib/__init__.py` 匯出；移除 `tests/test_git_ops.py` 中 `test_syncs_behind_remote_then_creates_branch`、`test_skips_sync_when_no_upstream`、`test_diverged_remote_fails_without_creating_branch` 測試（由 1.3 取代）；更新新匯出

## 2. 同一任務互斥鎖（core/change_lock.py）

- [x] 2.1 以 tdd 撰寫 `tests/test_change_lock.py`：兩個子行程對同一任務上鎖時第二個回傳「任務 <change 名稱> 已有執行進行中」、第一個行程結束後可再上鎖、同一行程重複上鎖視為成功
- [x] 2.2 實作 `core/change_lock.acquire()`（`fcntl.flock` 於 `<主工作目錄>/.agentloop/changes/<change>/run.lock`），並由 `core/__init__.py` 匯出
- [x] 2.3 `main.py` 的 `run_node()` 載入 state 後上鎖，失敗則印錯誤並以 exit 1 結束；補對應測試於 `tests/test_workflow_entrypoints.py`

## 3. 狀態欄位與節點改用任務工作目錄

- [x] 3.1 `core/state.py` 新增 `commit_message: str`、`archived: bool`；`main.py` 的 `_empty_state()` 補預設值；更新 `tests/test_state_persistence.py` 確認舊 state.json 缺欄位時以預設值載入
- [x] 3.2 `main._save_state()` 在設有 `AGENTLOOP_RUN_DIR` 時寫 `<run_dir>/change.json`（`{"change_name": ...}`）；補測試
- [x] 3.3 `analyze_plan`：初始規劃在決定 change 名稱後上鎖，再以 `create_worktree_from`／`ensure_worktree` 取代原分支切換；其餘模式改呼叫 `ensure_worktree`；所有 `openspec/` 路徑、`openspec` CLI cwd、`build_project_doc_hint_for` 與 prompt 中的目標專案目錄／OpenSpec Change 位置改用任務工作目錄；`.agentloop/` 仍用主工作目錄；已封存判定加入 state `archived`
- [x] 3.4 更新 `tests/test_analyze_plan_base_branch.py`（7 個測試改為斷言建立 worktree、主工作目錄 HEAD 不變；`test_non_ff_failure_is_error_and_branch_not_created` 改為 fetch 失敗且無遠端追蹤 ref 的錯誤情境）、`tests/test_analyze_adjust.py`、`tests/test_analyze_failed_retry.py` 中對 `ensure_on_branch`／`create_branch_from` 的 patch 改為新函式
- [x] 3.5 `execute`：改呼叫 `ensure_worktree` 並在任務工作目錄操作；`_SYSTEM` 改為告知任務工作目錄與主工作目錄路徑（Agent 自行決定沿用相依檔或重新安裝）、要求不得 commit 並於最後輸出一行 `COMMIT_MESSAGE: <依該專案 git log 慣例的一行訊息>`；依 CLAUDE.md「Keep prompts from growing」合併／刪除同義舊句，`_SYSTEM` 實質長度不增加
- [x] 3.6 以 tdd 撰寫 execute 測試：輸出含 `COMMIT_MESSAGE: feat: login page` 時回傳 `commit_message == "feat: login page"`；輸出缺該行時保留 state 原值；更新 `tests/test_node_guards.py`、`tests/test_usage_limit_resume.py` 中對 `ensure_on_branch` 的 patch
- [x] 3.7 `review`：改呼叫 `ensure_worktree`，`git diff HEAD` 與 prompt 路徑改用任務工作目錄；更新 `tests/test_review_suggestions.py` 的 patch
- [x] 3.8 `archive`：依 design.md「3. 節點改在任務工作目錄操作」的 archive 六步驟實作（同意 → openspec archive 或偵測已封存略過 → 檢查 commit 訊息 → `commit_all` → `remove_worktree` → `archived: True`；缺訊息或 commit 失敗回 `status: "error"` 並註明原因與 worktree 路徑）
- [x] 3.9 以 tdd 撰寫 archive 測試（真實 tmp repo，mock `archive_change`／`interaction.ask`）：有訊息時 commit 訊息相符、worktree 移除、分支保留、`archived: True`；無訊息時未 commit、worktree 保留、`status: "error"`；worktree 內已封存時不呼叫 `archive_change` 而直接 commit 與移除；使用者答否時不 commit、不移除、不標記

## 4. 網頁多執行管理（web/runner.py、web/app.py、web/repo_view.py）

- [x] 4.1 以 tdd 更新 `tests/test_web_runner.py`：移除 `test_second_start_is_rejected_while_run_active` 測試，新增「兩個新任務可同時啟動且 `runs()` 回兩筆」「同一任務已有執行時重跑拋 `RunConflict`、其他任務重跑成功」「回覆／中止指定 run 不影響另一個 run」「讀 `change.json` 取得 change 名稱」；既有 `test_abort_marks_stage_error_and_keeps_session`、`test_temp_row_abort_ends_run_without_state`、`test_answer_after_question_closed_reports_ended`、`test_blank_required_answer_is_rejected` 改帶 run_id
- [x] 4.2 `RunManager` 改為以 run_id 為鍵的多執行；執行目錄 `runs/<run_id>/`；`runs()`、`answer(run_id, …)`、`abort(run_id)`、`live_stage_log` 依 change 名稱找執行、`is_active()` 任一執行即 True；以 `change.json` 取代 `_detect_change_name` 的掃描
- [x] 4.3 `web/app.py`：`GET /run` 改 `GET /runs`；`POST /run/answer`、`POST /run/abort` 改 `POST /runs/{run_id}/answer`、`POST /runs/{run_id}/abort`；新增任務不再回 409；重跑只在同一任務已有執行時回 409（detail「<change 名稱> 執行中」）
- [x] 4.4 更新 `tests/test_web_app.py` 中 `test_rerun_starts_at_stage_and_continues`、`test_new_task_starts_analyze_plan_question`、`test_rejects_target_project_change_while_run_active` 改用新端點；新增「同一任務重跑 409、其他任務重跑 200」測試
- [x] 4.5 `repo_view`：`list_active_changes` 排除 state `archived` 為 True 者；`list_change_files`／`read_change_file` 讀取順序改為任務工作目錄 → 主工作目錄 → 工作分支 commit
- [x] 4.6 在 `tests/test_web_app.py` 新增「state 標記已封存的任務不出現在執行中任務」與「規格文件優先讀任務工作目錄」測試；調整 `test_change_files_read_from_work_branch_when_worktree_missing`、`test_change_files_prefer_worktree_when_branch_also_has_change` 的工作目錄前提
- [x] 4.7 以 tdd 在 `tests/test_web_app.py` 新增「兩個任務並行時各自讀到自己任務工作目錄內未 commit 的規格文件」測試（design.md 測試矩陣範例 5）
- [x] 4.8 以 tdd 在 `tests/test_web_app.py` 新增未合併封存任務測試：state `archived: True` 且工作分支上有封存資料夾時 `GET /archive` 含 `branch` 欄位並與一般封存依日期由新到舊混排、可列出與讀取分支上的檔案；工作分支已合併（主工作目錄有同名資料夾）時只出現一次且 `branch` 為空；工作分支已刪除時不列出且回 200；既有 `test_archive_lists_each_change_and_its_files` 補斷言 `branch` 為空字串
- [x] 4.9 `repo_view`：依 design.md「7. repo_view」實作 `list_archive` 加列未合併封存任務、`list_archive_files`／`read_archive_file` 在主工作目錄無該資料夾時改從工作分支唯讀讀取

## 5. 前端（web/frontend/src）

- [x] 5.1 `api.ts`：`RunStatus` 改 `RunInfo`、`getRun` 改 `getRuns`、`postAnswer(runId, questionId, answer)`、`postAbort(runId)`
- [x] 5.2 以 tdd 更新 `__tests__/ActiveChanges.spec.ts`：mock 改 `getRuns`；原斷言「目前已有 feat-login 執行中」的測試改為「只有 feat-login 自己的重跑按鈕停用且 title 為『feat-login 執行中』，其他任務重跑與『新增任務』可用」；移除新增任務收到 409 的測試；新增「兩個無 change 名稱的執行各顯示一列暫時列」「兩列各自有待回覆提問、回覆時帶各自 run_id」「中止時帶該列 run_id」測試；同步更新 `__tests__/App.spec.ts` 的 mock
- [x] 5.3 `ActiveChanges.vue`、`ChangeRow.vue`、`StageDetail.vue`、`QuestionForm.vue` 改為每列對應自己的執行（prop `run: RunInfo | null`），依 design.md「6. 前端」實作
- [x] 5.4 以 tdd 在 `__tests__/ArchivedChanges.spec.ts` 新增測試：`branch` 為 `feat/login` 的列名稱後顯示「未合併 · feat/login」、`branch` 為空的列無標籤；`api.ts` 的 `ArchiveRow` 新增 `branch: string`，並在 `ArchivedChanges.vue` 實作標籤；同步更新 `__tests__/App.spec.ts` 的 archive mock
- [x] 5.5 執行 `npx vitest run` 與 `pytest AgentLoop/tests/ -v` 全數通過

## 6. 文件

- [x] 6.1 依 design.md「8. 文件」更新 `ARCHITECTURE.md`（目錄結構、AgentState、流程圖與 archive 說明、檔案系統共享記憶表、Git Diff 稽核、執行管理、HTTP API 表（`GET /archive` 新增 `branch` 欄位）、前端（已封存任務的未合併標籤）、容器化層「仍只支援單一目標專案同時執行」一句）
- [x] 6.2 更新 `README.md` 安裝與使用：任務工作目錄位置、主工作目錄不被切換、多任務並行、archive 會 commit（不 push）並移除 worktree、相依套件由 Agent 自行處理、未合併封存任務在「已封存任務」以「未合併 · <工作分支>」標示
