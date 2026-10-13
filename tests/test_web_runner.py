"""
web/runner.py 測試：以假子行程替身（寫 question.json、輸出 stage 標記、睡眠等待被中止）
取代真正的 `python -m AgentLoop.main`，驗證單一作用中執行、中止、提問回覆的機制本身。
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
        mgr.start_rerun("feat-login", "execute")

        run_dir = Path(web_settings.web_state_dir()) / "run"
        _wait_until(lambda: (run_dir / "session.json").exists())

        start = time.monotonic()
        mgr.abort()
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

        assert mgr.status()["active"] is False


class TestTempRowAbortEndsRunWithoutState:
    def test_temp_row_abort_ends_run_without_state(self, workspace, monkeypatch):
        """新增任務的暫時列在 analyze_plan 執行中可中止並結束執行"""
        script = _write_script(workspace, "fake_main.py", FAKE_SLEEP_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        mgr.start_new_task("新增登入頁")

        run_dir = Path(web_settings.web_state_dir()) / "run"
        _wait_until(lambda: (run_dir / "session.json").exists())

        start = time.monotonic()
        mgr.abort()
        elapsed = time.monotonic() - start
        assert elapsed < 10

        assert mgr.status()["active"] is False
        changes_root = workspace / "my-project" / ".agentloop" / "changes"
        assert not list(changes_root.glob("*/state.json"))


class TestRejectsStartWhileRunning:
    def test_second_start_is_rejected_while_run_active(self, workspace, monkeypatch):
        """執行進行中再送出啟動要求時系統拒絕"""
        script = _write_script(workspace, "fake_main.py", FAKE_SLEEP_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        mgr.start_new_task("修正樣式 feat-login")

        run_dir = Path(web_settings.web_state_dir()) / "run"
        _wait_until(lambda: (run_dir / "session.json").exists())

        with pytest.raises(runner_mod.RunConflict):
            mgr.start_new_task("another task")

        mgr.abort()


class TestAnsweredQuestionRejectsSecondAnswer:
    def test_answer_after_question_closed_reports_ended(self, workspace, monkeypatch):
        """提問已被回覆後再送出回覆時顯示提問已結束"""
        script = _write_script(workspace, "fake_main.py", FAKE_QUESTION_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        mgr.start_new_task("新增登入頁")

        run_dir = Path(web_settings.web_state_dir()) / "run"
        _wait_until(lambda: (run_dir / "question.json").exists())

        mgr.answer("q1", "feat/login")
        _wait_until(lambda: not (run_dir / "question.json").exists())

        with pytest.raises(runner_mod.QuestionGone):
            mgr.answer("q1", "feat/login-again")

        mgr.abort()


class TestRequiredBlankAnswerRejected:
    def test_blank_required_answer_is_rejected(self, workspace, monkeypatch):
        """必填文字題送出空白時不送出並提示必填"""
        script = _write_script(workspace, "fake_main.py", FAKE_QUESTION_SCRIPT.format(sleep=60))
        monkeypatch.setattr(runner_mod, "MAIN_CMD", [sys.executable, str(script)])

        mgr = runner_mod.RunManager()
        mgr.start_new_task("新增登入頁")

        run_dir = Path(web_settings.web_state_dir()) / "run"
        _wait_until(lambda: (run_dir / "question.json").exists())

        with pytest.raises(runner_mod.RequiredAnswerMissing):
            mgr.answer("q1", "   ")

        assert not (run_dir / "answer.json").exists()
        mgr.abort()
