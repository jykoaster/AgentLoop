"""互動埠：節點對使用者提問的唯一管道（見 docs/adr/0001-web-gui-interaction-port-and-subprocess-run.md）。

命令列模式完整重現既有行為：`ask()` 直接呼叫 `input()` / `sys.stdin.readline()`，
EOFError／KeyboardInterrupt 原樣往上拋，由呼叫端既有的 except 分支處理；呼叫端仍自行
`print()` 提示文字，`ask()` 的 `prompt` 參數在這個模式下不使用。`is_interactive()`
直接委派 `sys.stdin.isatty()`。既有測試對 `builtins.input` / `sys.stdin.isatty` 的
patch 之所以依然有效，靠的是 `tests/conftest.py` 的 autouse fixture 在每個測試開始前
清掉 `AGENTLOOP_INTERACTION`／`AGENTLOOP_RUN_DIR`；`lib/claude_runner.py` 啟動 `claude`
子行程時也不把這兩個變數傳給它，因此 agent 執行的指令（例如 execute／review 節點呼叫的
`pytest`）不會誤入網頁模式。

網頁模式（`AGENTLOOP_INTERACTION=web`）：`is_interactive()` 一律回傳 True；`ask()`
把提問寫成 `$AGENTLOOP_RUN_DIR/question.json`，每 0.5 秒輪詢同目錄的 `answer.json`，
讀到 id 相符的回覆後刪除兩檔並回傳答案文字。必填檢查與「提問已結束」判斷由寫入
`answer.json` 的那一端（`web/runner.py`）負責，這裡只管問與等。
"""
import json
import os
import sys
import time
import uuid
from typing import Literal

Kind = Literal["text", "choice", "confirm", "pause"]

_POLL_INTERVAL = 0.5


def _web_mode() -> bool:
    return os.environ.get("AGENTLOOP_INTERACTION") == "web"


def is_interactive() -> bool:
    if _web_mode():
        return True
    return sys.stdin.isatty()


def is_web_mode() -> bool:
    return _web_mode()


def _run_dir() -> str:
    run_dir = os.environ.get("AGENTLOOP_RUN_DIR", "")
    if not run_dir:
        raise RuntimeError("AGENTLOOP_INTERACTION=web 但缺少 AGENTLOOP_RUN_DIR")
    return run_dir


def _drain_stdin() -> None:
    try:
        import termios
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass


def _read_multiline_cli() -> str:
    """連續兩個空行或 EOF／Ctrl-C 結束；結尾清掉尾端空行、drain 剩餘 stdin buffer。"""
    lines: list[str] = []
    consecutive_empty = 0
    try:
        while True:
            line = input()
            if not line:
                if not lines:
                    break
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
                lines.append(line)
            else:
                consecutive_empty = 0
                lines.append(line)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        _drain_stdin()
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


def _ask_cli(kind: str, multiline: bool) -> str:
    if kind == "pause":
        return sys.stdin.readline()
    if multiline:
        return _read_multiline_cli()
    return input()


def _write_json_atomic(path: str, data: dict) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _ask_web(
    prompt: str,
    kind: str,
    stage: str,
    options: list[str] | None,
    required: bool,
    multiline: bool,
) -> str:
    run_dir = _run_dir()
    question_path = os.path.join(run_dir, "question.json")
    answer_path = os.path.join(run_dir, "answer.json")

    qid = uuid.uuid4().hex
    _write_json_atomic(question_path, {
        "id": qid,
        "stage": stage,
        "kind": kind,
        "prompt": prompt,
        "options": options or [],
        "required": required,
        "multiline": multiline,
        "created_at": time.time(),
    })

    while True:
        time.sleep(_POLL_INTERVAL)
        if not os.path.isfile(answer_path):
            continue
        try:
            with open(answer_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("id") != qid:
            continue
        for p in (question_path, answer_path):
            try:
                os.remove(p)
            except OSError:
                pass
        return data.get("answer", "")


def ask(
    prompt: str,
    *,
    kind: Kind = "text",
    stage: str = "",
    options: list[str] | None = None,
    required: bool = False,
    multiline: bool = False,
) -> str:
    if _web_mode():
        return _ask_web(prompt, kind, stage, options, required, multiline)
    return _ask_cli(kind, multiline)
