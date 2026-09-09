import os
import re
import sys
from ..core import AgentState
from ..lib import REPO_ROOT, archive_change, ensure_on_branch

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


def _ask_should_archive(project_dir: str, change_name: str) -> bool:
    """archive 前的人工卡控：詢問是否要把這個 change 併入目標專案持久的 openspec/specs/。
    這是可選的安全機制，不是必填流程——非互動式環境（無法提問）或使用者中止都視為
    「否」，跟其他 archive 略過的情況一樣只印出提示與手動指令，不讓整個流程失敗。

    CJK 字元不可放進 input() 的 prompt 參數（GNU readline 用字元數而非顯示欄寬計算
    游標，會吃掉或混進控制碼導致誤判輸入），提示改由 print 輸出，input() 只負責讀一行。
    """
    print(
        f"{_YELLOW}  是否要將此 change 併入 {project_dir}/openspec/specs/？[y/N] {_RESET}",
        end="",
        flush=True,
    )
    if not sys.stdin.isatty():
        print("N（非互動式環境）", flush=True)
        return False
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(flush=True)
        return False
    return answer in ("y", "yes")


def archive_node(state: AgentState) -> dict:
    """review 通過後的收尾動作：詢問是否要把這次的 OpenSpec change 併入目標專案持久的
    openspec/specs/，同意才呼叫 openspec CLI archive；「該不該問、問完怎麼做」都是機械式
    判斷，不需要 Claude 的判斷力。使用者選擇不 archive、或 archive 本身失敗，都只印警告、
    不讓整個工作流程失敗——程式碼已經審查通過，archive 只是收尾動作，略過或失敗頂多之後
    手動補跑。

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

    if not _ask_should_archive(project_dir, change_name):
        print(
            f"{_YELLOW}  [Archive] 使用者選擇不 archive，略過。\n"
            f"  可稍後手動執行：cd {project_dir} && openspec archive {change_name} --yes{_RESET}\n",
            flush=True,
        )
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
