# Tasks

## 1. git_ops：列出分支、判斷存在、從起點分支同步並建立

- [x] 1.1 撰寫 `tests/test_git_ops.py`（tdd 紅-綠，真實 tmp git repo + bare remote，patch `git_ops.REPO_ROOT`）：`list_local_branches` 依名稱排序並回傳目前分支；`branch_exists` 正反案例
- [x] 1.2 在 `lib/git_ops.py` 實作 `list_local_branches()`、`branch_exists()`，並於 `lib/__init__.py` 匯出
- [x] 1.3 撰寫 `create_branch_from()` 測試，測試本體分別含 Scenario 標題原字串：「起點分支落後遠端時先同步再建立工作分支」「起點分支未設定 upstream 時略過同步並從本地版本建立」「起點分支無法快轉時記為錯誤且不建立工作分支」（git_ops 層斷言回傳值與實際分支狀態）
- [x] 1.4 在 `lib/git_ops.py` 實作 `create_branch_from()`（checkout 起點 → 檢查 upstream → `pull --ff-only` → `checkout -b`；攔下 `TimeoutExpired`），並於 `lib/__init__.py` 匯出

## 2. analyze_plan：起點分支提問與接線

- [x] 2.1 撰寫 `analyze_plan_node` 測試（沿用 `tests/test_node_guards.py` 的 patch 慣例），測試本體分別含 Scenario 標題原字串：「工作分支不存在時列出本地分支並以使用者選的分支為起點」「起點分支提問直接送出空白時以目前分支為起點」「起點分支提問輸入無效編號時重新詢問」「工作分支已存在時直接切換不詢問起點分支」「非互動式環境以目前分支為起點建立工作分支」「使用者中止起點分支提問時記為錯誤」
- [x] 2.2 在 `nodes/analyze_plan.py` 新增 `_ask_base_branch()`（`interaction.numbered()` 選項、目前分支加註「（目前分支）」、空白採目前分支、無效編號重問、中止回傳空字串）
- [x] 2.3 在 `analyze_plan_node` 初始規劃分支段接線：工作分支不存在 → `_ask_base_branch()` + `create_branch_from()`，失敗以 `_fail()` 回傳且錯誤說明含工作分支名稱與失敗原因；已存在或非初始規劃 → 照舊 `ensure_on_branch()`
- [x] 2.4 在 analyze_plan 層補一個同步失敗測試（patch `create_branch_from` 回傳失敗），測試本體含「起點分支無法快轉時記為錯誤且不建立工作分支」，斷言 `status == "error"` 且 `call_claude` 未被呼叫
- [x] 2.5 執行 `pytest AgentLoop/tests/ -v` 確認全部通過（含 `tests/test_usage_limit_resume.py`）；既有 patch `ensure_on_branch` 的初始規劃測試若因新增 `branch_exists` 判斷而失敗，補 patch `branch_exists` 回傳 True 使其維持原行為

## 3. 文件同步

- [x] 3.1 更新 `ARCHITECTURE.md`：目錄樹 `git_ops.py` 註解、1. `analyze_plan`「任務開始時詢問 git 分支名稱與目標專案」段落（起點分支提問、只快轉同步、無 upstream 略過、失敗記為錯誤）、建立階段摘要，以及互動埠「目前走互動埠的呼叫點」清單加入起點分支提問
- [x] 3.2 更新 `README.md` 安裝與使用段落：新增任務時工作分支不存在會詢問起點分支並先 `git pull --ff-only`；提醒容器需具備目標專案 remote 的 git 認證
