"""lib/git_ops.py 的分支列出／判斷存在／任務工作目錄建立測試（feat-git-worktree-mode）。

Seam：lib/git_ops 的公開函式，以 tmp_path 建立真實 git repo + bare repo 模擬 upstream，
patch git_ops.REPO_ROOT 指向 tmp 目錄；斷言實際 worktree、分支、commit 與回傳 (ok, msg)。
"""
import os
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


def _worktree_path(tmp_path: Path, project: str, change: str) -> Path:
    return tmp_path / ".agentloop-worktrees" / project / change


class TestWorktreeDir:
    def test_returns_path_relative_to_repo_root(self, git_ops):
        assert git_ops.worktree_dir("proj", "feat-login") == os.path.join(
            ".agentloop-worktrees", "proj", "feat-login"
        )


class TestEnsureWorktree:
    def test_creates_from_head_when_branch_missing_locally(self, git_ops, tmp_path):
        """Scenario: 本地無此分支時從主工作目錄 HEAD 建立"""
        repo, _bare = _init_tracked_repo(tmp_path)
        main_head = _head(repo)

        ok, msg = git_ops.ensure_worktree("proj", "feat-login", "feat/login")

        assert ok is True
        wt = _worktree_path(tmp_path, "proj", "feat-login")
        assert wt.is_dir()
        assert _head(wt) == main_head
        assert _current_branch(wt) == "feat/login"
        assert _current_branch(repo) == "main"

    def test_adds_worktree_when_branch_exists_locally(self, git_ops, tmp_path):
        """Scenario: 本地已有該分支時以它建立 worktree"""
        repo, _bare = _init_tracked_repo(tmp_path)
        _git(repo, "checkout", "-b", "feat/login")
        (repo / "x.txt").write_text("x")
        _git(repo, "add", "x.txt")
        _git(repo, "commit", "-m", "on feat/login")
        feat_head = _head(repo)
        _git(repo, "checkout", "main")

        ok, msg = git_ops.ensure_worktree("proj", "feat-login", "feat/login")

        assert ok is True
        wt = _worktree_path(tmp_path, "proj", "feat-login")
        assert _head(wt) == feat_head
        assert _current_branch(wt) == "feat/login"

    def test_already_existing_worktree_with_correct_branch_is_noop(self, git_ops, tmp_path):
        """Scenario: 任務工作目錄已存在且分支正確時不重建，既有未提交檔仍在"""
        _init_tracked_repo(tmp_path)
        ok, _ = git_ops.ensure_worktree("proj", "feat-login", "feat/login")
        assert ok is True
        wt = _worktree_path(tmp_path, "proj", "feat-login")
        (wt / "untracked.txt").write_text("keep me")

        ok2, msg2 = git_ops.ensure_worktree("proj", "feat-login", "feat/login")

        assert ok2 is True
        assert (wt / "untracked.txt").is_file()

    def test_branch_used_by_main_worktree_fails_with_fixed_message(self, git_ops, tmp_path):
        """Scenario: 工作分支為主工作目錄目前分支"""
        repo, _bare = _init_tracked_repo(tmp_path)
        main_head = _head(repo)

        ok, msg = git_ops.ensure_worktree("proj", "feat-main", "main")

        assert ok is False
        assert msg == (
            "分支 main 正在主工作目錄使用中，"
            "請先將主工作目錄切換到其他分支（未提交變更請先 commit 或 stash）"
        )
        assert _head(repo) == main_head
        assert not _worktree_path(tmp_path, "proj", "feat-main").exists()

    def test_branch_checked_out_by_other_worktree_fails(self, git_ops, tmp_path):
        """Scenario: 分支已被其他 worktree 簽出"""
        _init_tracked_repo(tmp_path)
        ok, _ = git_ops.ensure_worktree("proj", "feat-login", "feat/login")
        assert ok is True

        ok2, msg2 = git_ops.ensure_worktree("proj", "feat-login-2", "feat/login")

        assert ok2 is False
        assert not _worktree_path(tmp_path, "proj", "feat-login-2").exists()


class TestCreateWorktreeFrom:
    def test_fetch_succeeds_uses_remote_tracking_commit(self, git_ops, tmp_path):
        """Scenario: 起點分支有 upstream 且 fetch 成功時以遠端追蹤分支最新 commit 為起點"""
        repo, bare = _init_tracked_repo(tmp_path)
        main_head_before = _head(repo)
        remote_head = _push_extra_commit_from_clone(tmp_path, bare, "b.txt", "remote ahead")

        ok, msg = git_ops.create_worktree_from("proj", "feat-login", "feat/login", "main")

        assert ok is True
        wt = _worktree_path(tmp_path, "proj", "feat-login")
        assert _head(wt) == remote_head
        assert _current_branch(wt) == "feat/login"
        assert _head(repo) == main_head_before
        assert _current_branch(repo) == "main"

    def test_fetch_fails_but_local_tracking_ref_exists(self, git_ops, tmp_path, monkeypatch):
        """Scenario: 容器內無法連線遠端時改用本地的遠端追蹤分支"""
        repo, _bare = _init_tracked_repo(tmp_path)
        local_tracking_head = _git(repo, "rev-parse", "origin/main").stdout.strip()

        import AgentLoop.lib.git_ops as module
        real_git = module._git

        def fake_git(repo_path, *git_args):
            if git_args and git_args[0] == "fetch":
                return subprocess.CompletedProcess(
                    args=git_args, returncode=1, stdout="", stderr="could not resolve host",
                )
            return real_git(repo_path, *git_args)

        monkeypatch.setattr(module, "_git", fake_git)

        ok, msg = module.create_worktree_from("proj", "feat-login", "feat/login", "main")

        assert ok is True
        assert "容器內無法連線遠端、改用本地的遠端追蹤分支 origin/main" in msg
        wt = _worktree_path(tmp_path, "proj", "feat-login")
        assert _head(wt) == local_tracking_head

    def test_fetch_fails_and_no_local_tracking_ref(self, git_ops, tmp_path, monkeypatch):
        """Scenario: fetch 失敗且本地無遠端追蹤 ref 時不建立分支與 worktree"""
        repo, _bare = _init_tracked_repo(tmp_path)

        import AgentLoop.lib.git_ops as module
        real_git = module._git

        def fake_git(repo_path, *git_args):
            if git_args and git_args[0] == "fetch":
                return subprocess.CompletedProcess(args=git_args, returncode=1, stdout="", stderr="could not resolve host")
            if git_args[:2] == ("rev-parse", "--verify"):
                return subprocess.CompletedProcess(args=git_args, returncode=1, stdout="", stderr="unknown revision")
            return real_git(repo_path, *git_args)

        monkeypatch.setattr(module, "_git", fake_git)

        ok, msg = module.create_worktree_from("proj", "feat-login", "feat/login", "main")

        assert ok is False
        assert git_ops.branch_exists("proj", "feat/login") is False
        assert not _worktree_path(tmp_path, "proj", "feat-login").exists()

    def test_no_upstream_uses_local_branch_directly(self, git_ops, tmp_path):
        """Scenario: 起點分支無 upstream 時直接以本地起點分支建立、不 fetch"""
        repo, _bare = _init_tracked_repo(tmp_path)
        _git(repo, "checkout", "-b", "local-only")
        (repo / "c.txt").write_text("3")
        _git(repo, "add", "c.txt")
        _git(repo, "commit", "-m", "local only commit")
        local_head = _head(repo)
        _git(repo, "checkout", "main")

        ok, msg = git_ops.create_worktree_from("proj", "feat-x", "feat/x", "local-only")

        assert ok is True
        assert "起點分支 local-only 未設定 upstream，略過同步" in msg
        wt = _worktree_path(tmp_path, "proj", "feat-x")
        assert _head(wt) == local_head
        assert _current_branch(repo) == "main"


class TestCommitAllAndRemoveWorktree:
    def test_commit_all_adds_and_commits_in_worktree(self, git_ops, tmp_path):
        _init_tracked_repo(tmp_path)
        git_ops.ensure_worktree("proj", "feat-login", "feat/login")
        wt = _worktree_path(tmp_path, "proj", "feat-login")
        (wt / "new.txt").write_text("new content")

        ok, msg = git_ops.commit_all("proj", "feat-login", "feat: add new file")

        assert ok is True
        log = _git(wt, "log", "-1", "--format=%s").stdout.strip()
        assert log == "feat: add new file"
        assert _git(wt, "status", "--porcelain").stdout.strip() == ""

    def test_remove_worktree_keeps_branch(self, git_ops, tmp_path):
        repo, _bare = _init_tracked_repo(tmp_path)
        git_ops.ensure_worktree("proj", "feat-login", "feat/login")
        wt = _worktree_path(tmp_path, "proj", "feat-login")
        (wt / "new.txt").write_text("new content")
        git_ops.commit_all("proj", "feat-login", "feat: add new file")

        ok, msg = git_ops.remove_worktree("proj", "feat-login")

        assert ok is True
        assert not wt.exists()
        assert git_ops.branch_exists("proj", "feat/login") is True
