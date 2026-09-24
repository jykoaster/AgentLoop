"""呼叫本機 `openspec` CLI 的唯一入口；跟 claude_runner.py 是「唯一跟 claude CLI 對話的地方」
同樣的角色，這裡是唯一跟 `openspec` CLI 對話的地方。init / new change / validate / archive
都是機械式判斷（存在就跳過、失敗就回報訊息，不需要 Claude 的判斷力），因此由 analyze_plan／
archive_node 直接呼叫這裡，不耗費 Claude 呼叫、也不透過 Claude 的 Bash 執行。"""
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date


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


# 與 OpenSpec `ARCHIVE_DATE_PREFIX_PATTERN` 一致：change 名稱已帶日期前綴時不再疊加。
_ARCHIVE_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
_MAX_ARCHIVE_SUFFIX = 1000


def archive_destination_name(change_name: str, today: str | None = None) -> str:
    """OpenSpec 寫入 `openspec/changes/archive/` 的目標資料夾名。

    change 名稱已以 `YYYY-MM-DD-` 開頭（常見於分支轉 kebab-case）就原樣使用，否則
    前置今天的本地日期。規則必須跟 CLI 一致，否則「先讓出舊 archive」會讓錯資料夾。
    """
    if _ARCHIVE_DATE_PREFIX_RE.match(change_name):
        return change_name
    if today is None:
        today = date.today().isoformat()
    return f"{today}-{change_name}"


def vacate_existing_archive(project_dir_abs: str, dest_name: str) -> tuple[str | None, str]:
    """若 archive 目標已存在，改名成 `dest-2` / `dest-3` … 讓出原名給這次 archive。

    同一個 change 同一天（或名稱本身已帶日期前綴）再 archive 一次時，OpenSpec 會以
    `Archive '…' already exists.` 拒絕覆寫。舊資料夾是歷史快照，改名保留、不刪除。
    回傳 `(新名稱, "")`；目標不存在則 `(None, "")`；無法讓出時第二個元素為錯誤訊息。
    """
    if not dest_name or dest_name in (".", "..") or os.sep in dest_name:
        return None, f"不合法的 archive 名稱：{dest_name!r}"

    archive_dir = os.path.join(project_dir_abs, "openspec", "changes", "archive")
    dest_path = os.path.join(archive_dir, dest_name)
    if not os.path.lexists(dest_path):
        return None, ""

    for n in range(2, _MAX_ARCHIVE_SUFFIX):
        vacated = f"{dest_name}-{n}"
        vacated_path = os.path.join(archive_dir, vacated)
        if os.path.lexists(vacated_path):
            continue
        try:
            os.rename(dest_path, vacated_path)
        except OSError as e:
            return None, f"無法將既有 archive 改名為 {vacated}：{e}"
        return vacated, ""
    return None, f"既有 archive 過多，無法為 {dest_name} 找到可用後綴"


def archive_change(project_dir_abs: str, change_name: str, timeout: int = 120) -> OpenSpecResult:
    """執行 `openspec archive <change_name> --yes --json`：把 change 的 spec delta 合併進
    目標專案持久的 openspec/specs/，並把 change 資料夾搬到 openspec/changes/archive/。

    目標資料夾已存在時（同一 change 被 archive 過後又改、再 archive），先把舊的改名讓出
    原名，再呼叫 CLI——OpenSpec 不會覆寫既有 archive，也不提供 suffix / force 旗標。

    非互動模式下，驗證失敗、change 不存在等情況都會是 exit 1 + 一份 JSON 診斷（見 OpenSpec
    agent-contract 的 status: StoreDiagnostic[] 慣例），這裡容錯解析後回傳，呼叫端只記錄
    警告、不讓整個工作流程失敗。
    """
    dest_name = archive_destination_name(change_name)
    vacated_as, vacate_error = vacate_existing_archive(project_dir_abs, dest_name)
    if vacate_error:
        return OpenSpecResult(ok=False, error_text=vacate_error)

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
        if vacated_as:
            data["vacated_as"] = vacated_as
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
