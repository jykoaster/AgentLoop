"""
analyze_plan 失敗後重跑時重新執行原本的規劃（feat-analyze-failed-retry）。

Seam：analyze_plan_node(state)，沿用 tests/test_analyze_adjust.py 的 patch 方式與
_mock_claude_result／_base_state helper，斷言 interaction.ask 的提問內容、送進 Claude
的 prompt 屬於哪一種模式、回傳的 status／planned／replan_failed／task。
"""
from unittest.mock import patch, MagicMock

import AgentLoop.core.workflow  # noqa: F401 強制正確的 import 順序（見 test_node_guards.py 說明）
from AgentLoop.tests.test_analyze_adjust import _mock_claude_result
from AgentLoop.tests.test_analyze_adjust import _base_state as _adjust_base_state


def _base_state(**overrides) -> dict:
    """薄包裝 test_analyze_adjust._base_state：本檔案的情境預設「尚未成功規劃過」，
    覆寫其 analysis／plan 等欄位預設值，呼叫端的 overrides 優先。"""
    defaults = {
        "analysis": "",
        "plan": [],
        "session_node": "",
        "session_id": "",
        "planned": False,
        "replan_failed": False,
    }
    defaults.update(overrides)
    return _adjust_base_state(**defaults)


class TestInitialPlanFailureRetryRedoesInitialPlan:
    def test_initial_failure_retry_redoes_initial_plan_without_asking_adjustment(self):
        """Scenario: 初始規劃失敗後重跑 analyze_plan 重新執行初始規劃且不詢問調整內容"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            planned=False,
            analysis="Claude 執行失敗：逾時",
            plan=[],
            skip_specs=False,
            domains=["auth"],
            start_from="analyze_plan",
        )
        captured_prompt: dict = {}

        def _capture(prompt, **kwargs):
            captured_prompt["prompt"] = prompt
            return _mock_claude_result("規劃完成")

        with patch("AgentLoop.nodes.analyze_plan.call_claude", side_effect=_capture), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=MagicMock(ok=True, error_text="")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=MagicMock(ok=True, error_text="")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("proposal 全文", ["- [ ] 1.1 新增登入表單"]),
             ):
            result = analyze_plan_node(state)

        mock_ask.assert_not_called()
        assert "「分析與規劃」階段" in captured_prompt["prompt"]
        assert result["status"] == "pending"
        assert result["planned"] is True
        assert result["task"] == "新增登入頁"
        assert "調整 1：" not in result["task"]


class TestInitialPlanInterruptedByUsageLimitResumes:
    def test_initial_plan_usage_limit_interrupt_resumes_session_without_asking(self):
        """Scenario: 初始規劃因用量上限中斷後重跑接回原 session 續作"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            planned=False,
            analysis="[claude 執行失敗] You've hit your session limit",
            plan=[],
            skip_specs=False,
            domains=["auth"],
            session_node="analyze_plan",
            session_id="s1",
            start_from="analyze_plan",
        )

        mock_call = MagicMock(return_value=_mock_claude_result("規劃完成"))

        with patch("AgentLoop.nodes.analyze_plan.call_claude", mock_call), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=MagicMock(ok=True, error_text="")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=MagicMock(ok=True, error_text="")), \
             patch("AgentLoop.nodes.analyze_plan.build_skills_block", return_value="skill"), \
             patch("AgentLoop.nodes.analyze_plan.build_project_doc_hint_for", return_value=""), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("proposal 全文", ["- [ ] 1.1 新增登入表單"]),
             ):
            result = analyze_plan_node(state)

        mock_ask.assert_not_called()
        assert mock_call.call_args.kwargs["resume"] == "s1"
        assert result["planned"] is True


class TestAlreadyPlannedAdjustmentFailureStillAsksAdjustmentContent:
    def test_planned_true_after_failed_adjustment_still_asks_for_adjustment_content(self):
        """Scenario: 已完成過規劃的任務調整失敗後重跑仍詢問調整內容"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            planned=True,
            analysis="未提供調整內容，無法調整規劃",
            plan=[],
            start_from="analyze_plan",
        )
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch(
                 "AgentLoop.nodes.analyze_plan.interaction.ask",
                 return_value="登入失敗三次後鎖定帳號 5 分鐘",
             ) as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("analysis updated", ["- [ ] 新增帳號鎖定"]),
             ):
            analyze_plan_node(state)

        first_call = mock_ask.call_args_list[0]
        assert first_call.args[0] == "請輸入本次要調整的內容"
        assert first_call.kwargs["kind"] == "text"


class TestLegacyStateWithoutPlannedField:
    def test_legacy_state_with_nonempty_plan_is_treated_as_planned(self):
        """舊 state 無 planned、plan 非空 → 視為已完成規劃→調整"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            plan=["- [x] 1.1 新增登入表單"],
            start_from="analyze_plan",
        )
        del state["planned"]
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=MagicMock(ok=True, error_text="")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=MagicMock(ok=True, error_text="")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch(
                 "AgentLoop.nodes.analyze_plan.interaction.ask",
                 return_value="登入失敗三次後鎖定帳號 5 分鐘",
             ) as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("analysis updated", ["- [ ] 新增帳號鎖定"]),
             ):
            analyze_plan_node(state)

        first_call = mock_ask.call_args_list[0]
        assert first_call.args[0] == "請輸入本次要調整的內容"

    def test_legacy_state_with_empty_plan_and_no_tasks_file_is_treated_as_unplanned(self, tmp_path):
        """舊 state 無 planned、plan=[]、change 資料夾無 tasks.md → 視為未完成規劃→初始規劃"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(plan=[], skip_specs=False, start_from="analyze_plan")
        del state["planned"]
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(tmp_path)), \
             patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=MagicMock(ok=True, error_text="")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=MagicMock(ok=True, error_text="")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("proposal 全文", ["- [ ] 1.1 新增登入表單"]),
             ):
            analyze_plan_node(state)

        mock_ask.assert_not_called()


class TestPlannedFlagRetainedOnRepeatedFailure:
    def test_initial_plan_failure_keeps_planned_false(self):
        """初始規劃失敗時回傳 status="error" 且 planned 維持 False"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(planned=False, analysis="", plan=[], skip_specs=True, start_from="analyze_plan")
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("失敗", is_error=True)), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.branch_exists", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=MagicMock(ok=True, error_text="")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=MagicMock(ok=True, error_text="")), \
             patch("AgentLoop.nodes.analyze_plan.build_skills_block", return_value="skill"), \
             patch("AgentLoop.nodes.analyze_plan.build_project_doc_hint_for", return_value=""), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True):
            result = analyze_plan_node(state)

        assert result["status"] == "error"
        assert result["planned"] is False

    def test_adjustment_failure_keeps_planned_true(self):
        """planned=True 時失敗回傳仍為 True"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(planned=True, analysis="existing analysis", start_from="analyze_plan")
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("失敗", is_error=True)), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.build_skills_block", return_value="skill"), \
             patch("AgentLoop.nodes.analyze_plan.build_project_doc_hint_for", return_value=""), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask", return_value="登入失敗三次後鎖定帳號 5 分鐘"):
            result = analyze_plan_node(state)

        assert result["status"] == "error"
        assert result["planned"] is True


class TestReplanFailureRetryRedoesReplanWithoutModeChoice:
    def test_replan_failure_retry_redoes_replan_without_mode_choice(self):
        """Scenario: 依審查結果重新規劃失敗後重跑 analyze_plan 直接重新規劃且不出現選擇題"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            planned=True,
            analysis="上次重新規劃失敗：驗證錯誤",
            review_result="Ready to merge? No\nREVIEW_LEVEL: 修補",
            review_level="修補",
            review_blocking=True,
            replan_failed=True,
            start_from="analyze_plan",
        )
        captured_prompt: dict = {}

        def _capture(prompt, **kwargs):
            captured_prompt["prompt"] = prompt
            return _mock_claude_result("規劃完成")

        with patch("AgentLoop.nodes.analyze_plan.call_claude", side_effect=_capture), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("analysis updated", ["- [x] 1.1 新增登入表單"]),
             ):
            result = analyze_plan_node(state)

        mock_ask.assert_not_called()
        assert "「重新分析與規劃」階段" in captured_prompt["prompt"]
        assert result["replan_failed"] is False
        assert result["task"] == "新增登入頁"


class TestReplanFailureKeepsReplanFailedFlag:
    def test_replan_claude_failure_without_session_sets_replan_failed_true(self):
        """依審查結果重新規劃時 Claude 失敗（無 session）回傳 status="error"、replan_failed=True"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            planned=True,
            review_result="Ready to merge? No\nREVIEW_LEVEL: 修補",
            review_level="修補",
            review_blocking=True,
            replan_failed=False,
            start_from="analyze_plan",
        )
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("失敗", is_error=True)), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask", return_value="1"):
            result = analyze_plan_node(state)

        assert result["status"] == "error"
        assert result["replan_failed"] is True
        assert result["review_blocking"] is True

    def test_choosing_adjustment_then_failing_sets_replan_failed_false(self):
        """選擇題選「輸入調整內容」、輸入內容後 Claude 失敗 → replan_failed=False、human_feedback 為輸入內容"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            planned=True,
            review_result="Ready to merge? No\nREVIEW_LEVEL: 修補",
            review_level="修補",
            review_blocking=True,
            replan_failed=False,
            start_from="analyze_plan",
        )
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("失敗", is_error=True)), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch(
                 "AgentLoop.nodes.analyze_plan.interaction.ask",
                 side_effect=["2", "改用簡訊驗證碼登入"],
             ):
            result = analyze_plan_node(state)

        assert result["status"] == "error"
        assert result["replan_failed"] is False
        assert result["human_feedback"] == "改用簡訊驗證碼登入"


class TestHumanReviseFailureRetryReusesSameFeedback:
    def test_human_revise_failure_retry_reuses_same_feedback(self):
        """Scenario: 依人工意見調整失敗後重跑 analyze_plan 以同一份修改意見重新執行"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            planned=True,
            human_feedback="密碼至少 12 碼",
            analysis="上次依人工意見調整失敗：openspec validate 錯誤",
            start_from="analyze_plan",
        )
        captured_prompt: dict = {}

        def _capture(prompt, **kwargs):
            captured_prompt["prompt"] = prompt
            return _mock_claude_result("規劃完成")

        with patch("AgentLoop.nodes.analyze_plan.call_claude", side_effect=_capture), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("analysis updated", ["- [x] 1.1 新增登入表單"]),
             ):
            result = analyze_plan_node(state)

        mock_ask.assert_not_called()
        assert "密碼至少 12 碼" in captured_prompt["prompt"]
        assert result["task"] == "新增登入頁"
        assert "調整" not in result["task"]
