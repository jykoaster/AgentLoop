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


def _projects_with_change(change_name: str) -> list[str]:
    found: list[str] = []
    try:
        entries = os.listdir(REPO_ROOT)
    except OSError:
        return found
    for entry in sorted(entries):
        if entry.startswith("."):
            continue
        change_dir = os.path.join(REPO_ROOT, entry, "openspec", "changes", change_name)
        if os.path.isdir(change_dir) and os.path.isfile(os.path.join(change_dir, "proposal.md")):
            found.append(entry)
    return found


def _resolve_location(change_name: str, project_dir: str) -> tuple[str, str, str]:
    """回傳 (project_dir, change_name, error)。error 非空表示無法定位。"""
    names = _change_names_to_try(change_name)
    if not names:
        return "", "", "缺少 change 名稱"

    if project_dir:
        # 工作流已指定專案時先不要檢查目錄是否存在：change 可能只在即將
        # checkout 的分支上。名稱用呼叫端給的原值（必要時的 kebab 備援由掃描路徑處理）。
        return project_dir, names[0], ""

    matches: list[tuple[str, str]] = []
    for name in names:
        for proj in _projects_with_change(name):
            matches.append((proj, name))

    if not matches:
        return "", "", f"工作區找不到 openspec/changes/{change_name}/"

    if len(matches) == 1:
        proj, name = matches[0]
        return proj, name, ""

    target = os.environ.get("TARGET_PROJECT", "").strip()
    preferred = [m for m in matches if m[0] == target]
    if len(preferred) == 1:
        proj, name = preferred[0]
        return proj, name, ""

    listed = "、".join(f"{p}/openspec/changes/{n}" for p, n in matches)
    return "", "", f"同一個 change 出現在多個專案，請用 --state-file 指定 project_dir：{listed}"


def archive_node(state: AgentState) -> dict:
    """review 通過後的收尾動作：把這次的 OpenSpec change 併入目標專案持久的 openspec/specs/。
    純機械式判斷（review 通過就 archive），不需要 Claude 的判斷力，直接呼叫 openspec CLI。
    失敗只印警告、不讓整個工作流程失敗——程式碼已經審查通過，archive 只是收尾動作，
    失敗頂多之後手動補跑。

    單獨執行時沒有 project_dir／change_name 的話，用 task 當 change 名稱，
    掃描工作區 `*/openspec/changes/<name>/` 定位目標專案。
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
