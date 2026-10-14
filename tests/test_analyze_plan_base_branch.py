"""初始規劃時選擇起點分支並先同步才建立工作分支（feat-new-change-source-branch）。

Seam：analyze_plan_node(state)，沿用 tests/test_node_guards.py 的 patch 慣例：patch
interaction.ask／interaction.is_interactive、branch_exists、list_local_branches、
create_branch_from、ensure_on_branch、call_claude，斷言提示選項、呼叫參數與 status。
"""
from unittest.mock import patch, MagicMock

import AgentLoop.core.workflow  # noqa: F401 強制正確的 import 順序（見 test_node_guards.py 說明）


def _mock_claude_result(text: str = "完成") -> MagicMock:
    r = MagicMock()
    r.is_error = False
    r.text = text
    r.session_id = None
    r.input_tokens = 0
    r.output_tokens = 0
    r.cache_read_tokens = 0
    r.cache_write_tokens = 0
    return r


def _base_state(**overrides) -> dict:
    base = {
        "task": "新增登入頁",
        "analysis": "",
        "plan": [],
        "execution_result": "",
        "review_result": "",
        "review_level": "",
        "review_blocking": False,
        "status": "pending",
        "iteration": 0,
        "human_feedback": "",
        "change_name": "feat-login",
        "branch_name": "feat/login",
        "project_dir": "my-project",
        "domains": ["auth"],
        "skip_specs": True,
        "start_from": "",
    }
    base.update(overrides)
    return base


_OK = MagicMock(ok=True, error_text="")


class TestAsksBaseBranchWhenMissing:
    def test_lists_branches_and_creates_from_selected_branch(self):
        """Scenario: 工作分支不存在時列出本地分支並以使用者選的分支為起點"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state()
        with patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=False), \
             patch("AgentLoop.nodes.analyze_plan.list_local_branches",
                   return_value=(["develop", "main"], "develop")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask", return_value="2") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan.create_branch_from",
                   return_value=(True, "my-project 已從 main 建立並切換到分支 feat/login")) as mock_create, \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=_OK), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=_OK), \
             patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        assert mock_ask.call_args.kwargs["options"] == ["1. develop（目前分支）", "2. main"]
        mock_create.assert_called_once_with("my-project", "feat/login", "main")
        assert result["status"] != "error"

    def test_blank_answer_uses_current_branch(self):
        """Scenario: 起點分支提問直接送出空白時以目前分支為起點"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state()
        with patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=False), \
             patch("AgentLoop.nodes.analyze_plan.list_local_branches",
                   return_value=(["develop", "main"], "develop")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask", return_value=""), \
             patch("AgentLoop.nodes.analyze_plan.create_branch_from",
                   return_value=(True, "ok")) as mock_create, \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=_OK), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=_OK), \
             patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        mock_create.assert_called_once_with("my-project", "feat/login", "develop")
        assert result["status"] != "error"

    def test_invalid_number_reasks_then_accepts(self):
        """Scenario: 起點分支提問輸入無效編號時重新詢問"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state()
        with patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=False), \
             patch("AgentLoop.nodes.analyze_plan.list_local_branches",
                   return_value=(["develop", "main"], "develop")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask",
                   side_effect=["9", "1"]) as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan.create_branch_from",
                   return_value=(True, "ok")) as mock_create, \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=_OK), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=_OK), \
             patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        assert mock_ask.call_count == 2
        mock_create.assert_called_once_with("my-project", "feat/login", "develop")
        assert result["status"] != "error"


class TestExistingBranchSkipsQuestion:
    def test_existing_branch_switches_directly_without_asking(self):
        """Scenario: 工作分支已存在時直接切換不詢問起點分支"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state()
        with patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")) as mock_ensure, \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=_OK), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=_OK), \
             patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        mock_ask.assert_not_called()
        mock_ensure.assert_called_once_with("my-project", "feat/login")
        assert result["status"] != "error"


class TestNonInteractiveUsesCurrentBranch:
    def test_non_interactive_skips_question_uses_current_branch(self):
        """Scenario: 非互動式環境以目前分支為起點建立工作分支"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state()
        with patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=False), \
             patch("AgentLoop.nodes.analyze_plan.list_local_branches",
                   return_value=(["develop", "main"], "develop")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=False), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan.create_branch_from",
                   return_value=(True, "ok")) as mock_create, \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=_OK), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=_OK), \
             patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        mock_ask.assert_not_called()
        mock_create.assert_called_once_with("my-project", "feat/login", "develop")
        assert result["status"] != "error"


class TestAbortBaseBranchQuestionIsError:
    def test_abort_is_error_and_does_not_call_claude(self):
        """Scenario: 使用者中止起點分支提問時記為錯誤"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state()
        with patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=False), \
             patch("AgentLoop.nodes.analyze_plan.list_local_branches",
                   return_value=(["develop", "main"], "develop")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask", side_effect=KeyboardInterrupt), \
             patch("AgentLoop.nodes.analyze_plan.call_claude") as mock_claude:
            result = analyze_plan_node(state)

        mock_claude.assert_not_called()
        assert result["status"] == "error"
        assert "feat/login" in result["analysis"]


class TestSyncFailureIsError:
    def test_non_ff_failure_is_error_and_branch_not_created(self):
        """Scenario: 起點分支無法快轉時記為錯誤且不建立工作分支"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state()
        with patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=False), \
             patch("AgentLoop.nodes.analyze_plan.list_local_branches",
                   return_value=(["develop", "main"], "develop")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask", return_value="2"), \
             patch("AgentLoop.nodes.analyze_plan.create_branch_from",
                   return_value=(False, "git pull 失敗：non-fast-forward")), \
             patch("AgentLoop.nodes.analyze_plan.call_claude") as mock_claude:
            result = analyze_plan_node(state)

        mock_claude.assert_not_called()
        assert result["status"] == "error"
        assert "feat/login" in result["analysis"]
        assert "git pull 失敗" in result["analysis"]
