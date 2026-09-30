"""
純邏輯單元測試：CLI 參數、state 存讀、_route_after_review、_list_and_select_change、
domain 選擇相關函式。不依賴 Claude CLI，可在容器內直接 pytest 執行。
"""
import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_project(tmp_path):
    """在 tmp_path 內模擬一個目標專案目錄結構。"""
    project = tmp_path / "my-project"
    project.mkdir()
    return tmp_path, project


def _make_state(**overrides) -> dict:
    base = {
        "task": "test task",
        "analysis": "analysis text",
        "plan": ["- [ ] task 1"],
        "execution_result": "",
        "review_result": "",
        "review_level": "",
        "review_blocking": False,
        "status": "pending",
        "iteration": 0,
        "human_feedback": "",
        "change_name": "feat-test",
        "branch_name": "feat/test",
        "project_dir": "my-project",
    }
    base.update(overrides)
    return base


# ── _save_state ───────────────────────────────────────────────────────────────

class TestSaveState:
    def _call(self, state, workspace_root):
        from AgentLoop.main import _save_state
        with patch("AgentLoop.main.REPO_ROOT", str(workspace_root)):
            _save_state(state)

    def test_writes_state_json(self, tmp_project):
        workspace, _ = tmp_project
        state = _make_state()
        self._call(state, workspace)

        state_file = workspace / "my-project" / ".agentloop" / "changes" / "feat-test" / "state.json"
        assert state_file.exists()

    def test_excludes_project_dir(self, tmp_project):
        workspace, _ = tmp_project
        state = _make_state()
        self._call(state, workspace)

        state_file = workspace / "my-project" / ".agentloop" / "changes" / "feat-test" / "state.json"
        data = json.loads(state_file.read_text())
        assert "project_dir" not in data

    def test_all_other_fields_preserved(self, tmp_project):
        workspace, _ = tmp_project
        state = _make_state(review_result="LGTM", iteration=2, review_blocking=True)
        self._call(state, workspace)

        state_file = workspace / "my-project" / ".agentloop" / "changes" / "feat-test" / "state.json"
        data = json.loads(state_file.read_text())
        assert data["review_result"] == "LGTM"
        assert data["iteration"] == 2
        assert data["review_blocking"] is True

    def test_skips_when_no_change_name(self, tmp_project):
        workspace, _ = tmp_project
        state = _make_state(change_name="")
        self._call(state, workspace)

        agentloop = workspace / "my-project" / ".agentloop"
        assert not agentloop.exists()

    def test_skips_when_no_project_dir(self, tmp_project):
        workspace, _ = tmp_project
        state = _make_state(project_dir="")
        self._call(state, workspace)

        agentloop = workspace / "my-project" / ".agentloop"
        assert not agentloop.exists()

    def test_overwrites_on_second_call(self, tmp_project):
        workspace, _ = tmp_project
        state = _make_state(iteration=0)
        self._call(state, workspace)

        state["iteration"] = 1
        self._call(state, workspace)

        state_file = workspace / "my-project" / ".agentloop" / "changes" / "feat-test" / "state.json"
        data = json.loads(state_file.read_text())
        assert data["iteration"] == 1

    def test_surrogate_characters_are_replaced(self, tmp_project):
        """Claude 輸出偶爾含孤立 surrogate，應替換為 replacement character 而非拋例外。"""
        workspace, _ = tmp_project
        state = _make_state(review_result="ok😀bad\udc00end")
        self._call(state, workspace)  # 不應拋出 UnicodeEncodeError

        state_file = workspace / "my-project" / ".agentloop" / "changes" / "feat-test" / "state.json"
        assert state_file.exists()


# ── _route_after_review ───────────────────────────────────────────────────────

class TestRouteAfterReview:
    def _call(self, state):
        from AgentLoop.main import _route_after_review
        return _route_after_review(state)

    def test_passes_goes_to_archive(self):
        state = _make_state(review_blocking=False)
        assert self._call(state) == "archive_change"

    def test_error_returns_none(self):
        state = _make_state(status="error")
        assert self._call(state) is None

    def test_blocking_under_max_goes_to_increment(self):
        from AgentLoop.core import MAX_ITERATIONS
        state = _make_state(review_blocking=True, iteration=MAX_ITERATIONS - 1)
        assert self._call(state) == "increment"

    def test_blocking_at_max_returns_none(self):
        from AgentLoop.core import MAX_ITERATIONS
        state = _make_state(review_blocking=True, iteration=MAX_ITERATIONS)
        assert self._call(state) is None

    def test_blocking_iteration_zero_goes_to_increment(self):
        state = _make_state(review_blocking=True, iteration=0)
        assert self._call(state) == "increment"


# ── _list_and_select_change ───────────────────────────────────────────────────

class TestListAndSelectChange:
    def _make_change(self, workspace, project_name, change_name, state_data=None):
        d = workspace / project_name / ".agentloop" / "changes" / change_name
        d.mkdir(parents=True)
        payload = state_data or {"task": "x", "change_name": change_name}
        (d / "state.json").write_text(json.dumps(payload))

    def _call(self, workspace, target_project, user_input="1"):
        from AgentLoop.main import _list_and_select_change
        with patch("AgentLoop.main.REPO_ROOT", str(workspace)), \
             patch.dict(os.environ, {"TARGET_PROJECT": target_project}), \
             patch("builtins.input", return_value=user_input):
            return _list_and_select_change()

    def test_lists_changes_and_injects_project_dir(self, tmp_project):
        workspace, _ = tmp_project
        self._make_change(workspace, "my-project", "feat-login")

        result = self._call(workspace, "my-project")

        assert result["change_name"] == "feat-login"
        assert result["project_dir"] == "my-project"

    def test_selects_correct_change_by_index(self, tmp_project):
        workspace, _ = tmp_project
        self._make_change(workspace, "my-project", "aaa-change")
        self._make_change(workspace, "my-project", "zzz-change")

        result = self._call(workspace, "my-project", user_input="2")
        assert result["change_name"] == "zzz-change"

    def test_exits_when_no_changes(self, tmp_project):
        """--node 不收任務描述，沒有既有 state 就無事可做——包含 analyze_plan：
        原本「找不到 change 就全新開始」的路徑已移除，全新任務走完整工作流。"""
        workspace, _ = tmp_project

        with pytest.raises(SystemExit):
            self._call(workspace, "my-project")

    def test_exits_when_target_project_not_set(self, tmp_project):
        workspace, _ = tmp_project

        with patch("AgentLoop.main.REPO_ROOT", str(workspace)), \
             patch.dict(os.environ, {}, clear=True):
            from AgentLoop.main import _list_and_select_change
            with pytest.raises(SystemExit):
                _list_and_select_change()

    def test_skips_dirs_without_state_json(self, tmp_project):
        workspace, _ = tmp_project
        empty_dir = workspace / "my-project" / ".agentloop" / "changes" / "no-state"
        empty_dir.mkdir(parents=True)
        self._make_change(workspace, "my-project", "has-state")

        result = self._call(workspace, "my-project")
        assert result["change_name"] == "has-state"


# ── CLI 參數 ──────────────────────────────────────────────────────────────────

class TestCliArgs:
    def _main(self, argv):
        from AgentLoop.main import main
        with patch.object(sys, "argv", ["AgentLoop.main", *argv]):
            main()

    def test_node_rejects_task_description(self):
        """--node 的任務描述會無條件覆蓋 state 裡的原值並被寫回 state.json，
        所以直接拒絕而不是默默忽略——曾有 change 的 task 因此被佔位字串蓋掉。"""
        with pytest.raises(SystemExit) as exc:
            self._main(["--node", "execute", "任務描述"])
        assert exc.value.code == 2

    def test_node_without_task_runs(self):
        with patch("AgentLoop.main.run_node") as mock_run_node:
            self._main(["--node", "execute"])
        mock_run_node.assert_called_once_with("execute")

    def test_full_workflow_requires_task_description(self):
        with pytest.raises(SystemExit) as exc:
            self._main([])
        assert exc.value.code == 2

    def test_full_workflow_runs_with_task_description(self):
        with patch("AgentLoop.main.run") as mock_run:
            self._main(["加一個端點"])
        mock_run.assert_called_once_with("加一個端點")


# ── _list_existing_domains ────────────────────────────────────────────────────

class TestListExistingDomains:
    def _call(self, project_dir, workspace_root):
        from AgentLoop.nodes.analyze_plan import _list_existing_domains
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(workspace_root)):
            return _list_existing_domains(project_dir)

    def test_no_specs_dir(self, tmp_project):
        workspace, _ = tmp_project
        assert self._call("my-project", workspace) == []

    def test_empty_specs_dir(self, tmp_project):
        workspace, project = tmp_project
        (project / "openspec" / "specs").mkdir(parents=True)
        assert self._call("my-project", workspace) == []

    def test_returns_sorted_domain_dirs(self, tmp_project):
        workspace, project = tmp_project
        specs = project / "openspec" / "specs"
        specs.mkdir(parents=True)
        (specs / "users").mkdir()
        (specs / "articles").mkdir()
        assert self._call("my-project", workspace) == ["articles", "users"]

    def test_ignores_files_and_hidden_dirs(self, tmp_project):
        workspace, project = tmp_project
        specs = project / "openspec" / "specs"
        specs.mkdir(parents=True)
        (specs / "articles").mkdir()
        (specs / ".hidden").mkdir()
        (specs / "spec.md").write_text("")
        assert self._call("my-project", workspace) == ["articles"]


# ── _ask_domain_selection ─────────────────────────────────────────────────────

class TestAskDomainSelection:
    """使用 _list_existing_domains mock 隔離檔案系統；builtins.input mock 模擬終端輸入。"""

    def _call(self, domains, inputs):
        from AgentLoop.nodes.analyze_plan import _ask_domain_selection
        with patch("AgentLoop.nodes.analyze_plan._list_existing_domains", return_value=domains), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", side_effect=inputs):
            return _ask_domain_selection("my-project")

    def test_no_existing_domains_returns_empty(self):
        from AgentLoop.nodes.analyze_plan import _ask_domain_selection
        with patch("AgentLoop.nodes.analyze_plan._list_existing_domains", return_value=[]):
            assert _ask_domain_selection("my-project") == ([], "")

    def test_non_interactive_returns_empty(self):
        from AgentLoop.nodes.analyze_plan import _ask_domain_selection
        with patch("AgentLoop.nodes.analyze_plan._list_existing_domains", return_value=["articles"]), \
             patch("sys.stdin.isatty", return_value=False):
            assert _ask_domain_selection("my-project") == ([], "")

    def test_select_existing_domain_by_index(self):
        result = self._call(["articles", "users"], ["1"])
        assert result == (["articles"], "")

    def test_select_multiple_existing_domains(self):
        result = self._call(["articles", "users", "auth"], ["1,3"])
        assert result == (["articles", "auth"], "")

    def test_select_new_domain_with_name(self):
        # domains=["articles","users"] → new_idx=3; user enters "3" then domain name
        result = self._call(["articles", "users"], ["3", "order-management"])
        assert result == ([], "order-management")

    def test_select_new_domain_empty_name(self):
        # user presses Enter on domain name → Claude decides the name
        result = self._call(["articles"], ["2", ""])
        assert result == ([], "")

    def test_invalid_index_retries_then_valid(self):
        result = self._call(["articles", "users"], ["99", "1"])
        assert result == (["articles"], "")

    def test_mix_new_and_existing_retries(self):
        # "1,2" where 2 is new_idx (1 existing domain) → error, retry → pick new with name
        result = self._call(["articles"], ["1,2", "2", "payments"])
        assert result == ([], "payments")

    def test_eof_returns_empty(self):
        from AgentLoop.nodes.analyze_plan import _ask_domain_selection
        with patch("AgentLoop.nodes.analyze_plan._list_existing_domains", return_value=["articles"]), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", side_effect=EOFError):
            assert _ask_domain_selection("my-project") == ([], "")


# ── _recover_domains ──────────────────────────────────────────────────────────

class TestRecoverDomains:
    def test_prefers_state_over_files(self, tmp_project):
        from AgentLoop.nodes.analyze_plan import _recover_domains
        workspace, project = tmp_project
        specs = project / "openspec" / "changes" / "feat-test" / "specs" / "from-folder"
        specs.mkdir(parents=True)
        state_dir = project / ".agentloop" / "changes" / "feat-test"
        state_dir.mkdir(parents=True)
        (state_dir / "state.json").write_text(
            json.dumps({"domains": ["from-json"]}), encoding="utf-8"
        )
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(workspace)):
            assert _recover_domains(
                {"domains": ["from-state"]}, "my-project", "feat-test"
            ) == ["from-state"]

    def test_falls_back_to_state_json(self, tmp_project):
        from AgentLoop.nodes.analyze_plan import _recover_domains
        workspace, project = tmp_project
        state_dir = project / ".agentloop" / "changes" / "feat-test"
        state_dir.mkdir(parents=True)
        (state_dir / "state.json").write_text(
            json.dumps({"domains": ["access-log", "auth"]}), encoding="utf-8"
        )
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(workspace)):
            assert _recover_domains({"domains": []}, "my-project", "feat-test") == [
                "access-log",
                "auth",
            ]

    def test_falls_back_to_change_specs(self, tmp_project):
        from AgentLoop.nodes.analyze_plan import _recover_domains
        workspace, project = tmp_project
        specs = project / "openspec" / "changes" / "feat-test" / "specs"
        (specs / "users").mkdir(parents=True)
        (specs / "articles").mkdir()
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(workspace)):
            assert _recover_domains({}, "my-project", "feat-test") == ["articles", "users"]

    def test_falls_back_to_archived_change_specs(self, tmp_project):
        from AgentLoop.nodes.analyze_plan import _recover_domains
        workspace, project = tmp_project
        archived = (
            project / "openspec" / "changes" / "archive"
            / "2026-09-23-70-feat-access-log-ui-and-api" / "specs" / "access-log"
        )
        archived.mkdir(parents=True)
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(workspace)):
            assert _recover_domains(
                {}, "my-project", "2026-09-23-70-feat-access-log-ui-and-api"
            ) == ["access-log"]

    def test_empty_when_nothing_saved(self, tmp_project):
        from AgentLoop.nodes.analyze_plan import _recover_domains
        workspace, _ = tmp_project
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(workspace)):
            assert _recover_domains({}, "my-project", "feat-test") == []

    def test_rejects_unsafe_change_name(self, tmp_project):
        from AgentLoop.nodes.analyze_plan import _load_saved_domains, _list_change_domains
        workspace, _ = tmp_project
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(workspace)):
            assert _load_saved_domains("my-project", "../escape") == []
            assert _list_change_domains("my-project", "../escape") == []


# ── _build_new_domain_context ─────────────────────────────────────────────────

class TestBuildNewDomainContext:
    def _call(self, name, purpose):
        from AgentLoop.nodes.analyze_plan import _build_new_domain_context
        return _build_new_domain_context(name, purpose)

    def test_no_name_no_purpose_returns_default(self):
        from AgentLoop.nodes.analyze_plan import _DOMAIN_CONTEXT_NEW
        assert self._call("", "") == _DOMAIN_CONTEXT_NEW

    def test_purpose_only_injects_text(self):
        result = self._call("", "管理使用者帳號的功能集合")
        assert "管理使用者帳號的功能集合" in result
        assert "<<DOMAIN_PURPOSE_VALUE>>" not in result

    def test_name_only_injects_name_in_path(self):
        result = self._call("user-management", "")
        assert "user-management" in result
        assert "specs/user-management/spec.md" in result

    def test_name_and_purpose_injects_both(self):
        result = self._call("user-management", "管理使用者帳號")
        assert "user-management" in result
        assert "管理使用者帳號" in result
        assert "specs/user-management/spec.md" in result
