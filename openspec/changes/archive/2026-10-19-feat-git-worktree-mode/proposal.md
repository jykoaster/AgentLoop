# Proposal: 以 git worktree 讓多個任務同時執行

## Intent

**規範目的**：讓同一個目標專案底下的多個任務（change）能同時執行工作流，且使用者能在「執行中任務」分頁同時看到每個任務各自的階段進度、待回覆提問並各自中止。做法是每個任務在自己專屬的 git worktree（任務工作目錄）裡規劃、實作、審查與封存，目標專案的主工作目錄永遠不再被切換分支或修改；CLI 與網頁一律如此，不提供開關。

**規範背景**：目前各節點都在主工作目錄 `git checkout` 工作分支，兩個執行並行會互相切走分支，因此 `web/runner.py` 只允許同一目標專案同時一個執行（ADR：`docs/adr/0002-change-worktree-and-commit-on-archive.md`）。execute 從不 commit，所有實作都以未提交狀態留在工作目錄，因此 worktree 的移除必須搭配封存時的自動 commit，否則會丟失成果。

**輸出要求（可觀察行為）**：
- 任務工作目錄固定為 `<工作區根目錄>/.agentloop-worktrees/<目標專案>/<change 名稱>/`，簽出該任務的工作分支；主工作目錄目前所在分支與未提交變更在整個工作流期間都不變。
- 執行狀態紀錄（state.json、`logs/<stage>.log`）仍在主工作目錄的 `.agentloop/changes/<change 名稱>/`。
- 不同任務可無上限同時執行；同一任務同時最多一個執行。該任務執行中時，只有它自己的「重跑」按鈕停用，滑鼠停留提示「<change 名稱> 執行中」；其他任務的重跑與「新增任務」照常可用。暫時列可同時存在多列。
- 每個執行中的任務列各自顯示執行中階段、待回覆提問（驚嘆號、呼吸光暈）、可各自回覆與中止，互不影響。
- 網頁「執行中任務」點開任一任務的規格文件，顯示的是該任務自己任務工作目錄內 `openspec/changes/<change 名稱>/` 的最新內容（含尚未 commit 的修改），多個任務並行時各看各的；任務工作目錄不存在時退回讀主工作目錄，再退回讀工作分支最新 commit。各階段日誌照舊由主工作目錄的執行狀態紀錄提供。
- 「已封存任務」分頁同時列出一般封存任務與未合併封存任務，全部依封存日期由新到舊排序；未合併封存任務在名稱後加標籤「未合併 · <工作分支>」，例如「2026-10-19 feat-login　未合併 · feat/login」。點開未合併封存任務時，從工作分支最新 commit 的 `openspec/changes/archive/<日期>-<change 名稱>/` 唯讀顯示其文件。工作分支合併回主工作目錄所在分支後，同一筆只以一般封存列出現一次、不再有標籤；工作分支被刪除且未合併時不列出。
- execute 成功時擬出一行任務 commit 訊息，格式依目標專案過往 commit 習慣，例如 `feat: git worktree mode`（`<類型>: <描述>`），寫入 state，不實際 commit。
- archive：使用者同意併入 specs 且 `openspec archive` 成功 → 在任務工作目錄 `git add -A` + 以該訊息 commit 到本地工作分支（不 push）→ 移除任務工作目錄（工作分支保留）→ state 標記已封存，任務自「執行中任務」移除。缺 commit 訊息或 commit 失敗 → 不 commit、不移除、不標記已封存，archive 階段記為錯誤並註明原因；之後重跑 archive 偵測到任務工作目錄內已封存時，只補做 commit 與移除。

**範例及解釋**：
1. 使用者在網頁新增任務「新增登入頁」，回覆分支 `feat/login`、起點分支 `main` → 系統 `git fetch`，以 `origin/main` 為起點建立分支 `feat/login` 與任務工作目錄 `.agentloop-worktrees/my-project/feat-login/` → analyze_plan 把規格寫進該目錄的 `openspec/changes/feat-login/`。此時主工作目錄仍停在使用者原本的 `develop`，未提交檔案原封不動。
2. `feat-login` 在 execute 執行中時，使用者再新增任務「修正樣式」→ 列表同時出現 `feat-login` 列（execute 呼吸光暈）與標題「修正樣式」的暫時列（analyze_plan 驚嘆號，等分支名稱）→ 使用者在暫時列回覆 `fix/css` → 兩個任務在各自的任務工作目錄並行；`feat-login` 的重跑按鈕停用並提示「feat-login 執行中」，`fix-css` 的不受影響。
3. `feat-login` 的 execute 結束時輸出 commit 訊息 `feat: login page` 寫入 state → review 通過 → archive 詢問是否併入 specs，使用者答 y → `openspec archive` 成功 → commit `feat: login page` 到 `feat/login` → 移除任務工作目錄 → `feat-login` 從執行中任務消失，改出現在「已封存任務」的最上方（日期最新），顯示為「2026-10-19 feat-login　未合併 · feat/login」→ 點開後列出 `feat/login` 最新 commit 中 `openspec/changes/archive/2026-10-19-feat-login/` 的 proposal.md、design.md、tasks.md 並可閱讀 → 使用者把 `feat/login` 合併回 `develop` 後，同一列變成「2026-10-19 feat-login」（無標籤，改讀主工作目錄），「既有 Spec」此時才出現併入的內容。
4. 起點分支 `main` 有 upstream，但容器內 `git fetch` 因認證失敗：本地已有 `origin/main` → 以它為起點建立，日誌註明「容器內無法連線遠端、改用本地的遠端追蹤分支 origin/main」；連 `origin/main` 都沒有 → analyze_plan 記為錯誤，不建立任務工作目錄。
5. `feat-login`（execute 中）與 `fix-css`（analyze_plan 中）並行時，使用者在「執行中任務」點開 `fix-css` 的 proposal.md → 顯示 `.agentloop-worktrees/my-project/fix-css/openspec/changes/fix-css/proposal.md` 剛寫入、尚未 commit 的內容；再點開 `feat-login` 的 tasks.md → 顯示 `feat-login` 任務工作目錄內 execute 剛勾選的最新狀態。兩者互不混淆。
6. 舊任務 `feat-old` 的工作分支正是主工作目錄目前所在分支，使用者重跑其 execute → 錯誤「分支 feat/old 正在主工作目錄使用中，請先將主工作目錄切換到其他分支（未提交變更請先 commit 或 stash）」，不建立任務工作目錄。

## Scope

In scope:

- `lib/git_ops.py`：任務工作目錄路徑規則、建立（既有分支／從起點分支含 fetch 後備）、在 worktree 內 rollback、commit 全部變更、移除 worktree；移除在主工作目錄 checkout 的函式
- `analyze_plan`／`execute`／`review`／`archive` 改在任務工作目錄操作；prompt 中的目標專案路徑改指任務工作目錄，execute 另告知主工作目錄路徑供 Agent 自行決定沿用（如符號連結 `node_modules`）或重新安裝相依套件
- execute 產出任務 commit 訊息寫入 state；archive 成功後 commit、移除 worktree、標記已封存；重跑 archive 只補做 commit 與移除
- 同一任務同時最多一個執行的保護（CLI 與網頁皆適用）
- `web/runner.py` 改為多執行管理；HTTP API 與前端改為每個任務各自顯示執行、回覆提問、中止；「新增任務」不再因其他執行而停用
- 執行中任務列表排除已標記封存的任務；檢視規格文件先讀任務工作目錄
- 「已封存任務」加列未合併封存任務（標籤「未合併 · <工作分支>」），其文件從工作分支最新 commit 唯讀讀取
- 對應測試、`ARCHITECTURE.md`、`README.md`、`CONTEXT.md` 更新

Out of scope:

- 多個目標專案同時執行（設定頁仍在任何執行進行中時禁止變更目標專案）
- 自動 push、自動建立 PR、自動合併工作分支
- 顯示任務工作目錄的 git 狀態（未提交檔案數等）或新增 Worktree 分頁
- 系統自動安裝相依套件
- 目標專案 `docker compose` 固定容器名稱／埠在並行任務間的衝突
- 「既有 Spec」分頁顯示尚未合併回主工作目錄的封存內容

## Approach

以「任務工作目錄路徑由 `project_dir` + `change_name` 決定」為核心，不新增路徑欄位：`project_dir` 仍指主工作目錄（執行狀態紀錄所在），新增 helper 算出 worktree 路徑，所有讀寫程式碼與 `openspec/` 的地方改用它。git 操作全部集中在 `lib/git_ops.py`（`git worktree add/remove`、`git fetch`、`git commit`）。`AgentState` 新增 `commit_message`、`archived` 兩個欄位。`web/runner.py` 由單一 handle 改為以 run_id 為鍵的多 handle，執行目錄改為 `.web/runs/<run_id>/`；子行程決定 change 名稱後主動寫入執行目錄，取代以任務描述＋mtime 掃描的偵測。細節見 `design.md`。
