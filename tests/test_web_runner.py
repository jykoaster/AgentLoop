"""
web/runner.py 測試：以假子行程替身（寫 question.json、輸出 stage 標記、睡眠等待被中止）
取代真正的 `python -m AgentLoop.main`，驗證多執行並行、同一任務互斥、中止、提問回覆的機制。
"""
import json
import sys
import time
from pathlib import Path

import pytest

from AgentLoop.web import runner as runner_mod
from AgentLoop.web import settings as web_settings


FAKE_SLEEP_SCRIPT = """\
import json
import os
import time

run_dir = os.environ["AGENTLOOP_RUN_DIR"]
with open(os.path.join(run_dir, "session.json"), "w", encoding="utf-8") as f:
    json.dump({{"stage": "execute", "session_id": "abc123"}}, f)
print("@@AGENTLOOP_STAGE execute@@", flush=True)
time.sleep({sleep})
"""

FAKE_QUESTION_SCRIPT = """\
import json
import os
import time

run_dir = os.environ["AGENTLOOP_RUN_DIR"]
question_path = os.path.join(run_dir, "question.json")
answer_path = os.path.join(run_dir, "answer.json")

print("@@AGENTLOOP_STAGE analyze_plan@@", flush=True)
with open(question_path, "w", encoding="utf-8") as f:
    json.dump({{
        "id": "q1", "stage": "analyze_plan", "kind": "text",
        "prompt": "branch name?", "options": [], "required": True,
    }}, f)

# 模擬 lib/interaction.py 的 web 實作：讀到回覆後刪除兩個檔案（避免殘留的 question.json
# 讓測試誤以為同一題還能再回覆一次）。
deadline = time.monotonic() + {sleep}
while time.monotonic() < deadline and not os.path.exists(answer_path):
    time.sleep(0.02)
if os.path.exists(answer_path):
    os.remove(answer_path)
if os.path.exists(question_path):
    os.remove(question_path)

time.sleep({sleep})
"""

FAKE_CHANGE_JSON_SCRIPT = """\
import json
import os
import time

run_dir = os.environ["AGENTLOOP_RUN_DIR"]
with open(os.path.join(run_dir, "change.json"), "w", encoding="utf-8") as f:
    json.dump({{"change_name": "feat-login"}}, f)
print("@@AGENTLOOP_STAGE analyze_plan@@", flush=True)
time.sleep({sleep})
"""


def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for condition")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTLOOP_WEB_STATE_DIR", str(tmp_path / ".web"))
    monkeypatch.setenv("TARGET_PROJECT", "my-project")
    monkeypatch.setattr(runner_mod, "REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path


def _make_change(workspace: Path, name: str, stages: dict) -> Path:
    d = workspace / "my-project" / ".agentloop" / "changes" / name
    d.mkdir(parents=True)
    state = {
        "task": "x", "change_name": name, "project_dir": "my-project",
        "stages": stages, "stage_notes": {},
    }
    (d / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return d


def _write_script(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _run_dir(run_id: str) -> Path:
    return Path(web_settings.web_state_dir()) / "runs" / run_id


class TestAbortMarksStageErrorAndKeepsSession:
    def test_abort_marks_stage_error_and_keeps_session(self, workspace, monkeypatch):
        """使用者中止執行中的階段後該階段標為錯誤並保留 session 供重跑接回"""
        change_dir = _make_change(
            workspace, "feat-login",
            {"analyze_plan": "done", "human_confirm": "done", "execute": "running",
             "review": "pending", "archive": "pending"},
        )
        script = _write_script(workspace, "fake_main.py", FAKE_SLEEP_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        meta = mgr.start_rerun("feat-login", "execute")
        run_id = meta["run_id"]

        _wait_until(lambda: (_run_dir(run_id) / "session.json").exists())

        start = time.monotonic()
        mgr.abort(run_id)
        elapsed = time.monotonic() - start
        assert elapsed < 10

        updated = json.loads((change_dir / "state.json").read_text(encoding="utf-8"))
        assert updated["stages"]["execute"] == "error"
        assert updated["stage_notes"]["execute"] == "使用者中止"
        assert updated["session_node"] == "execute"
        assert updated["session_id"] == "abc123"
        assert updated["stages"]["analyze_plan"] == "done"
        assert updated["stages"]["human_confirm"] == "done"
        assert updated["stages"]["review"] == "pending"
        assert updated["stages"]["archive"] == "pending"

        assert mgr.runs() == []


class TestTempRowAbortEndsRunWithoutState:
    def test_temp_row_abort_ends_run_without_state(self, workspace, monkeypatch):
        """新增任務的暫時列在 analyze_plan 執行中可中止並結束執行"""
        script = _write_script(workspace, "fake_main.py", FAKE_SLEEP_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        meta = mgr.start_new_task("新增登入頁")
        run_id = meta["run_id"]

        _wait_until(lambda: (_run_dir(run_id) / "session.json").exists())

        start = time.monotonic()
        mgr.abort(run_id)
        elapsed = time.monotonic() - start
        assert elapsed < 10

        assert mgr.runs() == []
        changes_root = workspace / "my-project" / ".agentloop" / "changes"
        assert not list(changes_root.glob("*/state.json"))


class TestTwoNewTasksRunConcurrently:
    def test_two_new_tasks_can_start_together(self, workspace, monkeypatch):
        """Scenario: 兩個新任務先後啟動，兩個執行同時存在、各有執行目錄"""
        script = _write_script(workspace, "fake_main.py", FAKE_SLEEP_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        meta1 = mgr.start_new_task("任務一")
        meta2 = mgr.start_new_task("任務二")

        assert meta1["run_id"] != meta2["run_id"]
        assert len(mgr.runs()) == 2
        assert _run_dir(meta1["run_id"]).is_dir()
        assert _run_dir(meta2["run_id"]).is_dir()

        mgr.abort(meta1["run_id"])
        mgr.abort(meta2["run_id"])
        assert mgr.runs() == []


class TestRerunConflictIsPerTask:
    def test_same_task_rerun_conflicts_other_task_succeeds(self, workspace, monkeypatch):
        """Scenario: feat-login 執行中再重跑 feat-login 拒絕；重跑 fix-css 啟動成功"""
        _make_change(
            workspace, "feat-login",
            {"analyze_plan": "done", "human_confirm": "done", "execute": "error",
             "review": "pending", "archive": "pending"},
        )
        _make_change(
            workspace, "fix-css",
            {"analyze_plan": "done", "human_confirm": "done", "execute": "error",
             "review": "pending", "archive": "pending"},
        )
        script = _write_script(workspace, "fake_main.py", FAKE_SLEEP_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        meta1 = mgr.start_rerun("feat-login", "execute")
        _wait_until(lambda: (_run_dir(meta1["run_id"]) / "session.json").exists())

        with pytest.raises(runner_mod.RunConflict) as exc_info:
            mgr.start_rerun("feat-login", "execute")
        assert exc_info.value.label == "feat-login"

        meta2 = mgr.start_rerun("fix-css", "execute")
        assert len(mgr.runs()) == 2

        mgr.abort(meta1["run_id"])
        mgr.abort(meta2["run_id"])


class TestAnswerAndAbortAreScopedToRun:
    def test_answer_and_abort_affect_only_that_run(self, workspace, monkeypatch):
        """Scenario: 回覆／中止指定執行只影響該 run，另一個 run 的 question.json 與行程不受影響"""
        script = _write_script(workspace, "fake_main.py", FAKE_QUESTION_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        meta1 = mgr.start_new_task("任務一")
        meta2 = mgr.start_new_task("任務二")

        run_dir1 = _run_dir(meta1["run_id"])
        run_dir2 = _run_dir(meta2["run_id"])
        _wait_until(lambda: (run_dir1 / "question.json").exists())
        _wait_until(lambda: (run_dir2 / "question.json").exists())

        mgr.answer(meta1["run_id"], "q1", "feat/login")
        _wait_until(lambda: not (run_dir1 / "question.json").exists())

        assert (run_dir2 / "question.json").exists()
        assert len(mgr.runs()) == 2

        mgr.abort(meta1["run_id"])
        remaining = mgr.runs()
        assert len(remaining) == 1
        assert remaining[0]["run_id"] == meta2["run_id"]

        mgr.abort(meta2["run_id"])
        assert mgr.runs() == []


class TestChangeNameFromChangeJson:
    def test_reads_change_name_from_change_json(self, workspace, monkeypatch):
        """Scenario: 子行程決定 change 名稱後寫入 change.json，`runs()` 讀此檔取得"""
        script = _write_script(workspace, "fake_main.py", FAKE_CHANGE_JSON_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        meta = mgr.start_new_task("新增登入頁")
        run_id = meta["run_id"]

        _wait_until(lambda: any(r["change_name"] == "feat-login" for r in mgr.runs()))

        runs = mgr.runs()
        assert len(runs) == 1
        assert runs[0]["run_id"] == run_id
        assert runs[0]["change_name"] == "feat-login"

        mgr.abort(run_id)


class TestAnsweredQuestionRejectsSecondAnswer:
    def test_answer_after_question_closed_reports_ended(self, workspace, monkeypatch):
        """提問已被回覆後再送出回覆時顯示提問已結束"""
        script = _write_script(workspace, "fake_main.py", FAKE_QUESTION_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        meta = mgr.start_new_task("新增登入頁")
        run_id = meta["run_id"]

        _wait_until(lambda: (_run_dir(run_id) / "question.json").exists())

        mgr.answer(run_id, "q1", "feat/login")
        _wait_until(lambda: not (_run_dir(run_id) / "question.json").exists())

        with pytest.raises(runner_mod.QuestionGone):
            mgr.answer(run_id, "q1", "feat/login-again")

        mgr.abort(run_id)


class TestRequiredBlankAnswerRejected:
    def test_blank_required_answer_is_rejected(self, workspace, monkeypatch):
        """必填文字題送出空白時不送出並提示必填"""
        script = _write_script(workspace, "fake_main.py", FAKE_QUESTION_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        meta = mgr.start_new_task("新增登入頁")
        run_id = meta["run_id"]

        _wait_until(lambda: (_run_dir(run_id) / "question.json").exists())

        with pytest.raises(runner_mod.RequiredAnswerMissing):
            mgr.answer(run_id, "q1", "   ")

        assert not (_run_dir(run_id) / "answer.json").exists()
        mgr.abort(run_id)
