"""呼叫本機 `openspec` CLI 的唯一入口；跟 claude_runner.py 是「唯一跟 claude CLI 對話的地方」
同樣的角色，這裡是唯一跟 `openspec` CLI 對話的地方。init / new change / validate / archive
都是機械式判斷（存在就跳過、失敗就回報訊息，不需要 Claude 的判斷力），因此由 analyze_plan／
archive_node 直接呼叫這裡，不耗費 Claude 呼叫、也不透過 Claude 的 Bash 執行。"""
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class OpenSpecResult:
    ok: bool = False
    data: dict = field(default_factory=dict)
    error_text: str = ""


def ensure_initialized(project_dir_abs: str, timeout: int = 60) -> OpenSpecResult:
    """確保目標專案已有 `openspec/`；已存在則直接視為成功，不重複執行 init。"""
    if os.path.isdir(os.path.join(project_dir_abs, "openspec")):
        return OpenSpecResult(ok=True)
    if not shutil.which("openspec"):
        return OpenSpecResult(ok=False, error_text="找不到 `openspec` 指令")

    try:
        proc = subprocess.run(
            ["openspec", "init", "--tools", "claude", "--force"],
            cwd=project_dir_abs,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return OpenSpecResult(ok=False, error_text="openspec init 執行逾時")
    except OSError as e:
        return OpenSpecResult(ok=False, error_text=f"openspec init 執行失敗：{e}")

    if proc.returncode != 0:
        return OpenSpecResult(
            ok=False, error_text=(proc.stderr or proc.stdout or "openspec init 失敗").strip()
        )
    return OpenSpecResult(ok=True)


def ensure_change_created(project_dir_abs: str, change_name: str, timeout: int = 60) -> OpenSpecResult:
    """建立 OpenSpec change 資料夾；已存在則直接視為成功，避免覆蓋既有內容。"""
    change_dir = os.path.join(project_dir_abs, "openspec", "changes", change_name)
    if os.path.isdir(change_dir):
        return OpenSpecResult(ok=True)
    if not shutil.which("openspec"):
        return OpenSpecResult(ok=False, error_text="找不到 `openspec` 指令")

    try:
        proc = subprocess.run(
            ["openspec", "new", "change", change_name],
            cwd=project_dir_abs,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return OpenSpecResult(ok=False, error_text="openspec new change 執行逾時")
    except OSError as e:
        return OpenSpecResult(ok=False, error_text=f"openspec new change 執行失敗：{e}")

    if proc.returncode != 0:
        return OpenSpecResult(
            ok=False, error_text=(proc.stderr or proc.stdout or "openspec new change 失敗").strip()
        )
    return OpenSpecResult(ok=True)


def validate_change(project_dir_abs: str, change_name: str, timeout: int = 60) -> OpenSpecResult:
    """執行 `openspec validate <change_name> --json --strict`。`ok` 只代表沒有 ERROR 等級的
    issue（WARNING 不阻擋）；`error_text` 彙整所有 ERROR 訊息，供回傳給 Claude 修正用。
    """
    if not shutil.which("openspec"):
        return OpenSpecResult(ok=False, error_text="找不到 `openspec` 指令")

    try:
        proc = subprocess.run(
            ["openspec", "validate", change_name, "--json", "--strict"],
            cwd=project_dir_abs,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return OpenSpecResult(ok=False, error_text="openspec validate 執行逾時")
    except OSError as e:
        return OpenSpecResult(ok=False, error_text=f"openspec validate 執行失敗：{e}")

    data = {}
    stdout = proc.stdout.strip()
    if stdout:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            pass

    items = data.get("items")
    if items is None:
        # change/spec 找不到等情況是另一種 JSON 形狀：{"status": [...]}
        status = data.get("status") or []
        error_text = "; ".join(
            d.get("message", "") for d in status if isinstance(d, dict) and d.get("message")
        )
        if not error_text:
            error_text = proc.stderr.strip() or f"openspec validate 失敗（exit={proc.returncode}）"
        return OpenSpecResult(ok=False, data=data, error_text=error_text)

    errors = [
        f"[{issue.get('path', '')}] {issue.get('message', '')}"
        for item in items
        for issue in item.get("issues", [])
        if issue.get("level") == "ERROR"
    ]
    if not errors:
        return OpenSpecResult(ok=True, data=data)
    return OpenSpecResult(ok=False, data=data, error_text="\n".join(errors))


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
