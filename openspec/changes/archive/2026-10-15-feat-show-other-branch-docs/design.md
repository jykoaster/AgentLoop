# Design: 檢視規格文件可讀取其他分支上的 change

## Technical Approach

讀取來源依序決定（只在 `GET /api/changes/{name}/files` 與 `GET /api/changes/{name}/files/{path}` 兩個端點生效）：

1. **工作樹**：`<project>/openspec/changes/<name>/` 是資料夾 → 沿用現有 `_list_markdown()`／`_read_markdown()`，行為完全不變（含 untracked、未 commit 的修改）。
2. **工作分支**：工作樹沒有該資料夾 → 讀 `<project>/.agentloop/changes/<name>/state.json` 的 `branch_name`；非空且 `git_ops.branch_exists()` 為真時，改從該分支讀：
   - 清單：`git_ops.list_branch_files(project_dir, branch, dir_rel) -> tuple[list[str] | None, str]`，執行 `git ls-tree -r --name-only <branch> -- openspec/changes/<name>/`，第一個值為相對於 `dir_rel` 的路徑（`/` 分隔）；資料夾不在分支上回 `([], "")`；git 失敗回 `(None, <stderr 或 stdout 去頭尾空白>)`。
   - 內容：`git_ops.read_branch_file(project_dir, branch, path_rel) -> tuple[str | None, str]`，執行 `git show <branch>:<path_rel>`，以 UTF-8 解碼；成功回 `(內容, "")`，失敗回 `(None, <stderr 或 stdout 去頭尾空白>)`。
   - 兩者的錯誤訊息取法比照同檔 `create_branch_from`（`(result.stderr or result.stdout).strip()`），讓呼叫者看得到 git 實際錯誤。
   - 兩者皆只用唯讀 git 指令，不 checkout、不寫 index、不碰工作樹。
3. **都沒有**：`branch_name` 為空、分支不存在、分支上沒有任何 `.md` 檔 → 拋 `NotFound("找不到 change：<name>")`（HTTP 404，與現況相同）。

來源判定集中在 `web/repo_view.py` 新增的 `_resolve_change_source(project, change_name)`：

- 回傳兩種結果之一：工作樹（change 資料夾的 root 路徑）或工作分支（分支名稱＋已過濾排序的 `.md` 相對路徑清單）。型別可用小型 dataclass 或 tuple，由實作決定。
- 依上方 1→2→3 的順序判定；都沒有時在 helper 內拋 `NotFound("找不到 change：<name>")`；`list_branch_files` 回 `None`（git 失敗）時拋 `NotFound("找不到 change：<name>（git：<錯誤訊息>）")`。
- `list_change_files()`：工作樹來源照舊 `_sorted_markdown_files(root)`；分支來源直接回傳 helper 給的清單。
- `read_change_file()`：工作樹來源照舊 `_read_markdown(root, rel_path)`；分支來源先檢查 `rel_path` 是否**逐字**在 helper 給的清單內，不在 → `NotFound("找不到檔案：<rel_path>")`（不附 git 錯誤）；在清單內才呼叫 `read_branch_file`，回 `None` 時視為 git 出錯 → `NotFound("找不到檔案：<rel_path>（git：<錯誤訊息>）")`。

錯誤訊息格式：在原訊息後直接接全形括號「（git：<錯誤訊息>）」；錯誤訊息為空字串時不附括號。

排序：把現有 `_sorted_markdown_files()` 中的排序 key 抽出，讓工作樹的 `os.walk` 結果與分支的 `ls-tree` 結果共用同一套「只留 `.md`、`proposal.md`/`design.md`/`tasks.md` 置頂、其餘依路徑字母排序」規則。

路徑安全：分支來源沒有真實檔案系統可用 `realpath` 比對，改以「`rel_path` 必須逐字出現在分支上的 `.md` 清單內」作為唯一放行條件：清單只含 `ls-tree` 列出、位於該 change 資料夾下的 `.md` 檔，因此 `../`、絕對路徑、非 `.md` 檔都自然被拒絕。原先的 `_safe_branch_rel_path()`（`posixpath.normpath` 檢查）被這個清單比對取代，應刪除。`change_name` 仍先經 `_require_safe_name()`。`branch_name` 只當成 git 參數傳入（list 形式的 subprocess，不經 shell），並先以 `branch_exists()` 確認是本地分支，避免把任意字串當 revision。

`web/app.py`、HTTP 回應格式、前端 `FileBrowser.vue` 皆不變。

## Architecture Decisions

### Decision: 工作樹優先，找不到才讀工作分支的最新 commit

使用者已確認：不切換分支、直接從 git 讀。未 commit 的 change 檔案是 untracked，切分支時會留在工作樹，所以工作樹找得到就代表那是最新內容；找不到才代表它已 commit 在別的分支上，此時分支最新 commit 就是完整內容。不採用「每階段結束另存快照」，因為快照可能比分支實際內容舊，且要多維護一份副本。畫面不標示來源（使用者決定）。

### Decision: git 讀取失敗時保留錯誤訊息並顯示給使用者

使用者已確認：`list_branch_files`／`read_branch_file` 比照 `create_branch_from` 回傳 `(結果或 None, git 錯誤訊息)`，不吞掉 stderr。web 層目前沒有 logging，因此不新增 log，而是把錯誤附在 HTTP 404 的 detail 後面，畫面上直接看得到。`git show` 對「檔案不存在」與「git 出錯」都回非 0，無法用結束碼區分，所以讀單檔前先比對分支清單：不在清單內是單純找不到（訊息不變），在清單內卻讀失敗才是 git 出錯（附錯誤）。代價是讀單檔多一次 `ls-tree`，可接受。

### Decision: 來源判定抽成單一 helper

`list_change_files()` 與 `read_change_file()` 原本各自重複「工作樹優先 → 工作分支 → 找不到」流程；因讀單檔也需要分支清單，兩者需要的資訊一致，抽出 `_resolve_change_source()` 統一判定來源與錯誤訊息。

### Decision: git 讀取放在 `lib/git_ops.py`

`lib/git_ops.py` 已是「對目標專案下 git 指令」的唯一模組（共用 `_git()` 與逾時設定），唯讀查詢同樣放這裡，`web/repo_view.py` 只負責決定來源與排序。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫**：HTTP API（`tests/test_web_app.py`，FastAPI `TestClient` 打 `/api/changes/{name}/files[/{path}]`）。在 `tmp_path/my-project` 建立真實 git repo（作法同 `tests/test_git_ops.py`）。`git_ops.REPO_ROOT` 的 patch 併入 `workspace` fixture 既有的 `for mod in (...)` 迴圈（檔案開頭 import `AgentLoop.lib.git_ops`），各測試不再自行 `monkeypatch.setattr`。
- **次要接縫**：無（`git_ops` 新函式透過 API 測試即可涵蓋；不另寫單元測試）。

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| 主路徑：`feat-login` 的 state 記錄分支 `feat/login`；`feat/login` 上已 commit `openspec/changes/feat-login/` 的 `tasks.md`、`proposal.md`、`specs/auth/spec.md`；工作樹 checkout 回 `main`（無該資料夾） | 清單依序為 `proposal.md`、`tasks.md`、`specs/auth/spec.md`；讀 `specs/auth/spec.md` 回該分支上的全文；工作樹仍在 `main`、`git status` 乾淨 | 檔案清單、`content`、目前分支、工作樹無變化 |
| 工作樹與工作分支同時有該 change，內容不同 | 回工作樹的內容 | `content` 等於工作樹檔案 |
| 該任務的工作分支不存在（或 state 未記錄分支），工作樹也沒有資料夾 | 404「找不到 change：feat-login」 | status 404、detail |
| 分支來源下要求 `../../README.md` 或非 `.md` 檔 | 404 | status 404 |
| 錯誤：`feat/login` 上有 `proposal.md`，但刪除其 blob 的 loose object（`.git/objects/<前2碼>/<其餘>`，sha 以 `git rev-parse feat/login:openspec/changes/feat-login/proposal.md` 取得），工作樹在其他分支 | 清單仍含 `proposal.md`；讀 `proposal.md` 回 404，detail 以「找不到檔案：proposal.md（git：」開頭、以「）」結尾，中間非空 | 清單、status 404、detail 前綴／後綴 |
| 現有：工作樹有資料夾（`從任務列開啟該 change 的規格文件`） | 行為不變 | 既有斷言 |

## Technical Debt & Follow-up Notes

- 「執行中任務」列表判定是否已封存時只看目前工作樹的 `openspec/changes/archive/`；某任務若在其他分支上已封存，仍可能出現在列表中。本次不處理。
- 分支來源讀到的是已 commit 內容；若同一 change 在分支上 commit 後，使用者又在其他地方保留未 commit 的修改，網頁看不到那些修改（使用者已接受，不加來源提示）。
