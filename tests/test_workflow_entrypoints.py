"""
Workflow entry point 整合測試：每個 node 作為起點，驗證後續流程的 node 序列正確。

Mock 所有呼叫 Claude CLI 的 node function（不需要真實 API），
只驗證 LangGraph routing 與 config["configurable"]["start_from"] 的行為。

執行：容器內 pytest tests/test_workflow_entrypoints.py
"""
import pytest
from unittest.mock import patch, MagicMock
from AgentLoop.core.workflow import build_workflow, MAX_ITERATIONS


# ── 共用 helpers ──────────────────────────────────────────────────────────────

def _base_state(**overrides) -> dict:
    base = {
        "task": "test task",
        "analysis": "",
        "plan": [],
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


def _tracker(name: str, visited: list, returns: dict):
    """回傳一個會記錄呼叫順序的 mock node function。"""
    def _node(state):
        visited.append(name)
        return returns
    return _node


def _review_pass():
    return {"review_result": "Ready to merge? Yes", "review_level": "", "review_blocking": False}


def _review_block():
    return {"review_result": "Ready to merge? No", "review_level": "修補", "review_blocking": True}


def _stream(app, state, start_from=None):
    s = dict(state)
    if start_from:
        s["start_from"] = start_from
    return list(app.stream(s))


# ── entry point: execute ──────────────────────────────────────────────────────

class TestEntryFromExecute:
    def _build(self, visited, review_returns):
        mocks = {
            "AgentLoop.core.workflow.execute_node": _tracker("execute", visited, {"execution_result": "done"}),
            "AgentLoop.core.workflow.review_node": _tracker("review", visited, review_returns),
            "AgentLoop.core.workflow.archive_node": _tracker("archive_change", visited, {}),
            # 不應被呼叫
            "AgentLoop.core.workflow.analyze_plan_node": _tracker("analyze_plan", visited, {}),
            "AgentLoop.core.workflow.human_confirm_node": _tracker("human_confirm", visited, {}),
        }
        with patch.multiple("AgentLoop.core.workflow", **{k.split(".")[-1]: v for k, v in mocks.items()}):
            return build_workflow()

    def test_execute_review_pass_goes_to_archive(self):
        visited = []
        app = self._build(visited, _review_pass())
        _stream(app, _base_state(), start_from="execute")
        assert visited == ["execute", "review", "archive_change"]

    def test_execute_review_block_then_pass_replans(self):
        visited = []
        call_count = [0]

        def mock_review(state):
            visited.append("review")
            call_count[0] += 1
            if call_count[0] == 1:
                return _review_block()
            return _review_pass()

        def mock_analyze(state):
            visited.append("analyze_plan")
            return {"analysis": "re-planned"}

        def mock_confirm(state):
            visited.append("human_confirm")
            return {"status": "confirmed"}

        def mock_execute(state):
            visited.append("execute")
            return {"execution_result": "done"}

        def mock_archive(state):
            visited.append("archive_change")
            return {}

        with patch("AgentLoop.core.workflow.execute_node", mock_execute), \
             patch("AgentLoop.core.workflow.review_node", mock_review), \
             patch("AgentLoop.core.workflow.archive_node", mock_archive), \
             patch("AgentLoop.core.workflow.analyze_plan_node", mock_analyze), \
             patch("AgentLoop.core.workflow.human_confirm_node", mock_confirm):
            app = build_workflow()
            _stream(app, _base_state(), start_from="execute")

        assert visited[0] == "execute"
        assert visited[1] == "review"
        # replan 後必須經過 analyze_plan → human_confirm → execute → review(pass) → archive
        assert "analyze_plan" in visited
        assert "human_confirm" in visited
        assert visited[-1] == "archive_change"

    def test_execute_review_block_at_max_iterations_ends(self):
        visited = []

        with patch("AgentLoop.core.workflow.execute_node", _tracker("execute", visited, {"execution_result": "done"})), \
             patch("AgentLoop.core.workflow.review_node", _tracker("review", visited, _review_block())), \
             patch("AgentLoop.core.workflow.archive_node", _tracker("archive_change", visited, {})), \
             patch("AgentLoop.core.workflow.analyze_plan_node", _tracker("analyze_plan", visited, {})), \
             patch("AgentLoop.core.workflow.human_confirm_node", _tracker("human_confirm", visited, {})):
            app = build_workflow()
            _stream(app, _base_state(iteration=MAX_ITERATIONS), start_from="execute")

        assert "execute" in visited
        assert "review" in visited
        assert "archive_change" not in visited


# ── entry point: review ───────────────────────────────────────────────────────

class TestEntryFromReview:
    def test_review_pass_goes_to_archive(self):
        visited = []

        with patch("AgentLoop.core.workflow.review_node", _tracker("review", visited, _review_pass())), \
             patch("AgentLoop.core.workflow.archive_node", _tracker("archive_change", visited, {})), \
             patch("AgentLoop.core.workflow.execute_node", _tracker("execute", visited, {})), \
             patch("AgentLoop.core.workflow.analyze_plan_node", _tracker("analyze_plan", visited, {})), \
             patch("AgentLoop.core.workflow.human_confirm_node", _tracker("human_confirm", visited, {})):
            app = build_workflow()
            _stream(app, _base_state(), start_from="review")

        assert visited == ["review", "archive_change"]

    def test_review_block_goes_to_increment_then_replan(self):
        visited = []
        call_count = [0]

        def mock_review(state):
            visited.append("review")
            call_count[0] += 1
            return _review_block() if call_count[0] == 1 else _review_pass()

        def mock_analyze(state):
            visited.append("analyze_plan")
            return {"analysis": "re-planned"}

        def mock_confirm(state):
            visited.append("human_confirm")
            return {"status": "confirmed"}

        def mock_execute(state):
            visited.append("execute")
            return {"execution_result": "done"}

        def mock_archive(state):
            visited.append("archive_change")
            return {}

        with patch("AgentLoop.core.workflow.review_node", mock_review), \
             patch("AgentLoop.core.workflow.analyze_plan_node", mock_analyze), \
             patch("AgentLoop.core.workflow.human_confirm_node", mock_confirm), \
             patch("AgentLoop.core.workflow.execute_node", mock_execute), \
             patch("AgentLoop.core.workflow.archive_node", mock_archive):
            app = build_workflow()
            _stream(app, _base_state(), start_from="review")

        assert visited[0] == "review"
        assert "analyze_plan" in visited
        assert visited[-1] == "archive_change"

    def test_review_block_at_max_iterations_ends_without_archive(self):
        visited = []

        with patch("AgentLoop.core.workflow.review_node", _tracker("review", visited, _review_block())), \
             patch("AgentLoop.core.workflow.archive_node", _tracker("archive_change", visited, {})), \
             patch("AgentLoop.core.workflow.execute_node", _tracker("execute", visited, {})), \
             patch("AgentLoop.core.workflow.analyze_plan_node", _tracker("analyze_plan", visited, {})), \
             patch("AgentLoop.core.workflow.human_confirm_node", _tracker("human_confirm", visited, {})):
            app = build_workflow()
            _stream(app, _base_state(iteration=MAX_ITERATIONS), start_from="review")

        assert visited == ["review"]
        assert "archive_change" not in visited

    def test_review_error_ends_without_archive(self):
        visited = []

        with patch("AgentLoop.core.workflow.review_node",
                   _tracker("review", visited, {"status": "error", "review_result": "err", "review_level": ""})), \
             patch("AgentLoop.core.workflow.archive_node", _tracker("archive_change", visited, {})), \
             patch("AgentLoop.core.workflow.execute_node", _tracker("execute", visited, {})), \
             patch("AgentLoop.core.workflow.analyze_plan_node", _tracker("analyze_plan", visited, {})), \
             patch("AgentLoop.core.workflow.human_confirm_node", _tracker("human_confirm", visited, {})):
            app = build_workflow()
            _stream(app, _base_state(), start_from="review")

        assert "archive_change" not in visited


# ── entry point: analyze_plan ─────────────────────────────────────────────────

class TestEntryFromAnalyzePlan:
    def test_analyze_confirm_execute_review_pass_archive(self):
        visited = []

        with patch("AgentLoop.core.workflow.analyze_plan_node",
                   _tracker("analyze_plan", visited, {"analysis": "plan", "plan": ["- [ ] t1"]})), \
             patch("AgentLoop.core.workflow.human_confirm_node",
                   _tracker("human_confirm", visited, {"status": "confirmed"})), \
             patch("AgentLoop.core.workflow.execute_node",
                   _tracker("execute", visited, {"execution_result": "done"})), \
             patch("AgentLoop.core.workflow.review_node",
                   _tracker("review", visited, _review_pass())), \
             patch("AgentLoop.core.workflow.archive_node",
                   _tracker("archive_change", visited, {})):
            app = build_workflow()
            _stream(app, _base_state())  # default entry = analyze_plan

        assert visited == ["analyze_plan", "human_confirm", "execute", "review", "archive_change"]

    def test_analyze_confirm_aborted_ends(self):
        visited = []

        with patch("AgentLoop.core.workflow.analyze_plan_node",
                   _tracker("analyze_plan", visited, {"analysis": "plan"})), \
             patch("AgentLoop.core.workflow.human_confirm_node",
                   _tracker("human_confirm", visited, {"status": "aborted"})), \
             patch("AgentLoop.core.workflow.execute_node", _tracker("execute", visited, {})), \
             patch("AgentLoop.core.workflow.review_node", _tracker("review", visited, {})), \
             patch("AgentLoop.core.workflow.archive_node", _tracker("archive_change", visited, {})):
            app = build_workflow()
            _stream(app, _base_state())

        assert visited == ["analyze_plan", "human_confirm"]
        assert "execute" not in visited

    def test_analyze_confirm_needs_revision_replans(self):
        visited = []
        call_count = {"confirm": 0}

        def mock_confirm(state):
            visited.append("human_confirm")
            call_count["confirm"] += 1
            return {"status": "needs_revision", "human_feedback": "fix this"} if call_count["confirm"] == 1 \
                else {"status": "confirmed"}

        with patch("AgentLoop.core.workflow.analyze_plan_node",
                   _tracker("analyze_plan", visited, {"analysis": "plan"})), \
             patch("AgentLoop.core.workflow.human_confirm_node", mock_confirm), \
             patch("AgentLoop.core.workflow.execute_node",
                   _tracker("execute", visited, {"execution_result": "done"})), \
             patch("AgentLoop.core.workflow.review_node",
                   _tracker("review", visited, _review_pass())), \
             patch("AgentLoop.core.workflow.archive_node",
                   _tracker("archive_change", visited, {})):
            app = build_workflow()
            _stream(app, _base_state())

        # 第一輪 analyze → confirm(needs_revision) → analyze → confirm(confirmed) → execute → review → archive
        assert visited.count("analyze_plan") == 2
        assert visited.count("human_confirm") == 2
        assert visited[-1] == "archive_change"


# ── default entry point ───────────────────────────────────────────────────────

class TestDefaultEntryPoint:
    def test_no_config_defaults_to_analyze_plan(self):
        visited = []

        with patch("AgentLoop.core.workflow.analyze_plan_node",
                   _tracker("analyze_plan", visited, {"analysis": "plan"})), \
             patch("AgentLoop.core.workflow.human_confirm_node",
                   _tracker("human_confirm", visited, {"status": "aborted"})), \
             patch("AgentLoop.core.workflow.execute_node", _tracker("execute", visited, {})), \
             patch("AgentLoop.core.workflow.review_node", _tracker("review", visited, {})), \
             patch("AgentLoop.core.workflow.archive_node", _tracker("archive_change", visited, {})):
            app = build_workflow()
            list(app.stream(_base_state()))  # no config → default start_from

        assert visited[0] == "analyze_plan"
