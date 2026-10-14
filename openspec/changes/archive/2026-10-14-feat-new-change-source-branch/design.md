# Design: 新任務建立工作分支時讓使用者選擇起點分支並先同步

## Technical Approach

### lib/git_ops.py（新增，沿用 `_git()` 與 `REPO_ROOT`）

- `list_local_branches(project_dir) -> tuple[list[str], str]`：`git for-each-ref --format=%(refname:short) refs/heads` 依名稱排序回傳全部本地分支，第二個值為目前分支（`rev-parse --abbrev-ref HEAD`；detached HEAD 時回傳空字串）
- `branch_exists(project_dir, branch_name) -> bool`：`git show-ref --verify --quiet refs/heads/<branch>`
- `create_branch_from(project_dir, branch_name, base_branch) -> tuple[bool, str]`：
  1. `checkout <base_branch>`，失敗回傳 `(False, stderr)`（例如未提交變更衝突）
  2. `rev-parse --abbrev-ref --symbolic-full-name @{u}`；失敗＝沒有 upstream → 訊息加註「起點分支 <base> 未設定 upstream，略過 git pull」，直接進第 4 步
  3. `pull --ff-only`，失敗回傳 `(False, "git pull 失敗：<stderr>")`，不建立分支（此時停在起點分支上）
  4. `checkout -b <branch_name>`，回傳 `(True, "<project_dir> 已從 <base> 建立並切換到分支 <branch>")`（略過同步時一併帶出提示）
- `lib/__init__.py` 匯出上述函式
- `ensure_on_branch()` 不修改（execute／review／archive 繼續使用，「不存在則從 HEAD 建立」的退路保留給它們）

### nodes/analyze_plan.py

- 新增 `_ask_base_branch(project_dir) -> str`：取得 `list_local_branches()`；選項以 `interaction.numbered()` 組成「編號. 名稱」，目前分支的文字加「（目前分支）」；用 `_ask_or_default()` 提問（`kind="text"` 不 required，讓 Enter 可代表預設）
  - 空答案 → 回傳目前分支；目前分支為空（detached HEAD）時重問
  - 非互動式環境 → 回傳目前分支（detached 時回傳空字串）
  - 非數字或超出範圍 → 印提示重問
  - 中止（EOF／Ctrl-C）→ 回傳空字串
- 初始規劃分支段：`project_dir` 決定後、原本 `ensure_on_branch()` 之前，若為初始規劃且 `not branch_exists(project_dir, branch_name)`：呼叫 `_ask_base_branch()`；空字串 → `_fail("未選擇起點分支，無法建立分支 <branch>")`；否則 `create_branch_from()`，失敗 → `_fail(f"無法建立分支 {branch_name}：{msg}")`。其他情況照舊走 `ensure_on_branch()`
- 起點分支只在當次使用，不寫進 `AgentState`（後續節點不需要）

### 時序與逾時

`pull` 沿用 `_GIT_TIMEOUT`（30 秒）；`subprocess.TimeoutExpired` 需在 `create_branch_from()` 內攔下並回傳 `(False, "git pull 逾時")`，避免例外穿出節點。

## Architecture Decisions

### Decision: 同步採只快轉、無 upstream 時略過

只快轉保證不在起點分支上產生 merge commit 或衝突狀態；本地起點分支已分岔代表使用者需自行處理，記為錯誤比自動合併安全。僅存在於本地、未推送的分支（無 upstream）是常見情境，視為「已是最新」略過同步而非報錯。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫**：`lib/git_ops` 的公開函式，以 `tmp_path` 建立真實 git repo（另建 bare repo 當 remote 模擬 upstream），patch `git_ops.REPO_ROOT` 指向 tmp 目錄；斷言實際分支、commit 與回傳 `(ok, msg)`
- **次要接縫**：`analyze_plan_node(state)`（沿用 `tests/test_node_guards.py`／`test_analyze_adjust.py` 的 patch 慣例），patch `interaction.ask`／`is_interactive`、`branch_exists`、`list_local_branches`、`create_branch_from`、`ensure_on_branch`、`call_claude`；斷言提示選項、呼叫參數與 `status`

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| 本地分支 main、develop（目前在 develop）；工作分支 feat/login 不存在；使用者輸入「2」選 main；main 有 upstream 且遠端多一個 commit | 提問選項為「1. develop（目前分支）」「2. main」；main 快轉到遠端最新；feat/login 從最新 main 建立並切換 | 選項清單、feat/login 的 HEAD == 遠端 main HEAD、`status != "error"` |
| 同上但直接 Enter | 以 develop 為起點 | `create_branch_from` 收到 base == develop |
| 非互動式環境 | 以目前分支為起點，不提問 | `interaction.ask` 未被呼叫 |
| 輸入「9」或「abc」後再輸入「1」 | 重問一次後採用第 1 個分支 | `interaction.ask` 呼叫 2 次 |
| 起點分支沒有 upstream | 印出略過提示，仍建立工作分支 | 回傳 ok=True、msg 含「略過 git pull」 |
| 起點分支與遠端分岔（無法快轉） | 記為錯誤、工作分支不存在 | `status == "error"`、`branch_exists(feat/login) is False` |
| 工作分支已存在 | 不提問起點分支，照舊切過去 | `interaction.ask` 未以起點分支題呼叫、`ensure_on_branch` 被呼叫 |
| 使用者中止起點分支提問 | 記為錯誤、不呼叫 Claude | `status == "error"`、`call_claude` 未被呼叫 |

## Technical Debt & Follow-up Notes

- 容器內 `git pull` 需要目標專案 remote 的認證（SSH key 或 credential helper）；若容器未掛載，所有有 upstream 的起點分支都會同步失敗。需在 README 安裝與使用段落提醒
- 30 秒逾時對大型 repo 可能不足，若實務常逾時再另開任務調整
