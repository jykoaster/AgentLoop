"""
工作階段狀態紀錄測試（core/stages.py + core/workflow.py 的 _tracked 包裝）。

沿用 tests/test_workflow_entrypoints.py 的手法：build_workflow() 編出的 app ＋ mock node，
驗證 state["stages"] 隨 app.stream() 推進而變化，不需要真的呼叫 Claude CLI。
"""
from unittest.mock import patch

from AgentLoop.core import stages
from AgentLoop.core.workflow import build_workflow


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
        "stages": {},
        "stage_notes": {},
    }
    base.update(overrides)
    return base


def _run(app, state) -> dict:
    """跑完 app.stream()，回傳逐步合併後的最終 state。"""
    final = dict(state)
    for step in app.stream(state):
        for _node_name, update in step.items():
            if isinstance(update, dict):
                final.update(update)
    return final


class TestStageProgressesFromPendingToRunningToDone:
    def test_stages_move_from_pending_to_running_to_done(self):
        """工作流推進時各階段狀態依序由尚未開始轉為執行中再轉為完成"""
        observed_at_analyze: dict = {}
        observed_at_confirm: dict = {}

        def mock_analyze(state):
            observed_at_analyze.update(state["stages"])
            return {"analysis": "plan", "plan": ["- [ ] t1"]}

        def mock_confirm(state):
            observed_at_confirm.update(state["stages"])
            return {"status": "aborted"}

        with patch("AgentLoop.core.workflow.analyze_plan_node", mock_analyze), \
             patch("AgentLoop.core.workflow.human_confirm_node", mock_confirm), \
             patch("AgentLoop.core.workflow.execute_node", lambda s: {}), \
             patch("AgentLoop.core.workflow.review_node", lambda s: {}), \
             patch("AgentLoop.core.workflow.archive_node", lambda s: {}):
            app = build_workflow()
            final = _run(app, _base_state())

        # analyze_plan 開始執行時狀態為執行中
        assert observed_at_analyze["analyze_plan"] == "running"
        # analyze_plan 結束後為完成；human_confirm 開始時狀態為執行中
        assert observed_at_confirm["analyze_plan"] == "done"
        assert observed_at_confirm["human_confirm"] == "running"
        # execute、review、archive 仍為尚未開始
        assert observed_at_confirm["execute"] == "pending"
        assert observed_at_confirm["review"] == "pending"
        assert observed_at_confirm["archive"] == "pending"
        # 這些狀態都已寫入最終 state（重新整理網頁後看到相同結果＝狀態持續留在回傳的 state）
        assert final["stages"]["analyze_plan"] == "done"
        assert final["stages"]["human_confirm"] == "done"  # aborted 不是 error，只有 status=="error" 才記為錯誤


class TestStageMarkedErrorKeepsLaterStagesPending:
    def test_error_marks_that_stage_and_leaves_later_stages_pending(self):
        """階段結束且結果為錯誤時該階段記為錯誤且後續階段維持尚未開始"""
        def mock_review(state):
            if state.get("status") == "error":
                return {"status": "error"}
            return {"review_result": "Ready to merge? Yes", "review_blocking": False}

        with patch("AgentLoop.core.workflow.execute_node",
                   lambda s: {"status": "error", "execution_result": "boom"}), \
             patch("AgentLoop.core.workflow.review_node", mock_review), \
             patch("AgentLoop.core.workflow.archive_node", lambda s: {}), \
             patch("AgentLoop.core.workflow.analyze_plan_node", lambda s: {}), \
             patch("AgentLoop.core.workflow.human_confirm_node", lambda s: {}):
            app = build_workflow()
            state = _base_state(
                stages={"analyze_plan": "done", "human_confirm": "done"},
                start_from="execute",
            )
            final = _run(app, state)

        assert final["stages"]["execute"] == "error"
        assert final["stages"]["review"] == "pending"
        assert final["stages"]["archive"] == "pending"


class TestReplanResetsLaterStagesToPending:
    def test_review_replan_resets_later_stages_to_pending(self):
        """review 退回重新規劃時 analyze_plan 之後的階段重設為尚未開始"""
        call_count = {"review": 0}
        observed_on_replan: dict = {}

        def mock_review(state):
            call_count["review"] += 1
            if call_count["review"] == 1:
                return {"review_result": "Ready to merge? No", "review_level": "修補", "review_blocking": True}
            return {"review_result": "Ready to merge? Yes", "review_blocking": False}

        def mock_analyze(state):
            if not observed_on_replan:
                observed_on_replan.update(state["stages"])
            return {"analysis": "re-planned"}

        def mock_confirm(state):
            return {"status": "confirmed"}

        with patch("AgentLoop.core.workflow.review_node", mock_review), \
             patch("AgentLoop.core.workflow.analyze_plan_node", mock_analyze), \
             patch("AgentLoop.core.workflow.human_confirm_node", mock_confirm), \
             patch("AgentLoop.core.workflow.execute_node", lambda s: {"execution_result": "done"}), \
             patch("AgentLoop.core.workflow.archive_node", lambda s: {}):
            app = build_workflow()
            state = _base_state(
                stages={
                    "analyze_plan": "done", "human_confirm": "done",
                    "execute": "done", "review": "done", "archive": "pending",
                },
                start_from="review",
            )
            _run(app, state)

        assert observed_on_replan["analyze_plan"] == "running"
        assert observed_on_replan["human_confirm"] == "pending"
        assert observed_on_replan["execute"] == "pending"
        assert observed_on_replan["review"] == "pending"
        assert observed_on_replan["archive"] == "pending"


class TestFinishWithNoteWritesStageNotes:
    def test_finish_with_note_returns_stage_notes(self):
        """finish() 帶 note 時回傳 stages[stage] 與 stage_notes[stage]、不帶 note 時回傳只有 stages"""
        state = {"stages": {"execute": "running"}, "stage_notes": {}}

        with_note = stages.finish(state, "execute", "error", note="使用者中止")
        assert with_note["stages"]["execute"] == "error"
        assert with_note["stage_notes"]["execute"] == "使用者中止"

        without_note = stages.finish(state, "execute", "error")
        assert without_note["stages"]["execute"] == "error"
        assert "stage_notes" not in without_note
