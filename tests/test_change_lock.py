"""core/change_lock.py 的互斥鎖測試（feat-git-worktree-mode）。

Seam：core.change_lock.acquire()，以子行程模擬另一個行程持有鎖；斷言互斥訊息、
行程結束後鎖自動釋放、同一行程重複上鎖視為成功。
"""
import subprocess
import sys

import pytest

from AgentLoop.core import change_lock
from AgentLoop.lib import REPO_ROOT as REAL_REPO_ROOT

_CHILD_SCRIPT = """
import sys, time
from AgentLoop.core import change_lock
change_lock.REPO_ROOT = sys.argv[1]
ok, msg = change_lock.acquire(sys.argv[2], sys.argv[3])
print("OK" if ok else "FAIL", flush=True)
time.sleep(10)
"""


@pytest.fixture
def lock_module(monkeypatch, tmp_path):
    monkeypatch.setattr(change_lock, "REPO_ROOT", str(tmp_path))
    change_lock._open_locks.clear()
    yield change_lock
    change_lock._open_locks.clear()


def _spawn_holder(repo_root: str, project_dir: str, change_name: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-c", _CHILD_SCRIPT, repo_root, project_dir, change_name],
        cwd=REAL_REPO_ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    first_line = proc.stdout.readline().strip()
    assert first_line == "OK", f"子行程未能取得鎖：{first_line}"
    return proc


class TestAcquire:
    def test_second_process_fails_while_first_holds_lock(self, lock_module, tmp_path):
        """Scenario: 兩個子行程對同一任務上鎖時第二個失敗"""
        proc = _spawn_holder(str(tmp_path), "proj", "feat-login")
        try:
            ok, msg = lock_module.acquire("proj", "feat-login")
            assert ok is False
            assert msg == "任務 feat-login 已有執行進行中"
        finally:
            proc.kill()
            proc.wait()

    def test_lock_released_after_process_exits(self, lock_module, tmp_path):
        """Scenario: 第一個行程結束後可再上鎖"""
        proc = _spawn_holder(str(tmp_path), "proj", "feat-login")
        proc.kill()
        proc.wait()

        ok, msg = lock_module.acquire("proj", "feat-login")

        assert ok is True

    def test_same_process_reacquire_is_success(self, lock_module):
        """Scenario: 同一行程重複上鎖視為成功"""
        ok1, _ = lock_module.acquire("proj", "feat-login")
        ok2, _ = lock_module.acquire("proj", "feat-login")

        assert ok1 is True
        assert ok2 is True

    def test_other_change_is_independent(self, lock_module, tmp_path):
        """不同任務互不影響"""
        proc = _spawn_holder(str(tmp_path), "proj", "feat-login")
        try:
            ok, _ = lock_module.acquire("proj", "fix-css")
            assert ok is True
        finally:
            proc.kill()
            proc.wait()
