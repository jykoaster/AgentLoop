"""
用量上限的偵測，以及「重置後接回同一個 session」在三個節點上的行為測試。

回歸重點：
1. 訂閱制（Pro / Max / Team 席位）印的上限訊息一個字都對不上 _TOKEN_LIMIT_KEYWORDS，
   曾導致 execute 直接以 error 收場（1.8 秒結束、review 跟著跳過），而不是暫停等重置。
2. session id 只活在程序記憶體裡，工作流一結束就接不回去；現在存進 state 的單一插槽。

不依賴 Claude CLI，可在容器內直接 pytest 執行。
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 強制正確的 import 順序：core.workflow 必須先於 nodes 子模組載入，
# 否則 workflow.py 試圖從尚未完成初始化的 nodes 套件取用 node functions 會造成 circular import。
import AgentLoop.core.workflow  # noqa: F401

from AgentLoop.core import take_session, store_session
from AgentLoop.lib import is_usage_limit_error, RESUME_AFTER_INTERRUPT_PROMPT

# 節點實際收到的文字：claude exit!=0 時由 _run_claude_once 包成這個形狀
_REAL_SESSION_LIMIT_TEXT = (
    "[claude 執行失敗 exit=1]\n"
    "  stdout: You've hit your session limit · resets 6:10am (UTC)"
)
_STALE_SESSION_TEXT = (
    "[claude 執行失敗 exit=1]\n  stdout: No conversation found with session ID"
)


def _claude_result(text: str = "完成", *, is_error: bool = False, session_id: str = "") -> MagicMock:
    r = MagicMock()
    r.is_error = is_error
    r.text = text
    r.session_id = session_id
    r.input_tokens = 0
    r.output_tokens = 0
    r.cache_read_tokens = 0
    r.cache_write_tokens = 0
    r.total_cost_usd = 0.0
    return r


def _state(**overrides) -> dict:
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
        "session_node": "",
        "session_id": "",
        "start_from": "",
    }
    base.update(overrides)
    return base


def _interrupted(node: str, session_id: str) -> dict:
    """state 覆寫：插槽裡留著 `node` 中斷時的 session。"""
    return {"session_node": node, "session_id": session_id}


def _make_change_dir(workspace: Path) -> Path:
    d = workspace / "my-project" / "openspec" / "changes" / "feat-test"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("- [x] 1.1 done\n- [ ] 1.2 todo")
    (d / "proposal.md").write_text("## Intent\n測試用提案")
    return d


# ── is_usage_limit_error ──────────────────────────────────────────────────────

class TestIsUsageLimitError:
    @pytest.mark.parametrize("text", [
        _REAL_SESSION_LIMIT_TEXT,
        "You've hit your session limit · resets 3:45pm",
        "You've hit your weekly limit · resets Mon 12:00am",
        "You've hit your Opus limit · resets 3:45pm",
        "You've hit your Sonnet limit · resets 3:45pm",  # 未來可能出現的 per-model 上限
    ])
    def test_matches_subscription_limit_messages(self, text):
        assert is_usage_limit_error(text)

    @pytest.mark.parametrize("text", [
        "API Error: 429 Too Many Requests",
        "Claude AI usage limit reached",
        "rate limit exceeded",
        "Your credit balance is too low",
        "quota exceeded",
    ])
    def test_still_matches_existing_keywords(self, text):
        assert is_usage_limit_error(text)

    @pytest.mark.parametrize("text", [
        "API Error: 500 Internal Server Error",
        "[錯誤] claude 執行逾時",
        "ENOENT: no such file or directory",
        "spend limit reached (daily; resets 2026-08-09 00:00 UTC)",  # gateway 支出上限，非方案額度
    ])
    def test_does_not_match_unrelated_errors(self, text):
        assert not is_usage_limit_error(text)

    def test_does_not_match_context_limit(self):
        """脈絡視窗滿了等重置也不會好（由 auto-compact 處理），不可停在等待人工按鍵。"""
        assert not is_usage_limit_error("You've hit your context limit for this conversation")


# ── session 插槽 ──────────────────────────────────────────────────────────────

class TestSessionSlot:
    def test_takes_own_session(self):
        assert take_session(_state(**_interrupted("execute", "sess-a")), "execute") == "sess-a"

    def test_ignores_other_nodes_session(self):
        """analyze_plan 中斷後直接 --node execute：execute 不可接到別人的 session。"""
        state = _state(**_interrupted("analyze_plan", "sess-a"))
        assert take_session(state, "execute") == ""

    def test_empty_slot(self):
        assert take_session(_state(), "execute") == ""

    def test_store_replaces_previous_owner(self):
        """單一插槽：換節點時舊的直接被取代，不會留下沒人清的殘留。"""
        assert store_session("review", "sess-b") == {"session_node": "review", "session_id": "sess-b"}

    def test_store_empty_clears_slot(self):
        assert store_session("review", "") == {"session_node": "", "session_id": ""}


# ── execute ───────────────────────────────────────────────────────────────────

class TestExecuteSessionResume:
    def _run(self, state, claude_side_effect, workspace):
        from AgentLoop.nodes import execute_node

        mock_call = MagicMock(side_effect=claude_side_effect)
        with patch("AgentLoop.nodes.execute.REPO_ROOT", str(workspace)), \
             patch("AgentLoop.nodes.execute.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.execute.build_skills_block", return_value="skill"), \
             patch("AgentLoop.nodes.execute.call_claude", mock_call):
            result = execute_node(state)
        return result, mock_call

    def test_persists_session_id_on_usage_limit(self, tmp_path):
        """撞到上限而中止 → session id 留在插槽，供重置後接回。"""
        _make_change_dir(tmp_path)
        limit = _claude_result(_REAL_SESSION_LIMIT_TEXT, is_error=True, session_id="sess-abc")

        result, _ = self._run(_state(), [limit], tmp_path)

        assert result["status"] == "error"
        assert result["session_node"] == "execute"
        assert result["session_id"] == "sess-abc"

    def test_falls_back_to_prior_session_when_error_has_none(self, tmp_path):
        """第二次也在拿到 session id 前就被擋下 → 保留原本存著的 id，不要清掉。"""
        _make_change_dir(tmp_path)
        limit = _claude_result(_REAL_SESSION_LIMIT_TEXT, is_error=True, session_id="")

        state = _state(**_interrupted("execute", "sess-old"))
        result, _ = self._run(state, [limit], tmp_path)

        assert result["session_id"] == "sess-old"

    def test_clears_session_id_on_success(self, tmp_path):
        """正常完成 → 清掉；下一輪的規格可能已被 replan 改過，不該接舊 session。"""
        _make_change_dir(tmp_path)
        state = _state(**_interrupted("execute", "sess-old"))

        result, _ = self._run(state, [_claude_result("實作完成")], tmp_path)

        assert result["status"] == "ok"
        assert result["session_node"] == ""
        assert result["session_id"] == ""

    def test_resumes_prior_session_with_continuation_prompt(self, tmp_path):
        """有存著的 session id → 用 --resume 接回，且只送續作指示而非完整 prompt。"""
        _make_change_dir(tmp_path)
        state = _state(**_interrupted("execute", "sess-old"))

        _, mock_call = self._run(state, [_claude_result("續作完成")], tmp_path)

        assert mock_call.call_count == 1
        args, kwargs = mock_call.call_args
        assert kwargs["resume"] == "sess-old"
        assert args[0] == RESUME_AFTER_INTERRUPT_PROMPT
        assert "執行前準備" not in args[0]  # 沒有重送完整 _SYSTEM

    def test_ignores_session_owned_by_another_node(self, tmp_path):
        """analyze_plan 中斷後直接 --node execute → 全新 session，不可接錯脈絡。"""
        _make_change_dir(tmp_path)
        state = _state(**_interrupted("analyze_plan", "sess-plan"))

        _, mock_call = self._run(state, [_claude_result("實作完成")], tmp_path)

        assert mock_call.call_args[1]["resume"] is None
        assert "執行前準備" in mock_call.call_args[0][0]

    def test_no_resume_when_no_prior_session(self, tmp_path):
        _make_change_dir(tmp_path)

        _, mock_call = self._run(_state(), [_claude_result("實作完成")], tmp_path)

        assert mock_call.call_count == 1
        args, kwargs = mock_call.call_args
        assert kwargs["resume"] is None
        assert "執行前準備" in args[0]

    def test_stale_session_falls_back_to_full_prompt(self, tmp_path):
        """session 已失效（非上限錯誤）→ 退回完整 prompt 重跑，而不是直接失敗。"""
        _make_change_dir(tmp_path)
        stale = _claude_result(_STALE_SESSION_TEXT, is_error=True)
        state = _state(**_interrupted("execute", "sess-gone"))

        result, mock_call = self._run(state, [stale, _claude_result("實作完成")], tmp_path)

        assert mock_call.call_count == 2
        assert result["status"] == "ok"
        assert "執行前準備" in mock_call.call_args_list[1][0][0]

    def test_usage_limit_on_resume_is_not_treated_as_stale(self, tmp_path):
        """接回後又撞上限 → 不可退回完整 prompt 重跑（會重做已完成的 TASK）。"""
        _make_change_dir(tmp_path)
        limit = _claude_result(_REAL_SESSION_LIMIT_TEXT, is_error=True, session_id="sess-old")
        state = _state(**_interrupted("execute", "sess-old"))

        result, mock_call = self._run(state, [limit], tmp_path)

        assert mock_call.call_count == 1
        assert result["session_id"] == "sess-old"


# ── analyze_plan ──────────────────────────────────────────────────────────────

class TestAnalyzePlanSessionResume:
    """走「重新規劃（修補）」路徑：不需要問分支／domain，也不會觸發 rollback。"""

    def _run(self, state, claude_side_effect, workspace):
        from AgentLoop.nodes import analyze_plan_node

        mock_call = MagicMock(side_effect=claude_side_effect)
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(workspace)), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.build_skills_block", return_value="skill"), \
             patch("AgentLoop.nodes.analyze_plan.build_project_doc_hint_for", return_value=""), \
             patch("AgentLoop.nodes.analyze_plan.validate_change",
                   return_value=MagicMock(ok=True, error_text="")), \
             patch("AgentLoop.nodes.analyze_plan.call_claude", mock_call):
            result = analyze_plan_node(state)
        return result, mock_call

    def _replan_state(self, **overrides) -> dict:
        return _state(
            review_result="Ready to merge? No", review_level="修補",
            review_blocking=True, analysis="舊提案", **overrides,
        )

    def test_persists_session_id_on_usage_limit(self, tmp_path):
        _make_change_dir(tmp_path)
        limit = _claude_result(_REAL_SESSION_LIMIT_TEXT, is_error=True, session_id="sess-plan")

        result, _ = self._run(self._replan_state(), [limit], tmp_path)

        assert result["status"] == "error"
        assert result["session_node"] == "analyze_plan"
        assert result["session_id"] == "sess-plan"

    def test_clears_session_id_on_success(self, tmp_path):
        _make_change_dir(tmp_path)
        state = self._replan_state(**_interrupted("analyze_plan", "sess-old"))

        result, _ = self._run(state, [_claude_result("規劃完成")], tmp_path)

        assert result["status"] == "pending"  # 規劃完成＝等待 human_confirm
        assert result["session_node"] == ""
        assert result["session_id"] == ""

    def test_resumes_prior_session_with_continuation_prompt(self, tmp_path):
        _make_change_dir(tmp_path)
        state = self._replan_state(**_interrupted("analyze_plan", "sess-old"))

        _, mock_call = self._run(state, [_claude_result("規劃完成")], tmp_path)

        assert mock_call.call_count == 1
        args, kwargs = mock_call.call_args
        assert kwargs["resume"] == "sess-old"
        assert args[0] == RESUME_AFTER_INTERRUPT_PROMPT

    def test_stale_session_falls_back_to_full_prompt(self, tmp_path):
        _make_change_dir(tmp_path)
        stale = _claude_result(_STALE_SESSION_TEXT, is_error=True)
        state = self._replan_state(**_interrupted("analyze_plan", "sess-gone"))

        result, mock_call = self._run(state, [stale, _claude_result("規劃完成")], tmp_path)

        assert mock_call.call_count == 2
        assert result["status"] == "pending"
        assert "重新分析與規劃" in mock_call.call_args_list[1][0][0]

    def test_guard_failure_keeps_prior_session(self, tmp_path):
        """guard 擋下時還沒產生新 session，不可把先前中斷留下的 id 清掉。"""
        _make_change_dir(tmp_path)
        # 初始規劃 guard：analysis 已存在且非 replan／human revise
        state = _state(analysis="已規劃", **_interrupted("analyze_plan", "sess-old"))

        result, mock_call = self._run(state, [], tmp_path)

        assert result["status"] == "error"
        assert mock_call.call_count == 0
        assert result["session_id"] == "sess-old"

    def test_persists_session_id_when_validate_loop_hits_limit(self, tmp_path):
        """validate 修正迴圈自己撞上限也要存得下 session，否則等於接不回去。"""
        from AgentLoop.nodes import analyze_plan_node

        _make_change_dir(tmp_path)
        limit = _claude_result(_REAL_SESSION_LIMIT_TEXT, is_error=True, session_id="sess-fix")
        mock_call = MagicMock(side_effect=[_claude_result("規劃完成", session_id="sess-plan"), limit])
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(tmp_path)), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.build_skills_block", return_value="skill"), \
             patch("AgentLoop.nodes.analyze_plan.build_project_doc_hint_for", return_value=""), \
             patch("AgentLoop.nodes.analyze_plan.validate_change",
                   return_value=MagicMock(ok=False, error_text="missing Scenario")), \
             patch("AgentLoop.nodes.analyze_plan.call_claude", mock_call):
            result = analyze_plan_node(self._replan_state())

        assert result["status"] == "error"
        assert result["session_node"] == "analyze_plan"
        assert result["session_id"] == "sess-fix"


# ── review ────────────────────────────────────────────────────────────────────

_WELL_FORMED_REVIEW = "## Standards\n無問題\n\n## Spec\n無問題\n\nReady to merge? Yes"


class TestReviewSessionResume:
    def _run(self, state, claude_side_effect, workspace):
        from AgentLoop.nodes import review_node

        mock_call = MagicMock(side_effect=claude_side_effect)
        with patch("AgentLoop.nodes.review.REPO_ROOT", str(workspace)), \
             patch("AgentLoop.nodes.review.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.review.build_skills_block", return_value="code-review skill"), \
             patch("AgentLoop.nodes.review.build_project_doc_hint_for", return_value=""), \
             patch("AgentLoop.nodes.review._run_spec_trace_check", return_value=("✅ 全數通過", [])), \
             patch("AgentLoop.nodes.review.call_claude", mock_call):
            result = review_node(state)
        return result, mock_call

    def test_persists_session_id_on_usage_limit(self, tmp_path):
        _make_change_dir(tmp_path)
        limit = _claude_result(_REAL_SESSION_LIMIT_TEXT, is_error=True, session_id="sess-rev")

        result, _ = self._run(_state(), [limit], tmp_path)

        assert result["status"] == "error"
        assert result["session_node"] == "review"
        assert result["session_id"] == "sess-rev"

    def test_clears_session_id_on_success(self, tmp_path):
        _make_change_dir(tmp_path)
        state = _state(**_interrupted("review", "sess-old"))

        result, _ = self._run(state, [_claude_result(_WELL_FORMED_REVIEW)], tmp_path)

        assert result["review_blocking"] is False
        assert result["session_node"] == ""
        assert result["session_id"] == ""

    def test_resumes_prior_session_with_continuation_prompt(self, tmp_path):
        _make_change_dir(tmp_path)
        state = _state(**_interrupted("review", "sess-old"))

        _, mock_call = self._run(state, [_claude_result(_WELL_FORMED_REVIEW)], tmp_path)

        assert mock_call.call_count == 1
        args, kwargs = mock_call.call_args
        assert kwargs["resume"] == "sess-old"
        assert args[0] == RESUME_AFTER_INTERRUPT_PROMPT

    def test_stale_session_falls_back_to_full_prompt(self, tmp_path):
        _make_change_dir(tmp_path)
        stale = _claude_result(_STALE_SESSION_TEXT, is_error=True)
        state = _state(**_interrupted("review", "sess-gone"))

        result, mock_call = self._run(
            state, [stale, _claude_result(_WELL_FORMED_REVIEW)], tmp_path
        )

        assert mock_call.call_count == 2
        assert result["review_blocking"] is False
        assert "資深程式碼審查者" in mock_call.call_args_list[1][0][0]

    def test_retry_budget_resets_after_falling_back(self, tmp_path):
        """接回失敗後退回完整 prompt 時，「報告不完整就補完」的重試額度要重新計算，
        不能沿用接回那一輪已經用掉的次數。"""
        _make_change_dir(tmp_path)
        stale = _claude_result(_STALE_SESSION_TEXT, is_error=True)
        state = _state(**_interrupted("review", "sess-gone"))

        result, mock_call = self._run(
            state,
            [stale, _claude_result("報告還沒寫完"), _claude_result(_WELL_FORMED_REVIEW)],
            tmp_path,
        )

        assert mock_call.call_count == 3
        assert result["review_blocking"] is False
