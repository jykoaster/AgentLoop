"""執行管理：同一目標專案可多個任務並行，以獨立子行程（`python -m AgentLoop.main`）
執行工作流，提供啟動、回覆提問、中止、查詢狀態／日誌；同一任務同時最多一個執行。

見 docs/adr/0001-web-gui-interaction-port-and-subprocess-run.md：子行程獨立 process
group 讓中止可靠（整組一起 kill），不在網頁服務執行緒內直接跑 LangGraph（Python 執行緒
無法被強制中止，claude 子行程與互動埠的阻塞等待會卡死服務）。

見 docs/adr/0002-change-worktree-and-commit-on-archive.md：每個任務在自己專屬的任務
工作目錄執行，主工作目錄永遠不被切換分支，因此不同任務可無上限同時執行。
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
    """同一任務（`change_name`）已有執行進行中。"""
    def __init__(self, change_name: str):
        super().__init__(change_name)
        self.label = change_name


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
    run_dir: str
    process: subprocess.Popen
    log_file: object
    meta: dict = field(default_factory=dict)


class RunManager:
    """多執行狀態機：以 `run_id` 為鍵管理同時並行的多個子行程。production 用模組層的
    `get_manager()` 共用一個，測試則各自建立新實例以互相隔離。"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._handles: dict[str, _RunHandle] = {}

    # ── 路徑 ──────────────────────────────────────────────────────────────

    def _runs_root(self) -> str:
        return os.path.join(web_settings.web_state_dir(), "runs")

    def _run_dir(self, run_id: str) -> str:
        return os.path.join(self._runs_root(), run_id)

    def _meta_path(self, run_dir: str) -> str:
        return os.path.join(run_dir, "meta.json")

    def _log_path(self, run_dir: str) -> str:
        return os.path.join(run_dir, "output.log")

    def _question_path(self, run_dir: str) -> str:
        return os.path.join(run_dir, "question.json")

    def _answer_path(self, run_dir: str) -> str:
        return os.path.join(run_dir, "answer.json")

    def _session_path(self, run_dir: str) -> str:
        return os.path.join(run_dir, "session.json")

    def _change_json_path(self, run_dir: str) -> str:
        return os.path.join(run_dir, "change.json")

    # ── 小檔案讀寫 ────────────────────────────────────────────────────────

    def _read_json(self, path: str) -> dict | None:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def _write_meta(self, run_dir: str, meta: dict) -> None:
        path = self._meta_path(run_dir)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    # ── 啟動 ──────────────────────────────────────────────────────────────

    def start_new_task(self, task: str) -> dict:
        """新增任務永不因其他執行而拒絕——多個任務可無上限同時執行。"""
        with self._lock:
            self._poll_exit_locked()
            return self._spawn_locked(kind="new_task", task=task, change_name="", stage="")

    def start_rerun(self, change_name: str, stage: str) -> dict:
        """重跑某任務：該任務已有執行進行中才拒絕，其他任務的執行不受影響。"""
        if stage not in RERUNNABLE_STAGES:
            raise ValueError(f"不可重跑的階段：{stage}")
        with self._lock:
            self._poll_exit_locked()
            for handle in self._handles.values():
                self._maybe_detect_change_locked(handle)
                if handle.meta.get("change_name") == change_name:
                    raise RunConflict(change_name)
            return self._spawn_locked(kind="rerun", task="", change_name=change_name, stage=stage)

    def _spawn_locked(self, *, kind: str, task: str, change_name: str, stage: str) -> dict:
        run_id = uuid.uuid4().hex
        run_dir = self._run_dir(run_id)
        os.makedirs(run_dir, exist_ok=True)

        env = dict(os.environ)
        env.update(web_settings.effective_env_overrides())
        env["AGENTLOOP_INTERACTION"] = "web"
        env["AGENTLOOP_RUN_DIR"] = run_dir
        env["PYTHONUNBUFFERED"] = "1"

        argv = _build_argv(kind, task, change_name, stage)
        log_file = open(self._log_path(run_dir), "wb")
        process = subprocess.Popen(
            argv,
            cwd=REPO_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        meta = {
            "run_id": run_id,
            "kind": kind,
            "task": task,
            "change_name": change_name,
            "stage": stage,
            "started_at": time.time(),
            "pid": process.pid,
        }
        self._write_meta(run_dir, meta)
        self._handles[run_id] = _RunHandle(run_dir=run_dir, process=process, log_file=log_file, meta=meta)
        return meta

    # ── 狀態查詢 ──────────────────────────────────────────────────────────

    def runs(self) -> list[dict]:
        """回傳所有執行中的任務：`[{run_id, change_name, task, stage, question}]`。"""
        with self._lock:
            self._poll_exit_locked()
            out = []
            for handle in self._handles.values():
                self._maybe_detect_change_locked(handle)
                meta = handle.meta
                out.append({
                    "run_id": meta.get("run_id", ""),
                    "change_name": meta.get("change_name", ""),
                    "task": meta.get("task", ""),
                    "stage": self._current_stage_locked(handle),
                    "question": self._read_json(self._question_path(handle.run_dir)),
                })
            return out

    def is_active(self) -> bool:
        with self._lock:
            self._poll_exit_locked()
            return bool(self._handles)

    def _current_stage_locked(self, handle: _RunHandle) -> str:
        if handle.meta.get("stage"):
            return handle.meta["stage"]
        text = self._read_log_text(handle)
        matches = _STAGE_MARKER_RE.findall(text)
        return matches[-1] if matches else ""

    def _read_log_text(self, handle: _RunHandle) -> str:
        try:
            with open(self._log_path(handle.run_dir), encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    def live_stage_log(self, change_name: str, stage: str) -> str | None:
        """執行中時直接從該執行的 output.log 即時切分；沒有任何執行的 change_name 相符則
        回傳 None，由呼叫端改讀持久化的 `<target>/.agentloop/changes/<name>/logs/<stage>.log`。"""
        with self._lock:
            self._poll_exit_locked()
            for handle in self._handles.values():
                self._maybe_detect_change_locked(handle)
                if handle.meta.get("change_name") == change_name:
                    return _split_log_by_stage(self._read_log_text(handle)).get(stage)
            return None

    # ── change name 偵測（新增任務時分支名稱決定前，change_name 還不知道）───────

    def _maybe_detect_change_locked(self, handle: _RunHandle) -> None:
        if handle.meta.get("change_name"):
            return
        data = self._read_json(self._change_json_path(handle.run_dir))
        found = (data or {}).get("change_name", "")
        if found:
            handle.meta["change_name"] = found
            self._write_meta(handle.run_dir, handle.meta)

    # ── 回覆 ──────────────────────────────────────────────────────────────

    def answer(self, run_id: str, question_id: str, answer_text: str) -> None:
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is None:
                raise QuestionGone()
            question = self._read_json(self._question_path(handle.run_dir))
            if not question or question.get("id") != question_id:
                raise QuestionGone()
            if question.get("required") and not answer_text.strip():
                raise RequiredAnswerMissing()
            path = self._answer_path(handle.run_dir)
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"id": question_id, "answer": answer_text}, f, ensure_ascii=False)
            os.replace(tmp, path)

    # ── 中止 ──────────────────────────────────────────────────────────────

    def abort(self, run_id: str) -> None:
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is None:
                return
            process = handle.process
            pid = process.pid
            self._send_signal(pid, signal.SIGTERM)
            if not self._wait_exit(process, _SIGTERM_GRACE):
                self._send_signal(pid, signal.SIGKILL)
                self._wait_exit(process, _SIGKILL_GRACE)

            self._mark_aborted_locked(handle)
            self._finalize_locked(handle)
            self._handles.pop(run_id, None)

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

    def _mark_aborted_locked(self, handle: _RunHandle) -> None:
        self._maybe_detect_change_locked(handle)
        target = web_settings.effective_value("TARGET_PROJECT")
        change_name = handle.meta.get("change_name")
        if not target or not change_name:
            return
        state_path = os.path.join(
            REPO_ROOT, target, ".agentloop", "changes", change_name, "state.json"
        )
        state = self._read_json(state_path)
        if state is None:
            return

        stage = self._abort_stage(state, handle)
        if not stage:
            return

        state.update(stages.finish(state, stage, "error", note=ABORT_NOTE))

        session = self._read_json(self._session_path(handle.run_dir))
        if session and session.get("stage") == stage and session.get("session_id"):
            state.update(store_session(stage, session["session_id"]))

        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _abort_stage(self, state: dict, handle: _RunHandle) -> str:
        for name, status in (state.get("stages") or {}).items():
            if status == "running":
                return name
        return self._current_stage_locked(handle)

    # ── 收尾：切分日誌、清空執行目錄 ──────────────────────────────────────

    def _poll_exit_locked(self) -> None:
        for run_id, handle in list(self._handles.items()):
            if handle.process.poll() is not None:
                self._finalize_locked(handle)
                self._handles.pop(run_id, None)

    def _finalize_locked(self, handle: _RunHandle) -> None:
        self._maybe_detect_change_locked(handle)
        target = web_settings.effective_value("TARGET_PROJECT")
        change_name = handle.meta.get("change_name")
        if target and change_name:
            segments = _split_log_by_stage(self._read_log_text(handle))
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
            handle.log_file.close()
        except Exception:
            pass
        shutil.rmtree(handle.run_dir, ignore_errors=True)


_manager = RunManager()


def get_manager() -> RunManager:
    return _manager
