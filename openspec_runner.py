"""呼叫本機 `openspec` CLI 做 archive；跟 claude_runner.py 是「唯一跟 claude CLI 對話的地方」
同樣的角色，這裡是唯一跟 `openspec` CLI 對話的地方。規格文件本身的撰寫（init/new change/
validate）由 analyze_plan 的 Claude 呼叫自行透過 Bash 執行，不經過這個模組——只有「該不該
archive」是機械式判斷，值得獨立成一個不耗費 Claude 呼叫的 Python 節點。"""
import json
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class OpenSpecResult:
    ok: bool = False
    data: dict = field(default_factory=dict)
    error_text: str = ""


def archive_change(project_dir_abs: str, change_name: str, timeout: int = 120) -> OpenSpecResult:
    """執行 `openspec archive <change_name> --yes --json`：把 change 的 spec delta 合併進
    目標專案持久的 openspec/specs/，並把 change 資料夾搬到 openspec/changes/archive/。

    非互動模式下，驗證失敗、change 不存在等情況都會是 exit 1 + 一份 JSON 診斷（見 OpenSpec
    agent-contract 的 status: StoreDiagnostic[] 慣例），這裡容錯解析後回傳，呼叫端只記錄
    警告、不讓整個工作流程失敗。
    """
    if not shutil.which("openspec"):
        return OpenSpecResult(ok=False, error_text="找不到 `openspec` 指令，略過 archive")

    cmd = ["openspec", "archive", change_name, "--yes", "--json"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=project_dir_abs,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return OpenSpecResult(ok=False, error_text="openspec archive 執行逾時")
    except OSError as e:
        return OpenSpecResult(ok=False, error_text=f"openspec archive 執行失敗：{e}")

    data = {}
    stdout = proc.stdout.strip()
    if stdout:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            pass

    if proc.returncode == 0 and data.get("archive"):
        return OpenSpecResult(ok=True, data=data)

    error_text = ""
    status = data.get("status") or []
    if status:
        error_text = "; ".join(
            d.get("message", "") for d in status if isinstance(d, dict) and d.get("message")
        )
    if not error_text:
        error_text = proc.stderr.strip() or f"openspec archive 失敗（exit={proc.returncode}）"
    return OpenSpecResult(ok=False, data=data, error_text=error_text)
