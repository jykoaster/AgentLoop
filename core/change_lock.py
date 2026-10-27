"""同一任務（change）同時最多一個執行的互斥鎖。

鎖檔固定在主工作目錄 `<project_dir>/.agentloop/changes/<change_name>/run.lock`，以
`fcntl.flock` 上鎖；檔案描述子存在模組層的 `_open_locks`，行程結束（含被 SIGKILL）時
由 OS 自動釋放，不需要任何清理程式碼。
"""
import fcntl
import os

from ..lib import REPO_ROOT

_open_locks: dict[tuple[str, str], object] = {}


def _lock_path(project_dir: str, change_name: str) -> str:
    return os.path.join(REPO_ROOT, project_dir, ".agentloop", "changes", change_name, "run.lock")


def acquire(project_dir: str, change_name: str) -> tuple[bool, str]:
    """取得任務 `change_name` 的執行鎖。同一行程重複呼叫視為成功（不重新 flock）。"""
    key = (project_dir, change_name)
    if key in _open_locks:
        return True, f"任務 {change_name} 已由本行程持有執行鎖"

    path = _lock_path(project_dir, change_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fh = open(path, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False, f"任務 {change_name} 已有執行進行中"

    _open_locks[key] = fh
    return True, f"任務 {change_name} 已取得執行鎖"
