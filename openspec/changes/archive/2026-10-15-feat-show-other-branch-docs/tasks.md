# Tasks

## 1. git 唯讀讀取

- [x] 1.1 在 `lib/git_ops.py` 新增 `list_branch_files(project_dir, branch, dir_rel)`：以 `git ls-tree -r --name-only <branch> -- <dir_rel>/` 列出分支上該資料夾的檔案（相對 `dir_rel`、`/` 分隔），git 失敗回 `None`；不 checkout、不動工作樹與 index
- [x] 1.2 在 `lib/git_ops.py` 新增 `read_branch_file(project_dir, branch, path_rel)`：以 `git show <branch>:<path_rel>` 讀出 UTF-8 內容，不存在或失敗回 `None`

## 2. repo_view 讀取來源

- [x] 2.1 先寫測試（紅）：在 `tests/test_web_app.py` 新增測試，docstring 含「目前分支沒有該 change 資料夾時從任務的工作分支讀取規格文件（API）」；以 `tmp_path/my-project` 建真實 git repo，在 `feat/login` commit change 資料夾後切到 `feat/cart`，斷言檔案清單順序、`specs/auth/spec.md` 全文、目前分支仍為 `feat/cart` 且 `git status --porcelain` 無輸出（需另 patch `git_ops.REPO_ROOT`）
- [x] 2.2 先寫測試（紅）：新增測試，docstring 含「工作樹與工作分支都沒有該 change 時顯示找不到 change（API）」；state 記錄不存在的分支，斷言清單端點回 404 且 detail 為「找不到 change：feat-login」
- [x] 2.3 新增測試：工作樹與工作分支同時有該 change 時回工作樹內容；分支來源下要求 `../` 路徑或非 `.md` 檔回 404
- [x] 2.4 把 `web/repo_view.py` `_sorted_markdown_files()` 的過濾與排序規則抽成可共用的函式，工作樹與分支來源共用
- [x] 2.5 修改 `list_change_files()`／`read_change_file()`：工作樹有 change 資料夾時照舊；沒有時讀 `state.json` 的 `branch_name`，經 `branch_exists()` 確認後改用 1.1／1.2 讀取；分支路徑以 `posixpath.normpath` 正規化並拒絕跳出 change 資料夾或非 `.md`；都沒有時拋 `NotFound("找不到 change：<name>")`，使 2.1～2.3 轉綠
- [x] 2.6 確認既有測試「從任務列開啟該 change 的規格文件」（`tests/test_web_app.py`、`web/frontend/src/__tests__/ActiveChanges.spec.ts`）仍通過，執行 `pytest AgentLoop/tests/ -v` 與 `npx vitest run`

## 3. 文件同步

- [x] 3.1 更新 `ARCHITECTURE.md`：目錄樹與 HTTP API 一節中 `repo_view.py` 的說明、`/changes/{name}/files[/{path}]` 列補上「工作樹找不到時唯讀改讀任務工作分支最新 commit」；`lib/git_ops.py` 說明補上兩個唯讀函式

## 4. 審查修補：保留 git 錯誤訊息、抽出來源判定 helper、收斂測試 fixture

- [x] 4.1 收斂測試 fixture：`tests/test_web_app.py` 檔案開頭 import `AgentLoop.lib.git_ops`，加入 `workspace` fixture 的 `for mod in (app_module, repo_view_module, runner_module)` 迴圈；移除 `TestChangeFilesFromOtherBranch` 4 個測試中的區域 import、`monkeypatch.setattr(git_ops_module, "REPO_ROOT", ...)` 與不再需要的 `monkeypatch` 參數，確認 4 個測試仍通過
- [x] 4.2 先寫測試（紅）：在 `TestChangeFilesFromOtherBranch` 新增測試，docstring 含「讀取工作分支時 git 指令失敗會在找不到訊息後附上 git 錯誤訊息（API）」；在 `feat/login` commit 含 `proposal.md` 的 change 資料夾後切到 `feat/cart`，以 `git rev-parse feat/login:openspec/changes/feat-login/proposal.md` 取得 blob sha 並刪除對應 loose object 檔；斷言清單端點仍含 `proposal.md`，讀 `proposal.md` 回 404 且 detail 以「找不到檔案：proposal.md（git：」開頭、以「）」結尾、括號內非空
- [x] 4.3 修改 `lib/git_ops.py`：`list_branch_files` 改回傳 `tuple[list[str] | None, str]`、`read_branch_file` 改回傳 `tuple[str | None, str]`，失敗時第二個值為 `(result.stderr or result.stdout).strip()`，成功時為空字串；更新 docstring
- [x] 4.4 重構 `web/repo_view.py`：新增 `_resolve_change_source(project, change_name)`（工作樹 root 或「分支名稱＋已排序 `.md` 清單」；都沒有拋「找不到 change：<name>」；`ls-tree` 失敗拋「找不到 change：<name>（git：<錯誤>）」），`list_change_files()`／`read_change_file()` 改用它；分支來源讀單檔時 `rel_path` 不在清單內回「找不到檔案：<rel_path>」，在清單內但讀取失敗回「找不到檔案：<rel_path>（git：<錯誤>）」；刪除 `_safe_branch_rel_path()`，使 4.2 轉綠
- [x] 4.5 執行 `pytest AgentLoop/tests/ -v` 與 `cd AgentLoop/web/frontend && npx vitest run`，確認 2.1～2.3、既有「從任務列開啟該 change 的規格文件」與 4.2 全部通過
- [x] 4.6 更新 `ARCHITECTURE.md`：`lib/git_ops.py` 兩個唯讀函式改述為回傳 `(結果或 None, git 錯誤訊息)`；`repo_view.py`／`/changes/{name}/files[/{path}]` 說明補上「git 失敗時在 404 訊息後附上 git 錯誤」
