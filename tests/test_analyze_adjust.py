"""
「對同一個任務進行調整」功能測試（feat-adjust-plan）。

Seam：analyze_plan_node(state)，patch call_claude／ensure_on_branch／_run_with_validate／
_read_change_artifacts／interaction.ask／interaction.is_interactive，斷言回傳的
task／human_feedback／status／iteration，interaction.ask 的呼叫參數，以及送進
call_claude 的 prompt 是否含調整內容。
"""
from pathlib import Path
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
        "analysis": "existing analysis",
        "plan": ["- [x] 1.1 新增登入表單"],
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
        "skip_specs": False,
        "start_from": "",
    }
    base.update(overrides)
    return base


class TestAdjustMainPath:
    def test_rerun_after_review_passed_asks_for_adjustment_content_and_updates_change(self):
        """Scenario: 對已通過審查的任務重跑 analyze_plan 並輸入調整內容後更新同一個 change"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            review_result="## Standards\nok\n## Spec\nok\nReady to merge? Yes",
            review_blocking=False,
            iteration=2,
            start_from="analyze_plan",
        )
        captured_prompt: dict = {}

        def _capture(prompt, **kwargs):
            captured_prompt["prompt"] = prompt
            return _mock_claude_result("規劃完成")

        with patch("AgentLoop.nodes.analyze_plan.call_claude", side_effect=_capture), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch(
                 "AgentLoop.nodes.analyze_plan.interaction.ask",
                 return_value="登入失敗三次後鎖定帳號 5 分鐘",
             ) as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("analysis updated", ["- [x] 1.1 新增登入表單", "- [ ] 新增帳號鎖定"]),
             ):
            result = analyze_plan_node(state)

        mock_ask.assert_called_once()
        call = mock_ask.call_args
        assert call.args[0] == "請輸入本次要調整的內容"
        assert call.kwargs["kind"] == "text"
        assert call.kwargs["required"] is True

        assert "登入失敗三次後鎖定帳號 5 分鐘" in captured_prompt["prompt"]
        assert result["status"] == "pending"
        assert result["iteration"] == 0
        assert result["task"] == "新增登入頁\n\n調整 1：登入失敗三次後鎖定帳號 5 分鐘"
        assert result["review_result"] == ""
        assert result["review_blocking"] is False


class TestAdjustMissingContent:
    """Scenario: 未提供調整內容時 analyze_plan 記為錯誤且任務紀錄不變"""

    def test_keyboard_interrupt_is_error_and_task_unchanged(self):
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(start_from="analyze_plan")
        with patch("AgentLoop.nodes.analyze_plan.call_claude") as mock_claude, \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask", side_effect=KeyboardInterrupt):
            result = analyze_plan_node(state)

        mock_claude.assert_not_called()
        assert result["status"] == "error"
        assert "未提供調整內容，無法調整規劃" in result["analysis"]
        assert result["task"] == state["task"]

    def test_non_interactive_is_error_and_task_unchanged(self):
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(start_from="analyze_plan")
        with patch("AgentLoop.nodes.analyze_plan.call_claude") as mock_claude, \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=False):
            result = analyze_plan_node(state)

        mock_claude.assert_not_called()
        assert result["status"] == "error"
        assert "未提供調整內容，無法調整規劃" in result["analysis"]
        assert result["task"] == state["task"]


class TestAdjustSecondTime:
    def test_second_adjustment_appends_with_next_number_and_keeps_first(self):
        """Scenario: 第二次調整以下一個編號附加且保留先前的調整"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            task="新增登入頁\n\n調整 1：登入失敗三次後鎖定帳號 5 分鐘",
            start_from="analyze_plan",
        )
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask", return_value="鎖定時間改為 10 分鐘"), \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("analysis updated", ["- [x] 1.1 新增登入表單"]),
             ):
            result = analyze_plan_node(state)

        assert result["task"] == (
            "新增登入頁\n\n調整 1：登入失敗三次後鎖定帳號 5 分鐘\n\n調整 2：鎖定時間改為 10 分鐘"
        )


class TestAdjustInterruptedResume:
    def test_interrupted_adjustment_resumes_session_without_reasking(self):
        """Scenario: 調整被中止後重跑 analyze_plan 接回原 session 且不重複附加調整"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        interrupted_result = _mock_claude_result("[錯誤] claude 執行逾時")
        interrupted_result.is_error = True
        interrupted_result.session_id = "s-1"

        state1 = _base_state(
            task="新增登入頁\n\n調整 1：登入失敗三次後鎖定帳號 5 分鐘",
            start_from="analyze_plan",
        )
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=interrupted_result), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask", return_value="鎖定時間改為 10 分鐘"):
            first = analyze_plan_node(state1)

        assert first["status"] == "error"
        assert first["session_node"] == "analyze_plan"
        assert first["session_id"] == "s-1"
        assert first["human_feedback"] == "鎖定時間改為 10 分鐘"
        assert first["task"] == (
            "新增登入頁\n\n調整 1：登入失敗三次後鎖定帳號 5 分鐘\n\n調整 2：鎖定時間改為 10 分鐘"
        )

        state2 = _base_state(
            task=first["task"],
            human_feedback=first["human_feedback"],
            review_result=first["review_result"],
            review_blocking=first["review_blocking"],
            start_from="analyze_plan",
        )
        state2["session_node"] = first["session_node"]
        state2["session_id"] = first["session_id"]

        captured_calls: list = []

        def _capture(prompt, **kwargs):
            captured_calls.append(kwargs)
            return _mock_claude_result("規劃完成")

        with patch("AgentLoop.nodes.analyze_plan.call_claude", side_effect=_capture), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("analysis updated", ["- [x] 1.1 新增登入表單"]),
             ):
            second = analyze_plan_node(state2)

        mock_ask.assert_not_called()
        assert captured_calls[0]["resume"] == "s-1"
        assert "調整 3" not in second["task"]
        assert second["task"] == state2["task"]


# ── 審查退回時的模式選擇 ─────────────────────────────────────────────────────────

class TestRerunModeChoiceAfterReviewRejection:
    def test_choosing_adjustment_asks_mode_then_content(self):
        """Scenario: 審查退回後重跑 analyze_plan 選擇輸入調整內容"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            task="新增登入頁",
            review_result="Ready to merge? No\nREVIEW_LEVEL: 修補",
            review_level="修補",
            review_blocking=True,
            start_from="analyze_plan",
        )
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch(
                 "AgentLoop.nodes.analyze_plan.interaction.ask",
                 side_effect=["2", "改用簡訊驗證碼登入"],
             ) as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("analysis updated", ["- [x] 1.1 新增登入表單"]),
             ):
            result = analyze_plan_node(state)

        assert mock_ask.call_count == 2
        first_call, second_call = mock_ask.call_args_list
        assert first_call.kwargs["kind"] == "choice"
        assert first_call.kwargs["options"] == ["1. 依審查結果重新規劃", "2. 輸入調整內容"]
        assert second_call.kwargs["kind"] == "text"
        assert result["task"] == "新增登入頁\n\n調整 1：改用簡訊驗證碼登入"
        assert result["review_result"] == ""

    def test_choosing_replan_only_asks_once_and_keeps_review_prompt(self):
        """Scenario: 審查退回後重跑 analyze_plan 選擇依審查結果重新規劃"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            task="新增登入頁",
            review_result="Ready to merge? No\nREVIEW_LEVEL: 修補",
            review_level="修補",
            review_blocking=True,
            start_from="analyze_plan",
        )
        captured_prompt: dict = {}

        def _capture(prompt, **kwargs):
            captured_prompt["prompt"] = prompt
            return _mock_claude_result("規劃完成")

        with patch("AgentLoop.nodes.analyze_plan.call_claude", side_effect=_capture), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch(
                 "AgentLoop.nodes.analyze_plan.interaction.ask", return_value="1",
             ) as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("analysis updated", ["- [x] 1.1 新增登入表單"]),
             ):
            result = analyze_plan_node(state)

        mock_ask.assert_called_once()
        assert "Ready to merge? No" in captured_prompt["prompt"]
        assert result["task"] == "新增登入頁"

    def test_internal_workflow_rerun_does_not_ask_and_replans_directly(self):
        """邊界：start_from 不是 analyze_plan（工作流內部自動重新規劃）時不呼叫 ask，直接 replan"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            task="新增登入頁",
            review_result="Ready to merge? No\nREVIEW_LEVEL: 修補",
            review_level="修補",
            review_blocking=True,
            start_from="",
        )
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("analysis updated", ["- [x] 1.1 新增登入表單"]),
             ):
            result = analyze_plan_node(state)

        mock_ask.assert_not_called()
        assert result["task"] == "新增登入頁"


# ── 非重跑入口但已規劃 ───────────────────────────────────────────────────────────

class TestAlreadyPlannedButNotRerunEntry:
    def test_non_rerun_entry_with_existing_analysis_is_error_and_task_unchanged(self):
        """design §2 第 6 條：analysis 非空、非重跑入口、無 human_feedback、無尚未處理的審查退回"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            task="新增登入頁",
            start_from="",
            human_feedback="",
            review_blocking=False,
        )
        with patch("AgentLoop.nodes.analyze_plan.call_claude") as mock_claude, \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask") as mock_ask:
            result = analyze_plan_node(state)

        mock_claude.assert_not_called()
        mock_ask.assert_not_called()
        assert result["status"] == "error"
        assert result["analysis"] == "此 change 已完成規劃，請以重跑 analyze_plan 進行調整"
        assert result["task"] == "新增登入頁"


# ── 已封存任務 ────────────────────────────────────────────────────────────────

class TestArchivedChangeCannotBeAdjusted:
    def test_rerun_on_archived_change_is_error_before_any_question(self, tmp_path):
        """Scenario: 對已封存任務重跑 analyze_plan 時記為錯誤並提示改用新任務"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        archive_root = tmp_path / "my-project" / "openspec" / "changes" / "archive"
        (archive_root / "2026-10-13-feat-login").mkdir(parents=True)

        state = _base_state(change_name="feat-login", start_from="analyze_plan")
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(tmp_path)), \
             patch("AgentLoop.nodes.analyze_plan.interaction.ask") as mock_ask:
            result = analyze_plan_node(state)

        mock_ask.assert_not_called()
        assert result["status"] == "error"
        assert result["analysis"] == "此 change 已封存，請以新任務進行後續修改"


# ── Prompt 調整：保留已完成的待辦項目 ────────────────────────────────────────────

class TestAdjustPromptKeepsCheckedTasks:
    def test_adjustment_prompt_includes_keep_checked_rule_and_content(self):
        """Scenario: 已執行過的任務調整後執行計畫同時列出已完成項目與新增的待辦項目"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            task="新增登入頁",
            start_from="analyze_plan",
        )
        captured_prompt: dict = {}

        def _capture(prompt, **kwargs):
            captured_prompt["prompt"] = prompt
            return _mock_claude_result("規劃完成")

        with patch("AgentLoop.nodes.analyze_plan.call_claude", side_effect=_capture), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.interaction.is_interactive", return_value=True), \
             patch(
                 "AgentLoop.nodes.analyze_plan.interaction.ask",
                 return_value="登入失敗三次後鎖定帳號 5 分鐘",
             ), \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch(
                 "AgentLoop.nodes.analyze_plan._read_change_artifacts",
                 return_value=("analysis updated", ["- [x] 1.1 新增登入表單", "- [ ] 新增帳號鎖定"]),
             ):
            analyze_plan_node(state)

        prompt = captured_prompt["prompt"]
        assert prompt.count("既有 `- [x]` 維持原文") == 1
        assert "登入失敗三次後鎖定帳號 5 分鐘" in prompt

    def test_replan_prompt_also_includes_keep_checked_rule(self):
        """Scenario: 已執行過的任務調整後執行計畫同時列出已完成項目與新增的待辦項目（replan／修補模式）"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            task="新增登入頁",
            review_result="Ready to merge? No\nREVIEW_LEVEL: 修補",
            review_level="修補",
            review_blocking=True,
            start_from="",
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
            analyze_plan_node(state)

        mock_ask.assert_not_called()
        assert captured_prompt["prompt"].count("既有 `- [x]` 維持原文") == 1
