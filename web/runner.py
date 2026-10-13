"""執行管理：同一目標專案同時只允許一個執行，以獨立子行程（`python -m AgentLoop.main`）
執行工作流，提供啟動、回覆提問、中止、查詢狀態／日誌。

見 docs/adr/0001-web-gui-interaction-port-and-subprocess-run.md：子行程獨立 process
group 讓中止可靠（整組一起 kill），不在網頁服務執行緒內直接跑 LangGraph（Python 執行緒
無法被強制中止，claude 子行程與互動埠的阻塞等待會卡死服務）。
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from threading import Lock

from . import settings as web_settings
from ..core import stages
from ..core.session import store_session
from ..lib import REPO_ROOT

RERUNNABLE_STAGES = ("analyze_plan", "execute", "review", "archive")
ABORT_NOTE = "使用者中止"

MAIN_CMD: list[str] = [sys.executable, "-m", "AgentLoop.main"]

_STAGE_MARKER_RE = re.compile(r"@@AGENTLOOP_STAGE (\w+)@@")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

_SIGTERM_GRACE = 5
_SIGKILL_GRACE = 5


class RunConflict(Exception):
    def __init__(self, label: str):
        super().__init__(label)
        self.label = label


class QuestionGone(Exception):
    pass


class RequiredAnswerMissing(Exception):
    pass


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _split_log_by_stage(text: str) -> dict[str, str]:
    """依 `@@AGENTLOOP_STAGE x@@` 標記切分，回傳去 ANSI 後的各階段日誌。"""
    segments: dict[str, list[str]] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines(keepends=True):
        m = _STAGE_MARKER_RE.search(line)
        if m:
            if current:
                segments.setdefault(current, []).append("".join(buf))
            current = m.group(1)
            buf = []
            continue
        if current:
            buf.append(line)
    if current:
        segments.setdefault(current, []).append("".join(buf))
    return {k: _strip_ansi("".join(v)) for k, v in segments.items()}


def _build_argv(kind: str, task: str, change_name: str, stage: str) -> list[str]:
    if kind == "new_task":
        return [*MAIN_CMD, task]
    return [*MAIN_CMD, "--node", stage, "--change", change_name]


@dataclass
class _RunHandle:
    process: subprocess.Popen
    log_file: object
    meta: dict = field(default_factory=dict)


class RunManager:
    """單一作用中執行的狀態機。每個實例自成一個單例作用域——production 用模組層的
    `get_manager()` 共用一個，測試則各自建立新實例以互相隔離。"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._handle: _RunHandle | None = None

    # ── 路徑 ──────────────────────────────────────────────────────────────

    def _run_dir(self) -> str:
        return os.path.join(web_settings.web_state_dir(), "run")

    def _meta_path(self) -> str:
        return os.path.join(self._run_dir(), "meta.json")

    def _log_path(self) -> str:
        return os.path.join(self._run_dir(), "output.log")

    def _question_path(self) -> str:
        return os.path.join(self._run_dir(), "question.json")

    def _answer_path(self) -> str:
        return os.path.join(self._run_dir(), "answer.json")

    def _session_path(self) -> str:
        return os.path.join(self._run_dir(), "session.json")

    # ── 小檔案讀寫 ────────────────────────────────────────────────────────

    def _read_json(self, path: str) -> dict | None:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def _write_meta(self, meta: dict) -> None:
        path = self._meta_path()
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def _read_meta(self) -> dict:
        return self._read_json(self._meta_path()) or {}

    # ── 啟動 ──────────────────────────────────────────────────────────────

    def start_new_task(self, task: str) -> dict:
        with self._lock:
            self._poll_exit_locked()
            if self._handle is not None:
                raise RunConflict(self._label_locked())
            return self._spawn_locked(kind="new_task", task=task, change_name="", stage="")

    def start_rerun(self, change_name: str, stage: str) -> dict:
        if stage not in RERUNNABLE_STAGES:
            raise ValueError(f"不可重跑的階段：{stage}")
        with self._lock:
            self._poll_exit_locked()
            if self._handle is not None:
                raise RunConflict(self._label_locked())
            return self._spawn_locked(kind="rerun", task="", change_name=change_name, stage=stage)

    def _spawn_locked(self, *, kind: str, task: str, change_name: str, stage: str) -> dict:
        run_dir = self._run_dir()
        shutil.rmtree(run_dir, ignore_errors=True)
        os.makedirs(run_dir, exist_ok=True)

        env = dict(os.environ)
        env.update(web_settings.effective_env_overrides())
        env["AGENTLOOP_INTERACTION"] = "web"
        env["AGENTLOOP_RUN_DIR"] = run_dir
        env["PYTHONUNBUFFERED"] = "1"

        argv = _build_argv(kind, task, change_name, stage)
        log_file = open(self._log_path(), "wb")
        process = subprocess.Popen(
            argv,
            cwd=REPO_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        meta = {
            "run_id": uuid.uuid4().hex,
            "kind": kind,
            "task": task,
            "change_name": change_name,
            "stage": stage,
            "started_at": time.time(),
            "pid": process.pid,
        }
        self._write_meta(meta)
        self._handle = _RunHandle(process=process, log_file=log_file, meta=meta)
        return meta

    # ── 狀態查詢 ──────────────────────────────────────────────────────────

    def status(self) -> dict:
        with self._lock:
            self._poll_exit_locked()
            if self._handle is None:
                return {"active": False}
            meta = self._handle.meta
            self._maybe_detect_change_locked(meta)
            return {
                "active": True,
                "run_id": meta.get("run_id", ""),
                "label": self._label_locked(),
                "change_name": meta.get("change_name", ""),
                "task": meta.get("task", ""),
                "stage": self._current_stage_locked(meta),
                "question": self._read_json(self._question_path()),
            }

    def is_active(self) -> bool:
        return self.status().get("active", False)

    def _label_locked(self) -> str:
        meta = self._handle.meta if self._handle else {}
        return meta.get("change_name") or meta.get("task") or ""

    def _current_stage_locked(self, meta: dict) -> str:
        if meta.get("stage"):
            return meta["stage"]
        text = self._read_log_text()
        matches = _STAGE_MARKER_RE.findall(text)
        return matches[-1] if matches else ""

    def _read_log_text(self) -> str:
        try:
            with open(self._log_path(), encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    def live_stage_log(self, change_name: str, stage: str) -> str | None:
        """執行中時直接從 output.log 即時切分；不是目前這個執行就回傳 None，由呼叫端
        改讀持久化的 `<target>/.agentloop/changes/<name>/logs/<stage>.log`。"""
        with self._lock:
            self._poll_exit_locked()
            if self._handle is None:
                return None
            meta = self._handle.meta
            self._maybe_detect_change_locked(meta)
            if meta.get("change_name") != change_name:
                return None
            return _split_log_by_stage(self._read_log_text()).get(stage)

    # ── change name 偵測（新增任務時分支名稱決定前，change_name 還不知道）───────

    def _maybe_detect_change_locked(self, meta: dict) -> None:
        if meta.get("change_name"):
            return
        found = self._detect_change_name(meta)
        if found:
            meta["change_name"] = found
            self._write_meta(meta)

    def _detect_change_name(self, meta: dict) -> str:
        target = web_settings.effective_value("TARGET_PROJECT")
        if not target:
            return ""
        changes_root = os.path.join(REPO_ROOT, target, ".agentloop", "changes")
        if not os.path.isdir(changes_root):
            return ""
        started_at = meta.get("started_at", 0)
        task = meta.get("task", "")
        if not task:
            return ""
        for name in sorted(os.listdir(changes_root)):
            state_path = os.path.join(changes_root, name, "state.json")
            if not os.path.isfile(state_path):
                continue
            try:
                if os.path.getmtime(state_path) < started_at:
                    continue
            except OSError:
                continue
            data = self._read_json(state_path)
            if data and data.get("task") == task:
                return name
        return ""

    # ── 回覆 ──────────────────────────────────────────────────────────────

    def answer(self, question_id: str, answer_text: str) -> None:
        with self._lock:
            if self._handle is None:
                raise QuestionGone()
            question = self._read_json(self._question_path())
            if not question or question.get("id") != question_id:
                raise QuestionGone()
            if question.get("required") and not answer_text.strip():
                raise RequiredAnswerMissing()
            path = self._answer_path()
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"id": question_id, "answer": answer_text}, f, ensure_ascii=False)
            os.replace(tmp, path)

    # ── 中止 ──────────────────────────────────────────────────────────────

    def abort(self) -> None:
        with self._lock:
            if self._handle is None:
                return
            process = self._handle.process
            pid = process.pid
            self._send_signal(pid, signal.SIGTERM)
            if not self._wait_exit(process, _SIGTERM_GRACE):
                self._send_signal(pid, signal.SIGKILL)
                self._wait_exit(process, _SIGKILL_GRACE)

            self._mark_aborted_locked()
            self._finalize_locked()
            self._handle = None

    def _send_signal(self, pid: int, sig: int) -> None:
        try:
            os.killpg(os.getpgid(pid), sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _wait_exit(self, process: subprocess.Popen, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return True
            time.sleep(0.1)
        return process.poll() is not None

    def _mark_aborted_locked(self) -> None:
        meta = self._handle.meta
        self._maybe_detect_change_locked(meta)
        target = web_settings.effective_value("TARGET_PROJECT")
        change_name = meta.get("change_name")
        if not target or not change_name:
            return
        state_path = os.path.join(
            REPO_ROOT, target, ".agentloop", "changes", change_name, "state.json"
        )
        state = self._read_json(state_path)
        if state is None:
            return

        stage = self._abort_stage(state, meta)
        if not stage:
            return

        state.update(stages.finish(state, stage, "error", note=ABORT_NOTE))

        session = self._read_json(self._session_path())
        if session and session.get("stage") == stage and session.get("session_id"):
            state.update(store_session(stage, session["session_id"]))

        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _abort_stage(self, state: dict, meta: dict) -> str:
        for name, status in (state.get("stages") or {}).items():
            if status == "running":
                return name
        return self._current_stage_locked(meta)

    # ── 收尾：切分日誌、清空執行目錄 ──────────────────────────────────────

    def _poll_exit_locked(self) -> None:
        if self._handle is None:
            return
        if self._handle.process.poll() is not None:
            self._finalize_locked()
            self._handle = None

    def _finalize_locked(self) -> None:
        meta = self._handle.meta
        self._maybe_detect_change_locked(meta)
        target = web_settings.effective_value("TARGET_PROJECT")
        change_name = meta.get("change_name")
        if target and change_name:
            segments = _split_log_by_stage(self._read_log_text())
            logs_dir = os.path.join(
                REPO_ROOT, target, ".agentloop", "changes", change_name, "logs"
            )
            try:
                os.makedirs(logs_dir, exist_ok=True)
                for stage, text in segments.items():
                    with open(os.path.join(logs_dir, f"{stage}.log"), "w", encoding="utf-8") as f:
                        f.write(text)
            except OSError:
                pass
        try:
            self._handle.log_file.close()
        except Exception:
            pass
        shutil.rmtree(self._run_dir(), ignore_errors=True)


_manager = RunManager()


def get_manager() -> RunManager:
    return _manager
