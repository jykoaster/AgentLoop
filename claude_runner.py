"""呼叫本機 `claude -p` CLI，不需要 Anthropic API 額度。"""
import json
import os
import shutil
import subprocess
from dataclasses import dataclass

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

TOOL_PRESETS = {
    "readonly": "Read,Glob,Grep",
    "plan":     "Read,Write,Glob,Grep",
    "full":     "Read,Write,Edit,Bash,Glob,Grep",
    "check":    "Read,Glob,Grep,Bash",
}

MODEL_IDS = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-7",
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


_DIM   = "\033[90m"
_RESET = "\033[0m"


def _log_event(event: dict) -> None:
    """即時印出串流事件，僅 print 到 terminal，不存入任何變數。"""
    etype = event.get("type")

    if etype == "assistant":
        for block in event.get("message", {}).get("content", []):
            btype = block.get("type")
            if btype == "text":
                first = block.get("text", "").strip().splitlines()
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


def call_claude(
    prompt: str,
    tools: str = "readonly",
    timeout: int = 300,
    model: str | None = None,
) -> ClaudeResult:
    """以非互動模式執行 `claude -p`，回傳結果及 token 用量。"""
    allowed = TOOL_PRESETS.get(tools, tools)

    if not shutil.which("claude"):
        raise RuntimeError(
            "找不到 `claude` 指令。請確認 Claude Code CLI 已安裝並在 PATH 中。"
        )

    cmd = [
        "claude", "-p", prompt,
        "--allowedTools", allowed,
        "--output-format", "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
    ]
    if model:
        cmd += ["--model", MODEL_IDS.get(model, model)]

    lines: list[str] = []
    stderr_out = ""
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
                        _log_event(json.loads(stripped))
                    except json.JSONDecodeError:
                        pass
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
                )
        except json.JSONDecodeError:
            continue

    return ClaudeResult(text="".join(lines).strip())
