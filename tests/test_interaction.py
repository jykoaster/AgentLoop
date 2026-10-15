"""
互動埠（lib/interaction.py）測試：CLI 模式維持原本終端行為，web 模式以待回覆檔
（question.json／answer.json）在背景執行緒與主執行緒間一問一答。

函式名用英文。Scenario 標題的原文寫在該測試的 docstring 裡。
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import AgentLoop.core.workflow  # noqa: F401  防止 nodes 子模組先於 core.workflow 載入造成 circular import
from AgentLoop.lib import interaction
from AgentLoop.lib.project_context import REPO_ROOT


def _fast_poll(monkeypatch):
    monkeypatch.setattr(interaction, "_POLL_INTERVAL", 0.01)


def _wait_for_question(run_dir: Path, exclude_id: str | None = None, timeout: float = 2.0) -> dict:
    """等待 question.json 出現，且 id 跟 exclude_id 不同（避免讀到上一題尚未被背景
    執行緒清掉的舊檔——question.json 路徑固定，單靠「存在」無法分辨是不是新的一題）。"""
    path = run_dir / "question.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = None
            if data and data.get("id") != exclude_id:
                return data
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for a new question in {run_dir}")


def _write_answer(run_dir: Path, question: dict, answer: str) -> None:
    (run_dir / "answer.json").write_text(
        json.dumps({"id": question["id"], "answer": answer}), encoding="utf-8"
    )


class TestNumbered:
    def test_numbers_items_from_one(self):
        assert interaction.numbered(["auth", "billing", "以上皆非，建立新 domain"]) == [
            "1. auth", "2. billing", "3. 以上皆非，建立新 domain",
        ]

    def test_empty_list_returns_empty(self):
        assert interaction.numbered([]) == []


class TestCliWorkflowRepliesInTerminal:
    def test_cli_questions_stay_on_the_terminal(self, capsys):
        """以命令列執行工作流時提問仍在終端回覆"""
        from AgentLoop.nodes.analyze_plan import _ask_branch_name

        assert os.environ.get("AGENTLOOP_INTERACTION") != "web"

        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="feat/login"):
            result = _ask_branch_name()

        captured = capsys.readouterr()
        assert "請輸入本次任務要使用的 git 分支名稱" in captured.out
        assert result == "feat/login"


class TestWebHumanConfirm:
    def test_web_confirm_can_approve_or_request_changes(self, tmp_path, monkeypatch):
        """人工確認關卡可在網頁確認執行或送出修改意見"""
        from AgentLoop.nodes.human_confirm import human_confirm_node

        _fast_poll(monkeypatch)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        monkeypatch.setenv("AGENTLOOP_INTERACTION", "web")
        monkeypatch.setenv("AGENTLOOP_RUN_DIR", str(run_dir))

        state = {
            "task": "test", "analysis": "分析摘要", "plan": ["- [ ] task 1"],
            "status": "pending", "change_name": "feat-test",
            "branch_name": "feat/test", "project_dir": "my-project",
        }

        result_holder: dict = {}

        def _run():
            result_holder["result"] = human_confirm_node(state)

        thread = threading.Thread(target=_run)
        thread.start()

        question = _wait_for_question(run_dir)
        assert question["kind"] == "confirm"
        assert question["stage"] == "human_confirm"
        _write_answer(run_dir, question, "n")

        question2 = _wait_for_question(run_dir, exclude_id=question["id"])
        assert question2["kind"] == "text"
        _write_answer(run_dir, question2, "改用 Flask")

        thread.join(timeout=5)
        assert not thread.is_alive()
        assert result_holder["result"]["status"] == "needs_revision"
        assert result_holder["result"]["human_feedback"] == "改用 Flask"

    def test_yes_confirms_execution(self, tmp_path, monkeypatch):
        """人工確認按是直接確認執行"""
        from AgentLoop.nodes.human_confirm import human_confirm_node

        _fast_poll(monkeypatch)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        monkeypatch.setenv("AGENTLOOP_INTERACTION", "web")
        monkeypatch.setenv("AGENTLOOP_RUN_DIR", str(run_dir))

        state = {
            "task": "test", "analysis": "分析摘要", "plan": [],
            "status": "pending", "change_name": "feat-test",
            "branch_name": "feat/test", "project_dir": "my-project",
        }
        result_holder: dict = {}

        def _run():
            result_holder["result"] = human_confirm_node(state)

        thread = threading.Thread(target=_run)
        thread.start()
        question = _wait_for_question(run_dir)
        _write_answer(run_dir, question, "y")
        thread.join(timeout=5)

        assert result_holder["result"]["status"] == "confirmed"


class TestWebUsageLimitPause:
    def test_usage_limit_pause_can_continue_or_abort(self, tmp_path, monkeypatch):
        """用量上限暫停時可在網頁選擇繼續或中止"""
        from AgentLoop.lib import claude_runner

        _fast_poll(monkeypatch)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        monkeypatch.setenv("AGENTLOOP_INTERACTION", "web")
        monkeypatch.setenv("AGENTLOOP_RUN_DIR", str(run_dir))
        monkeypatch.setattr(claude_runner.shutil, "which", lambda _: "/usr/bin/claude")
        monkeypatch.setattr(
            "AgentLoop.core.stages.current_stage", lambda: "execute"
        )

        limit_result = claude_runner.ClaudeResult(
            text="You've hit your session limit · resets 3:45pm",
            is_error=True, session_id="sess-abc",
        )
        ok_result = claude_runner.ClaudeResult(text="完成", session_id="sess-abc")

        calls: list[list[str]] = []

        def _fake_run_once(timeout, cmd):
            calls.append(cmd)
            return limit_result if len(calls) == 1 else ok_result

        result_holder: dict = {}

        def _run():
            with patch.object(claude_runner, "_run_claude_once", side_effect=_fake_run_once):
                result_holder["result"] = claude_runner.call_claude("do work", tools="full")

        thread = threading.Thread(target=_run)
        thread.start()

        question = _wait_for_question(run_dir)
        assert question["kind"] == "pause"
        _write_answer(run_dir, question, "")

        thread.join(timeout=5)
        assert not thread.is_alive()
        assert result_holder["result"].text == "完成"
        assert len(calls) == 2
        assert "--resume" in calls[1]
        assert "sess-abc" in calls[1]
