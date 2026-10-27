"""nodes/archive.py 的 archive 六步驟測試（feat-git-worktree-mode）。

Seam：archive_node(state)，在 tmp_path 建立真實 git repo，以真實 ensure_worktree／
commit_all／remove_worktree 操作任務工作目錄，mock archive_change／interaction.ask，
斷言 commit 訊息、worktree 移除、分支保留與 archived 旗標。
"""
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 強制正確的 import 順序：core.workflow 必須先於 nodes 子模組載入，
# 否則 workflow.py 試圖從尚未完成初始化的 nodes 套件取用 node functions 會造成 circular import。
import AgentLoop.core.workflow  # noqa: F401


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _init_repo(workspace: Path, project: str = "proj") -> Path:
    repo = workspace / project
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "a.txt").write_text("1")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    return repo


def _base_state(**overrides) -> dict:
    base = {
        "change_name": "feat-login",
        "project_dir": "proj",
        "branch_name": "feat/login",
        "commit_message": "feat: login page",
        "stage_notes": {},
    }
    base.update(overrides)
    return base


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    from AgentLoop.lib import git_ops
    from AgentLoop.nodes import archive as archive_module

    _init_repo(tmp_path, "proj")
    monkeypatch.setattr(git_ops, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(archive_module, "REPO_ROOT", str(tmp_path))
    return tmp_path


def _worktree_path(tmp_path: Path) -> Path:
    return tmp_path / ".agentloop-worktrees" / "proj" / "feat-login"


def _make_worktree_with_change(tmp_path: Path) -> Path:
    """以真實 ensure_worktree 建立任務工作目錄，內含一個 openspec change 與未提交變更。"""
    from AgentLoop.lib import git_ops

    ok, msg = git_ops.ensure_worktree("proj", "feat-login", "feat/login")
    assert ok, msg
    wt = _worktree_path(tmp_path)
    change_dir = wt / "openspec" / "changes" / "feat-login"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text("## Intent\ntest")
    (wt / "app.py").write_text("print('hello')")
    return wt


_OK_ARCHIVE = MagicMock(ok=True, data={"archive": {"archivedAs": "2026-10-19-feat-login"}}, error_text="")


class TestArchiveSixSteps:
    def test_archive_with_commit_message_commits_and_removes_worktree(self, repo_env):
        """Scenario: archive 同意、openspec 成功、有訊息"""
        tmp_path = repo_env
        wt = _make_worktree_with_change(tmp_path)

        with patch("AgentLoop.nodes.archive.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.archive.interaction.ask", return_value="y"), \
             patch("AgentLoop.nodes.archive.archive_change", return_value=_OK_ARCHIVE) as mock_archive:
            from AgentLoop.nodes.archive import archive_node
            result = archive_node(_base_state())

        assert result.get("archived") is True
        assert result.get("status") != "error"
        mock_archive.assert_called_once()
        assert not wt.exists()

        from AgentLoop.lib import git_ops
        assert git_ops.branch_exists("proj", "feat/login") is True
        log = _git(tmp_path / "proj", "log", "-1", "--format=%s", "feat/login").stdout.strip()
        assert log == "feat: login page"

    def test_no_commit_message_is_error_and_worktree_kept(self, repo_env):
        """Scenario: archive 同意、openspec 成功、無訊息"""
        tmp_path = repo_env
        wt = _make_worktree_with_change(tmp_path)

        with patch("AgentLoop.nodes.archive.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.archive.interaction.ask", return_value="y"), \
             patch("AgentLoop.nodes.archive.archive_change", return_value=_OK_ARCHIVE):
            from AgentLoop.nodes.archive import archive_node
            result = archive_node(_base_state(commit_message=""))

        assert result["status"] == "error"
        assert "沒有任務 commit 訊息" in result["stage_notes"]["archive"]
        assert wt.exists()

    def test_already_archived_skips_openspec_archive_then_commits(self, repo_env):
        """Scenario: 前次已 archive 但未 commit，補上訊息後重跑 archive"""
        tmp_path = repo_env
        wt = _make_worktree_with_change(tmp_path)
        shutil.rmtree(wt / "openspec" / "changes" / "feat-login")
        archived_dir = wt / "openspec" / "changes" / "archive" / "2026-10-19-feat-login"
        archived_dir.mkdir(parents=True)
        (archived_dir / "proposal.md").write_text("## Intent\ntest")

        with patch("AgentLoop.nodes.archive.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.archive.interaction.ask", return_value="y"), \
             patch("AgentLoop.nodes.archive.archive_change") as mock_archive:
            from AgentLoop.nodes.archive import archive_node
            result = archive_node(_base_state())

        mock_archive.assert_not_called()
        assert result.get("archived") is True
        assert not wt.exists()

    def test_user_declines_archive_keeps_worktree_untouched(self, repo_env):
        """Scenario: 使用者答不 archive"""
        tmp_path = repo_env
        wt = _make_worktree_with_change(tmp_path)

        with patch("AgentLoop.nodes.archive.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.archive.interaction.ask", return_value="n"), \
             patch("AgentLoop.nodes.archive.archive_change") as mock_archive:
            from AgentLoop.nodes.archive import archive_node
            result = archive_node(_base_state())

        mock_archive.assert_not_called()
        assert result == {}
        assert wt.exists()
        assert (wt / "app.py").is_file()

    def test_commit_all_failure_keeps_worktree_and_is_error(self, repo_env):
        """commit_all 失敗 → status error、worktree 保留"""
        tmp_path = repo_env
        wt = _make_worktree_with_change(tmp_path)

        with patch("AgentLoop.nodes.archive.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.archive.interaction.ask", return_value="y"), \
             patch("AgentLoop.nodes.archive.archive_change", return_value=_OK_ARCHIVE), \
             patch("AgentLoop.nodes.archive.commit_all", return_value=(False, "git commit 失敗")):
            from AgentLoop.nodes.archive import archive_node
            result = archive_node(_base_state())

        assert result["status"] == "error"
        assert wt.exists()

    def test_ensure_worktree_failure_is_error(self, repo_env):
        """ensure_worktree 失敗 → status error"""
        with patch("AgentLoop.nodes.archive.ensure_worktree", return_value=(False, "分支 feat/login 正在主工作目錄使用中")):
            from AgentLoop.nodes.archive import archive_node
            result = archive_node(_base_state())

        assert result["status"] == "error"
