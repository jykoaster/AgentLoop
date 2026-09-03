"""呼叫本機 `claude -p` CLI，不需要 Anthropic API 額度。"""
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

TOOL_PRESETS = {
    "readonly": "Read,Glob,Grep",
    # analyze_plan 的初始規劃：只新增規格文件（不含 Edit），checkout／openspec CLI／validate
    # 都已由 Python 端處理，不需要 Bash
    "plan":     "Read,Write,Glob,Grep",
    # analyze_plan 的 replan／依人工意見調整：要 Edit 既有的規格文件；同樣不需要 Bash
    "revise":   "Read,Write,Edit,Glob,Grep",
    "full":     "Read,Write,Edit,Bash,Glob,Grep",
    "check":    "Read,Glob,Grep,Bash",
    # code-review skill 需要 Task 工具以平行呼叫 Standards / Spec 兩個 sub-agent
    "review":   "Read,Glob,Grep,Bash,Task",
}

MODEL_IDS = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-7",
    "fable":  "claude-fable-5",
}


@dataclass
class ClaudeResult:
    text: str = ""
    is_error: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_cost_usd: float = 0.0
    session_id: str = ""


_DIM     = "\033[90m"
_YELLOW  = "\033[1;33m"
_MAGENTA = "\033[1;35m"
_RESET   = "\033[0m"

QUESTION_MARKER = "QUESTION:"
_QUESTION_LINE_RE = re.compile(r"(?:^|\n)\s*" + re.escape(QUESTION_MARKER))

_RESUME_AFTER_LIMIT_PROMPT = (
    "系統偵測到上一輪呼叫因 token / rate limit 中斷，現在恢復執行。"
    "在繼續之前，請先重新確認目前的檔案內容與 tasks.md 的勾選狀態"
    "（中斷前可能已經寫入部分變更或打勾），不要重做已完成的部分，"
    "也不要假設中斷前的最後一個動作一定完整或正確，"
    "確認後再從實際進度繼續完成剩餘工作。"
)

_TOKEN_LIMIT_KEYWORDS = [
    "rate limit",
    "usage limit",
    "quota exceeded",
    "too many requests",
    "429",
    "overloaded",
    "insufficient_quota",
    "has exceeded",
    "credit balance",
    "billing",
]


def _is_token_limit_error(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _TOKEN_LIMIT_KEYWORDS)


def _log_event(event: dict) -> None:
    """即時印出串流事件，僅 print 到 terminal，不存入任何變數。"""
    etype = event.get("type")

    if etype == "assistant":
        for block in event.get("message", {}).get("content", []):
            btype = block.get("type")
            if btype == "text":
                text = block.get("text", "").strip()
                match = _QUESTION_LINE_RE.search(text)
                if match:
                    question = text[match.end():].strip()
                    print(f"\n{_MAGENTA}{'┄'*50}", flush=True)
                    print(f"  ❓ Agent 提問，等待回覆", flush=True)
                    print(f"{'┄'*50}{_RESET}", flush=True)
                    print(f"  {question}\n", flush=True)
                elif text:
                    first = text.splitlines()
                    if first:
                        print(f"{_DIM}  {first[0][:120]}{_RESET}", flush=True)
            elif btype == "tool_use":
                name = block.get("name", "?")
                inp  = block.get("input", {})
                if name in ("Read", "Write", "Edit"):
                    detail = inp.get("file_path", inp.get("path", ""))
                elif name == "Bash":
                    detail = inp.get("command", "")[:120]
                elif name == "Grep":
                    pat  = inp.get("pattern", "")
                    path = inp.get("path", "")
                    detail = f"{pat!r} in {path}" if path else repr(pat)
                elif name == "Glob":
                    detail = inp.get("pattern", "")
                else:
                    detail = str(inp)[:120]
                print(f"{_DIM}  ▶ [{name}] {detail}{_RESET}", flush=True)

    elif etype == "tool_result":
        content = event.get("content", "")
        if isinstance(content, list):
            # 取第一個 text block
            content = next(
                (b.get("text", "") for b in content if b.get("type") == "text"),
                "",
            )
        if isinstance(content, str):
            first = content.strip().splitlines()
            if first:
                print(f"{_DIM}    → {first[0][:100]}{_RESET}", flush=True)


def format_usage_stats(result: ClaudeResult, elapsed: float) -> str:
    """格式化階段統計：耗時、token 用量。"""
    lines: list[str] = [f"  耗時：{elapsed:.1f}s"]

    total = result.input_tokens + result.output_tokens
    if total > 0:
        lines.append(
            f"  Tokens：輸入 {result.input_tokens:,} ／ 輸出 {result.output_tokens:,}"
        )
        if result.cache_read_tokens or result.cache_write_tokens:
            lines.append(
                f"  Cache：讀 {result.cache_read_tokens:,} ／ 寫 {result.cache_write_tokens:,}"
            )
        if result.total_cost_usd > 0:
            lines.append(f"  費用：${result.total_cost_usd:.6f}")

    return "\n".join(lines)


def _run_claude_once(
    timeout: int,
    cmd: list[str],
) -> ClaudeResult:
    """單次執行 claude subprocess，不含重試邏輯。"""
    lines: list[str] = []
    stderr_out = ""
    session_id = ""
    with subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=REPO_ROOT,
    ) as process:
        try:
            for line in process.stdout:
                lines.append(line)
                stripped = line.strip()
                if stripped:
                    try:
                        event = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    session_id = event.get("session_id") or session_id
                    _log_event(event)
            process.wait(timeout=timeout)
            # 在 with 結束前讀取 stderr，避免 pipe 關閉後 I/O error
            stderr_out = process.stderr.read().strip()
        except subprocess.TimeoutExpired:
            process.kill()
            return ClaudeResult(text="[錯誤] claude 執行逾時", is_error=True)

    if process.returncode != 0:
        # 也嘗試從 stdout stream-json 取出 error event
        stdout_tail = ""
        for line in reversed(lines[-10:]):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if event.get("type") in ("error", "result"):
                    stdout_tail = event.get("error") or event.get("result") or ""
                    break
            except json.JSONDecodeError:
                continue
        detail = ""
        if stdout_tail:
            detail += f"\n  stdout: {stdout_tail}"
        if stderr_out:
            detail += f"\n  stderr: {stderr_out}"
        return ClaudeResult(
            text=f"[claude 執行失敗 exit={process.returncode}]{detail}",
            is_error=True,
            session_id=session_id,
        )

    # 從 stream-json 的最後一個 result event 取出文字與 token 用量
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "result":
                usage = event.get("usage") or {}
                return ClaudeResult(
                    text=event.get("result", ""),
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                    cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
                    total_cost_usd=event.get("total_cost_usd", 0.0),
                    session_id=event.get("session_id") or session_id,
                )
        except json.JSONDecodeError:
            continue

    return ClaudeResult(text="".join(lines).strip(), session_id=session_id)


def call_claude(
    prompt: str,
    tools: str = "readonly",
    timeout: int = 300,
    model: str | None = None,
    resume: str | None = None,
) -> ClaudeResult:
    """以非互動模式執行 `claude -p`，回傳結果及 token 用量。
    偵測到 token / rate limit 錯誤時暫停，等人工確認 token 已更新後再重試。

    resume：帶入先前呼叫回傳的 session_id，以同一個 session 延續對話
    （用於一問一答式的多輪互動，例如 grilling 式提問）。
    """
    allowed = TOOL_PRESETS.get(tools, tools)

    if not shutil.which("claude"):
        raise RuntimeError(
            "找不到 `claude` 指令。請確認 Claude Code CLI 已安裝並在 PATH 中。"
        )

    def _build_cmd(p: str, resume_id: str | None) -> list[str]:
        c = [
            "claude", "-p", p,
            "--allowedTools", allowed,
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
        ]
        if model:
            c += ["--model", MODEL_IDS.get(model, model)]
        if resume_id:
            c += ["--resume", resume_id]
        return c

    cmd = _build_cmd(prompt, resume)

    while True:
        result = _run_claude_once(timeout, cmd)

        if result.is_error and _is_token_limit_error(result.text):
            print(f"\n{_YELLOW}{'═'*60}", flush=True)
            print(f"  ⚠  偵測到 Token / Rate Limit 錯誤，工作流程已暫停", flush=True)
            print(f"  錯誤訊息：{result.text[:300]}", flush=True)
            print(f"{'═'*60}", flush=True)
            print(f"  請等待 token 配額更新後，按 Enter 繼續；", flush=True)
            print(f"  或輸入 q 後按 Enter 中止程序。{_RESET}", flush=True)
            print(f"{_YELLOW}  > {_RESET}", end="", flush=True)
            try:
                user_input = sys.stdin.readline()
            except (KeyboardInterrupt, EOFError):
                print(f"\n{_YELLOW}  已中止{_RESET}\n", flush=True)
                return result
            if not user_input:  # stdin 已關閉（非 TTY / pipe EOF）
                print(f"\n{_YELLOW}  stdin 已關閉，中止{_RESET}\n", flush=True)
                return result
            if user_input.strip().lower() == "q":
                print(f"{_YELLOW}  已中止{_RESET}\n", flush=True)
                return result

            if result.session_id:
                print(
                    f"{_YELLOW}  接續中斷前的 session（{result.session_id}）繼續...{_RESET}\n",
                    flush=True,
                )
                cmd = _build_cmd(_RESUME_AFTER_LIMIT_PROMPT, result.session_id)
            else:
                print(
                    f"{_YELLOW}  中斷前未取得 session id，改為重新呼叫 Claude...{_RESET}\n",
                    flush=True,
                )
            continue

        return result
