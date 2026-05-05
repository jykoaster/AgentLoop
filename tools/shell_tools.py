import subprocess
import os
from langchain_core.tools import tool

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 允許執行的指令白名單前綴
_ALLOWED_PREFIXES = (
    "npm run",
    "npx",
    "python",
    "pytest",
    "docker",
    "alembic",
    "git diff",
    "git status",
    "git log",
    "ls",
    "cat",
    "grep",
    "find",
    "node",
)


@tool
def run_command(command: str, working_dir: str = "") -> str:
    """在 repo 內執行 shell 指令（限白名單）。

    working_dir 為相對於 repo root 的路徑，預設在 repo root 執行。
    回傳 stdout + stderr（最多 4000 字元）。
    """
    stripped = command.strip()
    if not any(stripped.startswith(p) for p in _ALLOWED_PREFIXES):
        return f"[拒絕] 指令不在允許清單中: {stripped}"

    cwd = os.path.join(REPO_ROOT, working_dir) if working_dir else REPO_ROOT
    if not os.path.isdir(cwd):
        return f"[錯誤] 工作目錄不存在: {working_dir}"

    try:
        result = subprocess.run(
            stripped,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        if len(output) > 4000:
            output = output[:4000] + "\n...[輸出已截斷]"
        return output or "[無輸出]"
    except subprocess.TimeoutExpired:
        return "[錯誤] 指令逾時（120s）"
    except Exception as e:
        return f"[錯誤] {e}"
