"""review 修改建議改為多選題的測試（見 openspec/changes/feat-multiple-choose-reivew-advises）。"""
from unittest.mock import patch, MagicMock

import AgentLoop.core.workflow  # noqa: F401

from AgentLoop.tests.test_node_guards import _base_state, _make_openspec_dir, _mock_claude_result


_REVIEW_TEXT_WITH_SUGGESTIONS = (
    "## Standards\nok\n## Spec\nok\nReady to merge? Yes\n\n"
    "## 建議事項（不影響功能）\n"
    "SUGGESTION 1: 抽出重複的路徑組裝\n"
    "SUGGESTION 2: 補上型別註記\n"
    "SUGGESTION 3: 合併重複的測試\n"
)


class TestReviewSuggestionsMultiChoice:
    def test_勾選多條建議後按送出只針對勾選的建議重新規劃(self, tmp_path):
        from AgentLoop.nodes import review_node

        _make_openspec_dir(tmp_path)
        captured_ask_args: dict = {}

        def _fake_ask(prompt, **kwargs):
            captured_ask_args["prompt"] = prompt
            captured_ask_args.update(kwargs)
            return "1,3"

        with patch("AgentLoop.nodes.review.REPO_ROOT", str(tmp_path)), \
             patch("AgentLoop.nodes.review.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.review.build_skills_block", return_value="skill"), \
             patch("AgentLoop.nodes.review.call_claude", return_value=_mock_claude_result(_REVIEW_TEXT_WITH_SUGGESTIONS)), \
             patch("AgentLoop.nodes.review.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.review.interaction.is_web_mode", return_value=True), \
             patch("AgentLoop.nodes.review.interaction.ask", side_effect=_fake_ask):
            result = review_node(state=_base_state())

        assert captured_ask_args["prompt"] == "請勾選要修改的建議後按送出（未勾選＝不修改）"
        assert captured_ask_args["kind"] == "multi_choice"
        assert captured_ask_args["options"] == [
            "1. 抽出重複的路徑組裝",
            "2. 補上型別註記",
            "3. 合併重複的測試",
        ]
        assert result["review_blocking"] is True
        assert result["review_level"] == "修補"
        assert "SUGGESTION 1: 抽出重複的路徑組裝" in result["review_result"]
        assert "SUGGESTION 3: 合併重複的測試" in result["review_result"]
        assert "SUGGESTION 2: 補上型別註記" not in result["review_result"].split("人工確認：選定修改的建議事項")[1]

    def test_未勾選任何建議就送出時視為不修改並直接通過(self, tmp_path):
        from AgentLoop.nodes import review_node

        _make_openspec_dir(tmp_path)
        captured_ask_args: dict = {}

        def _fake_ask(prompt, **kwargs):
            captured_ask_args["prompt"] = prompt
            captured_ask_args.update(kwargs)
            return ""

        with patch("AgentLoop.nodes.review.REPO_ROOT", str(tmp_path)), \
             patch("AgentLoop.nodes.review.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.review.build_skills_block", return_value="skill"), \
             patch("AgentLoop.nodes.review.call_claude", return_value=_mock_claude_result(_REVIEW_TEXT_WITH_SUGGESTIONS)), \
             patch("AgentLoop.nodes.review.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.review.interaction.is_web_mode", return_value=True), \
             patch("AgentLoop.nodes.review.interaction.ask", side_effect=_fake_ask):
            result = review_node(state=_base_state())

        assert captured_ask_args["kind"] == "multi_choice"
        assert result["review_blocking"] is False

    def test_以命令列回覆修改建議時終端機提示編號輸入格式(self, tmp_path):
        from AgentLoop.nodes import review_node

        _REVIEW_TEXT_TWO_SUGGESTIONS = (
            "## Standards\nok\n## Spec\nok\nReady to merge? Yes\n\n"
            "## 建議事項（不影響功能）\n"
            "SUGGESTION 1: 補上型別註記\n"
            "SUGGESTION 2: 合併重複的測試\n"
        )
        _make_openspec_dir(tmp_path)
        captured_ask_args: dict = {}

        def _fake_ask(prompt, **kwargs):
            captured_ask_args["prompt"] = prompt
            captured_ask_args.update(kwargs)
            return "all"

        with patch("AgentLoop.nodes.review.REPO_ROOT", str(tmp_path)), \
             patch("AgentLoop.nodes.review.ensure_on_branch", return_value=(True, "ok")), \
             patch("AgentLoop.nodes.review.build_skills_block", return_value="skill"), \
             patch("AgentLoop.nodes.review.call_claude", return_value=_mock_claude_result(_REVIEW_TEXT_TWO_SUGGESTIONS)), \
             patch("AgentLoop.nodes.review.interaction.is_interactive", return_value=True), \
             patch("AgentLoop.nodes.review.interaction.is_web_mode", return_value=False), \
             patch("AgentLoop.nodes.review.interaction.ask", side_effect=_fake_ask):
            result = review_node(state=_base_state())

        assert captured_ask_args["prompt"] == "請輸入要修改的建議編號（例如 1,3；all=全部；留空＝不修改）"
        assert result["review_blocking"] is True
        assert result["review_level"] == "修補"
        selected_block = result["review_result"].split("人工確認：選定修改的建議事項")[1]
        assert selected_block.index("SUGGESTION 1: 補上型別註記") < selected_block.index("SUGGESTION 2: 合併重複的測試")
