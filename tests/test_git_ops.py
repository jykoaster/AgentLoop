"""lib/git_ops.py 的分支列出／判斷存在／建立測試（feat-new-change-source-branch）。

Seam：lib/git_ops 的公開函式，以 tmp_path 建立真實 git repo + bare repo 模擬 upstream，
patch git_ops.REPO_ROOT 指向 tmp 目錄；斷言實際分支、commit 與回傳 (ok, msg)。
"""
import subprocess
from pathlib import Path

import pytest


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
    )


def _head(cwd: Path) -> str:
    return _git(cwd, "rev-parse", "HEAD").stdout.strip()


def _current_branch(cwd: Path) -> str:
    return _git(cwd, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def _init_tracked_repo(workspace: Path, project: str = "proj") -> tuple[Path, Path]:
    """建一個 bare repo 當 origin，clone 出本地 repo（main 追蹤 origin/main），
    另建不追蹤遠端的 develop 分支。回傳 (repo_dir, bare_dir)。"""
    bare = workspace / "origin.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "-b", "main")

    _git(workspace, "clone", str(bare), project)
    repo = workspace / project
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "a.txt").write_text("1")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    _git(repo, "push", "-u", "origin", "main")
    _git(repo, "checkout", "-b", "develop")
    _git(repo, "checkout", "main")
    return repo, bare


def _push_extra_commit_from_clone(workspace: Path, bare: Path, filename: str, message: str) -> str:
    """模擬另一個貢獻者 clone 同一個 bare repo 後推一個新 commit，回傳該 commit 的 HEAD。"""
    clone_dir = workspace / f"clone-{filename}"
    _git(workspace, "clone", str(bare), clone_dir.name)
    _git(clone_dir, "config", "user.email", "other@example.com")
    _git(clone_dir, "config", "user.name", "Other")
    (clone_dir / filename).write_text(message)
    _git(clone_dir, "add", filename)
    _git(clone_dir, "commit", "-m", message)
    _git(clone_dir, "push", "origin", "main")
    return _head(clone_dir)


@pytest.fixture
def git_ops(monkeypatch, tmp_path):
    from AgentLoop.lib import git_ops as module
    monkeypatch.setattr(module, "REPO_ROOT", str(tmp_path))
    return module


class TestListLocalBranches:
    def test_lists_branches_sorted_with_current(self, git_ops, tmp_path):
        _init_tracked_repo(tmp_path)

        branches, current = git_ops.list_local_branches("proj")

        assert branches == ["develop", "main"]
        assert current == "main"


class TestBranchExists:
    def test_true_for_existing_branch(self, git_ops, tmp_path):
        _init_tracked_repo(tmp_path)
        assert git_ops.branch_exists("proj", "develop") is True

    def test_false_for_missing_branch(self, git_ops, tmp_path):
        _init_tracked_repo(tmp_path)
        assert git_ops.branch_exists("proj", "feat/login") is False


class TestCreateBranchFrom:
    def test_syncs_behind_remote_then_creates_branch(self, git_ops, tmp_path):
        """Scenario: 起點分支落後遠端時先同步再建立工作分支"""
        repo, bare = _init_tracked_repo(tmp_path)
        remote_head = _push_extra_commit_from_clone(tmp_path, bare, "b.txt", "remote ahead")

        ok, msg = git_ops.create_branch_from("proj", "feat/login", "main")

        assert ok is True
        assert "已從 main 建立並切換到分支 feat/login" in msg
        assert _head(repo) == remote_head
        assert _current_branch(repo) == "feat/login"

    def test_skips_sync_when_no_upstream(self, git_ops, tmp_path):
        """Scenario: 起點分支未設定 upstream 時略過同步並從本地版本建立"""
        repo, _bare = _init_tracked_repo(tmp_path)
        _git(repo, "checkout", "-b", "local-only")
        (repo / "c.txt").write_text("3")
        _git(repo, "add", "c.txt")
        _git(repo, "commit", "-m", "local only commit")
        local_head = _head(repo)
        _git(repo, "checkout", "main")

        ok, msg = git_ops.create_branch_from("proj", "feat/x", "local-only")

        assert ok is True
        assert "起點分支 local-only 未設定 upstream，略過 git pull" in msg
        assert _head(repo) == local_head
        assert _current_branch(repo) == "feat/x"

    def test_diverged_remote_fails_without_creating_branch(self, git_ops, tmp_path):
        """Scenario: 起點分支無法快轉時記為錯誤且不建立工作分支"""
        repo, bare = _init_tracked_repo(tmp_path)
        _push_extra_commit_from_clone(tmp_path, bare, "b.txt", "remote diverges")

        (repo / "d.txt").write_text("4")
        _git(repo, "add", "d.txt")
        _git(repo, "commit", "-m", "local diverges")

        ok, msg = git_ops.create_branch_from("proj", "feat/login", "main")

        assert ok is False
        assert "git pull 失敗" in msg
        assert git_ops.branch_exists("proj", "feat/login") is False
