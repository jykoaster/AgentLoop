"""在目標專案切換／建立 git 分支。"""
import os
import subprocess
from .project_context import REPO_ROOT

_GIT_TIMEOUT = 30


def _git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT,
    )


def ensure_on_branch(project_dir: str, branch_name: str) -> tuple[bool, str]:
    """把 `<workspace>/<project_dir>` 切到 `branch_name`；本地沒有則從目前 HEAD 建立。

    回傳 `(成功, 訊息)`。已在該分支上時視為成功。
    """
    if not project_dir or not branch_name:
        return False, "缺少 project_dir 或 branch_name"

    repo = os.path.join(REPO_ROOT, project_dir)
    inside = _git(repo, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return False, f"{project_dir} 不是 git 工作樹"

    current = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if current.returncode == 0 and current.stdout.strip() == branch_name:
        return True, f"{project_dir} 已在分支 {branch_name}"

    checked_out = _git(repo, "checkout", branch_name)
    if checked_out.returncode == 0:
        return True, f"{project_dir} 已切換到分支 {branch_name}"

    created = _git(repo, "checkout", "-b", branch_name)
    if created.returncode == 0:
        return True, f"{project_dir} 已建立並切換到分支 {branch_name}"

    err = (created.stderr or checked_out.stderr or created.stdout or checked_out.stdout).strip()
    return False, err or f"無法切換到分支 {branch_name}"


def rollback_except_openspec(project_dir: str) -> tuple[bool, str]:
    """還原 `<workspace>/<project_dir>` 未提交的程式碼變更（含 untracked 新檔），
    但保留 `openspec/` 目錄不動——規格文件必須留下給後續步驟更新。

    先試 `git stash`；若沒有可 stash 的變更或 stash 失敗，改用 `checkout` + `clean` 還原。
    回傳 `(成功, 訊息)`。
    """
    repo = os.path.join(REPO_ROOT, project_dir)

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
