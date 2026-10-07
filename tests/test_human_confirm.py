"""
human_confirm_node 輸入處理測試。

重點：空字串（誤觸 Enter）必須重新提示，不得進入拒絕流程，
避免 grilling 等待期間緩衝的 Enter 把後續真正的 'y' 誤讀為修改意見。
"""
import pytest
from unittest.mock import patch

import AgentLoop.core.workflow  # noqa: F401  # 先載入 core.workflow 避免 circular import


def _state(**overrides) -> dict:
    base = {
        "task": "test task",
        "analysis": "plan summary",
        "plan": ["- [ ] task 1"],
        "status": "pending",
        "change_name": "feat-test",
        "branch_name": "feat/test",
        "project_dir": "my-project",
    }
    base.update(overrides)
    return base


class TestHumanConfirmInputHandling:
    def test_y_confirms(self):
        """直接輸入 'y' → confirmed"""
        from AgentLoop.nodes.human_confirm import human_confirm_node

        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="y"):
            result = human_confirm_node(_state())

        assert result["status"] == "confirmed"

    def test_empty_enter_reprompts_then_y_confirms(self):
        """空字串（誤觸 Enter）→ 重新提示；後續 'y' → confirmed"""
        from AgentLoop.nodes.human_confirm import human_confirm_node

        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", side_effect=["", "y"]):
            result = human_confirm_node(_state())

        assert result["status"] == "confirmed"

    def test_multiple_empty_enters_then_y_confirms(self):
        """連續多個空字串 → 重新提示；最後 'y' → confirmed"""
        from AgentLoop.nodes.human_confirm import human_confirm_node

        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", side_effect=["", "", "", "y"]):
            result = human_confirm_node(_state())

        assert result["status"] == "confirmed"

    def test_empty_enter_then_n_with_feedback_gives_needs_revision(self):
        """空字串 → 重新提示；'n' + 修改意見 → needs_revision（不把意見誤讀為 'y'）"""
        from AgentLoop.nodes.human_confirm import human_confirm_node

        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", side_effect=["", "n", "請修改 X"]):
            result = human_confirm_node(_state())

        assert result["status"] == "needs_revision"
        assert result["human_feedback"] == "請修改 X"

    def test_n_with_empty_feedback_aborts(self):
        """'n' + 空白意見 → aborted"""
        from AgentLoop.nodes.human_confirm import human_confirm_node

        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", side_effect=["n", ""]):
            result = human_confirm_node(_state())

        assert result["status"] == "aborted"

    def test_non_interactive_aborts(self):
        """非互動式環境 → 自動 aborted"""
        from AgentLoop.nodes.human_confirm import human_confirm_node

        with patch("sys.stdin.isatty", return_value=False):
            result = human_confirm_node(_state())

        assert result["status"] == "aborted"

    def test_upstream_error_skips_prompt(self):
        """上游 status=error → 不顯示提示，直接回傳 error"""
        from AgentLoop.nodes.human_confirm import human_confirm_node

        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input") as mock_input:
            result = human_confirm_node(_state(status="error"))

        mock_input.assert_not_called()
        assert result["status"] == "error"
