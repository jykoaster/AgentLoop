"""任務工作目錄（git worktree）的建立／移除／commit，與唯讀的分支查詢。"""
import os
import subprocess
from .project_context import REPO_ROOT

_GIT_TIMEOUT = 30
_WORKTREES_DIR = ".agentloop-worktrees"


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=_GIT_TIMEOUT,
    )


def worktree_dir(project_dir: str, change_name: str) -> str:
    """回傳任務工作目錄相對 `REPO_ROOT` 的路徑：`.agentloop-worktrees/<project_dir>/<change_name>`。

    路徑完全由這兩個欄位決定，不另外存成 state 欄位。
    """
    return os.path.join(_WORKTREES_DIR, project_dir, change_name)


def list_local_branches(project_dir: str) -> tuple[list[str], str]:
    """列出 `<workspace>/<project_dir>` 全部本地分支（依名稱排序）與目前所在分支。

    目前為 detached HEAD 時，第二個值回傳空字串。
    """
    repo = os.path.join(REPO_ROOT, project_dir)
    refs = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    branches = sorted(line.strip() for line in refs.stdout.splitlines() if line.strip())

    head = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    current = head.stdout.strip()
    if head.returncode != 0 or current == "HEAD":
        current = ""
    return branches, current


def branch_exists(project_dir: str, branch_name: str) -> bool:
    """判斷 `branch_name` 是否為 `<workspace>/<project_dir>` 的本地分支。"""
    repo = os.path.join(REPO_ROOT, project_dir)
    result = _git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}")
    return result.returncode == 0


def list_branch_files(project_dir: str, branch: str, dir_rel: str) -> tuple[list[str] | None, str]:
    """唯讀列出 `branch` 最新 commit 中 `dir_rel/` 資料夾下的檔案路徑（相對 `dir_rel`、`/` 分隔）。

    不 checkout、不動工作樹與 index。回傳 `(結果或 None, git 錯誤訊息)`：資料夾在該分支上不存在
    回傳 `([], "")`；git 指令失敗回傳 `(None, <git 錯誤訊息>)`。
    """
    repo = os.path.join(REPO_ROOT, project_dir)
    prefix = dir_rel.rstrip("/") + "/"
    result = _git(repo, "ls-tree", "-r", "--name-only", branch, "--", prefix)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout).strip()
    files = [
        line[len(prefix):]
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    return files, ""


def read_branch_file(project_dir: str, branch: str, path_rel: str) -> tuple[str | None, str]:
    """唯讀讀出 `branch` 最新 commit 中 `path_rel` 檔案的 UTF-8 內容。

    不 checkout、不動工作樹與 index。回傳 `(結果或 None, git 錯誤訊息)`：成功時錯誤訊息為空字串，
    檔案不存在或 git 失敗時回傳 `(None, <git 錯誤訊息>)`。
    """
    repo = os.path.join(REPO_ROOT, project_dir)
    result = _git(repo, "show", f"{branch}:{path_rel}")
    if result.returncode != 0:
        return None, (result.stderr or result.stdout).strip()
    return result.stdout, ""


def _list_worktrees(repo: str) -> list[dict]:
    """解析 `git worktree list --porcelain`，回傳 `[{"worktree": path, "branch": "" 或分支名}, ...]`。
    第一筆固定是主工作目錄；`branch` 為空代表 detached HEAD 或 bare repo。"""
    result = _git(repo, "worktree", "list", "--porcelain")
    entries: list[dict] = []
    current: dict = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["worktree"] = line[len("worktree "):]
            current.setdefault("branch", "")
        elif line.startswith("branch "):
            ref = line[len("branch "):]
            current["branch"] = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    if current:
        entries.append(current)
    return entries


def ensure_worktree(project_dir: str, change_name: str, branch_name: str) -> tuple[bool, str]:
    """確保任務工作目錄存在、簽出 `branch_name`（取代 `ensure_on_branch`）。

    1. 任務工作目錄已存在且是該 repo 的 worktree、簽出 `branch_name` → 成功，不做事。
    2. `branch_name` 是主工作目錄目前所在分支 → 失敗，固定錯誤訊息。
    3. `branch_name` 已被其他 worktree 簽出 → 失敗並附 git 訊息。
    4. 本地已有 `branch_name` → `git worktree add`；本地沒有 → 從主工作目錄 HEAD 建立。
    """
    repo = os.path.join(REPO_ROOT, project_dir)
    abs_path = os.path.join(REPO_ROOT, worktree_dir(project_dir, change_name))

    _git(repo, "worktree", "prune")
    entries = _list_worktrees(repo)

    abs_path_real = os.path.realpath(abs_path)
    for entry in entries:
        if os.path.realpath(entry.get("worktree", "")) == abs_path_real:
            if entry.get("branch") == branch_name:
                return True, f"任務工作目錄已存在並簽出分支 {branch_name}：{abs_path}"
            return False, (
                f"任務工作目錄 {abs_path} 已存在但簽出分支 "
                f"{entry.get('branch') or '(detached)'}，與要求的 {branch_name} 不符"
            )

    main_branch = entries[0].get("branch", "") if entries else ""
    if main_branch == branch_name:
        return False, (
            f"分支 {branch_name} 正在主工作目錄使用中，"
            "請先將主工作目錄切換到其他分支（未提交變更請先 commit 或 stash）"
        )

    for entry in entries:
        if entry.get("branch") == branch_name:
            return False, f"分支 {branch_name} 已被其他 worktree 簽出：{entry.get('worktree', '')}"

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    if branch_exists(project_dir, branch_name):
        result = _git(repo, "worktree", "add", abs_path, branch_name)
    else:
        result = _git(repo, "worktree", "add", "-b", branch_name, abs_path, "HEAD")

    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        return False, err or f"無法建立任務工作目錄 {abs_path}"

    return True, f"已建立任務工作目錄 {abs_path}，簽出分支 {branch_name}"


def create_worktree_from(
    project_dir: str, change_name: str, branch_name: str, base_branch: str
) -> tuple[bool, str]:
    """以 `base_branch` 的遠端追蹤分支為起點，建立新分支 `branch_name` 與任務工作目錄
    （取代 `create_branch_from`）；主工作目錄不 checkout、不 pull，只 `git fetch`。

    `base_branch` 沒有 upstream 時直接以本地版本為起點。fetch 失敗但本地已有該遠端追蹤
    ref 時仍以它為起點（容器內常無遠端認證）；fetch 失敗又沒有該 ref 則不建立。
    """
    repo = os.path.join(REPO_ROOT, project_dir)
    abs_path = os.path.join(REPO_ROOT, worktree_dir(project_dir, change_name))

    upstream = _git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{base_branch}@{{u}}")
    start_point = base_branch
    note = ""

    if upstream.returncode == 0 and upstream.stdout.strip():
        remote_ref = upstream.stdout.strip()
        remote_name, _, remote_branch = remote_ref.partition("/")
        fetch = _git(repo, "fetch", remote_name, remote_branch or base_branch)
        if fetch.returncode == 0:
            start_point = remote_ref
        else:
            fetch_err = (fetch.stderr or fetch.stdout).strip()
            check = _git(repo, "rev-parse", "--verify", "--quiet", remote_ref)
            if check.returncode != 0:
                return False, f"無法連線遠端且本地無 {remote_ref}：{fetch_err}"
            start_point = remote_ref
            note = f"容器內無法連線遠端、改用本地的遠端追蹤分支 {remote_ref}（{fetch_err}）；"
    else:
        note = f"起點分支 {base_branch} 未設定 upstream，略過同步；"

    _git(repo, "worktree", "prune")
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    result = _git(repo, "worktree", "add", "--no-track", "-b", branch_name, abs_path, start_point)
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        return False, err or f"無法建立任務工作目錄 {abs_path}"

    return True, f"{note}已從 {start_point} 建立任務工作目錄 {abs_path}，分支 {branch_name}"


def commit_all(project_dir: str, change_name: str, message: str) -> tuple[bool, str]:
    """在任務工作目錄 `git add -A` 後 `git commit -m message`；不 push。"""
    abs_path = os.path.join(REPO_ROOT, worktree_dir(project_dir, change_name))

    added = _git(abs_path, "add", "-A")
    if added.returncode != 0:
        return False, (added.stderr or added.stdout).strip() or "git add 失敗"

    committed = _git(abs_path, "commit", "-m", message)
    if committed.returncode != 0:
        return False, (committed.stderr or committed.stdout).strip() or "git commit 失敗"

    return True, (committed.stdout or "").strip() or f"已 commit：{message}"


def remove_worktree(project_dir: str, change_name: str) -> tuple[bool, str]:
    """移除任務工作目錄（`git worktree remove`，不加 `--force`）；工作分支保留。"""
    repo = os.path.join(REPO_ROOT, project_dir)
    abs_path = os.path.join(REPO_ROOT, worktree_dir(project_dir, change_name))

    result = _git(repo, "worktree", "remove", abs_path)
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        return False, err or f"無法移除任務工作目錄 {abs_path}"

    return True, f"已移除任務工作目錄 {abs_path}"


def rollback_except_openspec(project_dir: str, change_name: str) -> tuple[bool, str]:
    """還原任務工作目錄未提交的程式碼變更（含 untracked 新檔），但保留 `openspec/` 目錄不動
    ——規格文件必須留下給後續步驟更新。

    先試 `git stash`；若沒有可 stash 的變更或 stash 失敗，改用 `checkout` + `clean` 還原。
    回傳 `(成功, 訊息)`。
    """
    repo = os.path.join(REPO_ROOT, worktree_dir(project_dir, change_name))

    stash = _git(repo, "stash", "push", "--include-untracked", "--", ".", ":!openspec")
    if stash.returncode == 0:
        msg = (stash.stdout or stash.stderr or "").strip()
        return True, msg or f"{project_dir} 已 stash 未提交的變更（openspec/ 除外）"

    checkout = _git(repo, "checkout", "--", ".", ":!openspec")
    clean = _git(repo, "clean", "-fd", "--exclude=openspec/")
    if checkout.returncode == 0 and clean.returncode == 0:
        return True, f"{project_dir} 已用 checkout + clean 還原未提交的變更（openspec/ 除外）"

    err = (checkout.stderr or clean.stderr or stash.stderr or "rollback 失敗").strip()
    return False, err
