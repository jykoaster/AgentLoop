"""
Node precondition guard 測試。

每個 guard 觸發時應直接回傳 status="error"，不呼叫 Claude CLI。
Guard 不應阻擋合法的重新規劃或修補流程。
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# 強制正確的 import 順序：core.workflow 必須先於 nodes 子模組載入，
# 否則 workflow.py 試圖從尚未完成初始化的 nodes 套件取用 node functions 會造成 circular import。
import AgentLoop.core.workflow  # noqa: F401


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
        "skip_specs": False,
        "start_from": "",
    }
    base.update(overrides)
    return base


def _make_openspec_dir(workspace: Path, project: str = "my-project", change: str = "feat-test") -> Path:
    """建立 openspec change 目錄並回傳路徑。"""
    d = workspace / project / "openspec" / "changes" / change
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("- [ ] task 1")
    return d


# ── analyze_plan guards ───────────────────────────────────────────────────────

class TestAnalyzePlanGuards:
    def test_blocks_initial_plan_when_already_planned(self):
        """analysis 已存在且非重新規劃/修補 → 拒絕初始規劃"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(analysis="existing analysis")
        result = analyze_plan_node(state)

        assert result["status"] == "error"
        assert "初始規劃" in result["analysis"]

    def test_blocks_when_review_blocking_but_review_result_empty(self):
        """review_blocking=True 但 review_result 為空 → 拒絕重新規劃。
        analysis 故意留空，避免同時觸發 Guard 1（已規劃過的 guard）。"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            analysis="",          # Guard 1 不觸發（沒有既有分析）
            review_blocking=True,
            review_result="",
        )
        result = analyze_plan_node(state)

        assert result["status"] == "error"
        assert "review_result" in result["analysis"]

    def test_allows_replan_from_review_passes_guard(self):
        """review_result 非空 → 不觸發 guard（即使 analysis 已存在）"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            analysis="existing analysis",
            review_result="Ready to merge? No\nREVIEW_LEVEL: 修補",
            review_level="修補",
            review_blocking=True,
        )
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.rollback_except_openspec", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        assert "初始規劃" not in result.get("analysis", "")
        assert "review_result 為空" not in result.get("analysis", "")
        assert result["review_result"] == ""
        assert result["review_level"] == ""
        assert result["review_blocking"] is False

    def test_allows_human_revise_passes_guard_and_clears_review(self):
        """human_feedback 非空（且 review_result 空）→ 不觸發 guard；成功後 review 相關欄位應清空"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            analysis="existing analysis",
            human_feedback="請修改 X",
            review_result="",
            review_level="修補",
            review_blocking=True,
        )
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.rollback_except_openspec", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        assert "初始規劃" not in result.get("analysis", "")
        assert "review_result 為空" not in result.get("analysis", "")
        assert result["review_result"] == ""
        assert result["review_level"] == ""
        assert result["review_blocking"] is False

    def test_allows_fresh_initial_plan_when_no_analysis(self):
        """analysis 為空 → 初始規劃不被擋下"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(analysis="", review_result="", human_feedback="")
        ok_result = MagicMock()
        ok_result.ok = True
        ok_result.error_text = ""
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=ok_result), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=ok_result), \
             patch("AgentLoop.nodes.analyze_plan._ask_domain_selection", return_value=([], "")), \
             patch("AgentLoop.nodes.analyze_plan._ask_domain_purpose", return_value=""), \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        assert "初始規劃" not in result.get("analysis", "")

    def test_reuses_saved_domains_without_asking(self):
        """同一 change 已有 domains → 初始規劃不再問 domain 歸屬"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            analysis="",
            review_result="",
            human_feedback="",
            domains=["access-log"],
        )
        ok_result = MagicMock()
        ok_result.ok = True
        ok_result.error_text = ""
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=ok_result), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=ok_result), \
             patch("AgentLoop.nodes.analyze_plan._ask_domain_selection") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._ask_domain_purpose") as mock_purpose, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        mock_ask.assert_not_called()
        mock_purpose.assert_not_called()
        assert result.get("status") != "error"
        assert result["domains"] == ["access-log"]

    def test_reuses_saved_skip_specs_without_asking(self):
        """同一 change 已決定不寫 spec → 初始規劃不再問，也不問 domain"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            analysis="",
            review_result="",
            human_feedback="",
            domains=["access-log"],
            skip_specs=True,
        )
        ok_result = MagicMock()
        ok_result.ok = True
        ok_result.error_text = ""
        captured: dict = {}

        def _capture(prompt, **kwargs):
            captured["prompt"] = prompt
            return _mock_claude_result("規劃完成")

        with patch("AgentLoop.nodes.analyze_plan.call_claude", side_effect=_capture), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=ok_result), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=ok_result), \
             patch("AgentLoop.nodes.analyze_plan._ask_skip_specs") as mock_skip, \
             patch("AgentLoop.nodes.analyze_plan._ask_domain_selection") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._ask_domain_purpose") as mock_purpose, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")) , \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        mock_skip.assert_not_called()
        mock_ask.assert_not_called()
        mock_purpose.assert_not_called()
        assert result.get("status") != "error"
        assert result["skip_specs"] is True
        assert result["domains"] == []
        assert "skip_specs: true" in captured["prompt"]
        assert "不需要決定 domain" not in captured["prompt"]
        assert "不要詢問 domain" not in captured["prompt"]
        assert "沿用以下既有 domain" not in captured["prompt"]
        assert "目標專案與 Domain" not in captured["prompt"]
        assert "目標專案與 domain 已由系統確認" not in captured["prompt"]

    def test_asks_skip_specs_then_skips_domain_when_declined(self):
        """尚未決定時提問；使用者選擇不寫 spec 後不再問 domain"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(analysis="", review_result="", human_feedback="", skip_specs=None)
        ok_result = MagicMock()
        ok_result.ok = True
        ok_result.error_text = ""
        with patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=ok_result), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=ok_result), \
             patch("AgentLoop.nodes.analyze_plan._recover_skip_specs", return_value=None), \
             patch("AgentLoop.nodes.analyze_plan._ask_skip_specs", return_value=True) as mock_skip, \
             patch("AgentLoop.nodes.analyze_plan._ask_domain_selection") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._ask_domain_purpose") as mock_purpose, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        mock_skip.assert_called_once()
        mock_ask.assert_not_called()
        mock_purpose.assert_not_called()
        assert result["skip_specs"] is True

    def test_cancel_skip_specs_question_is_error(self):
        """使用者中止「是否寫 spec」→ 不呼叫 Claude"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(analysis="", review_result="", human_feedback="", skip_specs=None)
        ok_result = MagicMock()
        ok_result.ok = True
        ok_result.error_text = ""
        with patch("AgentLoop.nodes.analyze_plan.call_claude") as mock_claude, \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=ok_result), \
             patch("AgentLoop.nodes.analyze_plan._recover_skip_specs", return_value=None), \
             patch("AgentLoop.nodes.analyze_plan._ask_skip_specs", return_value=None):
            result = analyze_plan_node(state)

        mock_claude.assert_not_called()
        assert result["status"] == "error"
        assert result["skip_specs"] is None

    def test_replan_keeps_skip_specs_in_prompt(self):
        """重新規劃讀 state 裡的決定，注入 prompt，不再提問"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        state = _base_state(
            analysis="existing analysis",
            review_result="Ready to merge? No\nREVIEW_LEVEL: 修補",
            review_level="修補",
            review_blocking=True,
            skip_specs=True,
        )
        captured: dict = {}

        def _capture(prompt, **kwargs):
            captured["prompt"] = prompt
            return _mock_claude_result("規劃完成")

        with patch("AgentLoop.nodes.analyze_plan.call_claude", side_effect=_capture), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan._ask_skip_specs") as mock_skip, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        mock_skip.assert_not_called()
        assert result["skip_specs"] is True
        assert "skip_specs: true" in captured["prompt"]

    def test_initial_plan_reads_skip_specs_from_state_json(self, tmp_path):
        """新的一輪工作流沒帶這個欄位時，從同一個 change 的 state.json 還原、不再問"""
        from AgentLoop.nodes.analyze_plan import analyze_plan_node

        project = tmp_path / "my-project"
        state_dir = project / ".agentloop" / "changes" / "feat-test"
        state_dir.mkdir(parents=True)
        (state_dir / "state.json").write_text('{"skip_specs": true}', encoding="utf-8")

        state = _base_state(analysis="", review_result="", human_feedback="")
        state.pop("skip_specs")
        ok_result = MagicMock()
        ok_result.ok = True
        ok_result.error_text = ""
        with patch("AgentLoop.nodes.analyze_plan.REPO_ROOT", str(tmp_path)), \
             patch("AgentLoop.nodes.analyze_plan.call_claude", return_value=_mock_claude_result("規劃完成")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.analyze_plan.ensure_initialized", return_value=ok_result), \
             patch("AgentLoop.nodes.analyze_plan.ensure_change_created", return_value=ok_result), \
             patch("AgentLoop.nodes.analyze_plan._ask_skip_specs") as mock_skip, \
             patch("AgentLoop.nodes.analyze_plan._ask_domain_selection") as mock_ask, \
             patch("AgentLoop.nodes.analyze_plan._run_with_validate", return_value=("", "")), \
             patch("AgentLoop.nodes.analyze_plan._read_change_artifacts", return_value=("analysis", ["- [x] t1"])):
            result = analyze_plan_node(state)

        mock_skip.assert_not_called()
        mock_ask.assert_not_called()
        assert result["skip_specs"] is True


# ── execute_node guards ───────────────────────────────────────────────────────

class TestExecuteNodeGuards:
    def test_blocks_when_openspec_dir_missing(self, tmp_path):
        """openspec/changes/{change_name}/ 不存在 → error"""
        from AgentLoop.nodes import execute_node

        state = _base_state()
        with patch("AgentLoop.nodes.execute.REPO_ROOT", str(tmp_path)):
            result = execute_node(state)

        assert result["status"] == "error"
        assert "OpenSpec change 目錄" in result["execution_result"]

    def test_allows_when_openspec_dir_exists(self, tmp_path):
        """openspec/changes/{change_name}/ 存在 → guard 通過"""
        from AgentLoop.nodes import execute_node

        _make_openspec_dir(tmp_path)
        with patch("AgentLoop.nodes.execute.REPO_ROOT", str(tmp_path)), \
             patch("AgentLoop.nodes.execute.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.execute.call_claude", return_value=_mock_claude_result("實作完成")):
            result = execute_node(state=_base_state())

        assert "OpenSpec change 目錄" not in result.get("execution_result", "")


# ── review_node guards ────────────────────────────────────────────────────────

class TestReviewNodeGuards:
    def test_blocks_when_openspec_dir_missing(self, tmp_path):
        """openspec/changes/{change_name}/ 不存在 → error"""
        from AgentLoop.nodes import review_node

        state = _base_state()
        with patch("AgentLoop.nodes.review.REPO_ROOT", str(tmp_path)):
            result = review_node(state)

        assert result["status"] == "error"
        assert "OpenSpec change 目錄" in result["review_result"]

    def test_skips_when_upstream_error(self, tmp_path):
        """上游 status=error → 直接回傳 error，不做 openspec 檢查"""
        from AgentLoop.nodes import review_node

        state = _base_state(status="error")
        # 即使目錄不存在也不應嘗試檢查
        with patch("AgentLoop.nodes.review.REPO_ROOT", str(tmp_path)):
            result = review_node(state)

        assert result["status"] == "error"
        # 確認是上游 error 路徑，而非 openspec guard
        assert "OpenSpec change 目錄" not in result.get("review_result", "")

    def test_allows_when_openspec_dir_exists(self, tmp_path):
        """openspec/changes/{change_name}/ 存在 → guard 通過"""
        from AgentLoop.nodes import review_node

        _make_openspec_dir(tmp_path)
        review_text = "## Standards\nok\n## Spec\nok\nReady to merge? Yes"
        with patch("AgentLoop.nodes.review.REPO_ROOT", str(tmp_path)), \
             patch("AgentLoop.nodes.review.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.review.build_skills_block", return_value="skill"), \
             patch("AgentLoop.nodes.review.call_claude", return_value=_mock_claude_result(review_text)):
            result = review_node(state=_base_state())

        assert "OpenSpec change 目錄" not in result.get("review_result", "")
        assert result.get("review_blocking") is False
