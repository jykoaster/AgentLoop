import os
import re
from ..state import AgentState
from ..project_context import REPO_ROOT
from ..openspec_runner import archive_change
from ..git_ops import ensure_on_branch

_BANNER = "\033[1;35m"
_YELLOW = "\033[1;33m"
_RESET  = "\033[0m"

_KEBAB_INVALID_RE = re.compile(r"[^a-z0-9-]+")
_MULTI_HYPHEN_RE = re.compile(r"-{2,}")


def _kebab(raw: str) -> str:
    s = raw.strip().lower().replace("/", "-")
    s = re.sub(r"[\s_]+", "-", s)
    s = _KEBAB_INVALID_RE.sub("", s)
    s = _MULTI_HYPHEN_RE.sub("-", s)
    return s.strip("-")


def _change_names_to_try(raw: str) -> list[str]:
    names: list[str] = []
    for name in (raw.strip(), _kebab(raw)):
        if name and name not in names and name not in (".", "..") and os.sep not in name:
            names.append(name)
    return names


def _resolve_location(change_name: str, project_dir: str) -> tuple[str, str, str]:
    """回傳 (project_dir, change_name, error)。error 非空表示無法定位。

    workspace 只支援掛載單一目標專案：project_dir 未指定時直接採用環境變數
    TARGET_PROJECT，不再掃描工作區比對哪個專案有這個 change。
    """
    names = _change_names_to_try(change_name)
    if not names:
        return "", "", "缺少 change 名稱"

    if project_dir:
        # 工作流已指定專案時先不要檢查目錄是否存在：change 可能只在即將
        # checkout 的分支上。名稱用呼叫端給的原值（必要時的 kebab 備援由下方比對處理）。
        return project_dir, names[0], ""

    target = os.environ.get("TARGET_PROJECT", "").strip()
    if not target:
        return "", "", "缺少 project_dir，且環境變數 TARGET_PROJECT 未設定"

    for name in names:
        change_dir = os.path.join(REPO_ROOT, target, "openspec", "changes", name)
        if os.path.isdir(change_dir) and os.path.isfile(os.path.join(change_dir, "proposal.md")):
            return target, name, ""

    return "", "", f"{target}/openspec/changes/ 底下找不到 {change_name}"


def archive_node(state: AgentState) -> dict:
    """review 通過後的收尾動作：把這次的 OpenSpec change 併入目標專案持久的 openspec/specs/。
    純機械式判斷（review 通過就 archive），不需要 Claude 的判斷力，直接呼叫 openspec CLI。
    失敗只印警告、不讓整個工作流程失敗——程式碼已經審查通過，archive 只是收尾動作，
    失敗頂多之後手動補跑。

    單獨執行時沒有 change_name 的話，用 task 當 change 名稱；沒有 project_dir 的話，
    直接採用環境變數 TARGET_PROJECT 定位目標專案。
    """
    print(f"\n{_BANNER}{'═'*50}\n  [Archive] 開始\n{'═'*50}{_RESET}\n", flush=True)

    change_name = (state.get("change_name") or "").strip() or (state.get("task") or "").strip()
    project_dir = (state.get("project_dir") or "").strip()
    branch_name = (state.get("branch_name") or "").strip()

    project_dir, change_name, error = _resolve_location(change_name, project_dir)
    if error:
        print(f"{_YELLOW}  [Archive] {error}，略過{_RESET}\n", flush=True)
        return {}

    print(
        f"{_YELLOW}  定位：{project_dir}/openspec/changes/{change_name}/{_RESET}",
        flush=True,
    )

    if branch_name:
        ok, msg = ensure_on_branch(project_dir, branch_name)
        print(f"{_YELLOW}  [git] {msg}{_RESET}", flush=True)
        if not ok:
            print(f"{_YELLOW}  [Archive] 無法切換到指定分支，略過{_RESET}\n", flush=True)
            return {}

    project_dir_abs = os.path.join(REPO_ROOT, project_dir)
    result = archive_change(project_dir_abs, change_name)

    if result.ok:
        archived = result.data.get("archive", {})
        print(
            f"{_BANNER}  [Archive] 完成，已合併進 "
            f"{project_dir}/openspec/specs/（{archived.get('archivedAs', change_name)}）{_RESET}\n",
            flush=True,
        )
    else:
        print(
            f"{_YELLOW}  [Archive] 未完成：{result.error_text}\n"
            f"  可稍後手動執行：cd {project_dir} && openspec archive {change_name} --yes{_RESET}\n",
            flush=True,
        )

    return {}
