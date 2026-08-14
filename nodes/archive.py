import os
from ..state import AgentState
from ..project_context import REPO_ROOT
from ..openspec_runner import archive_change

_BANNER = "\033[1;35m"
_YELLOW = "\033[1;33m"
_RESET  = "\033[0m"


def archive_node(state: AgentState) -> dict:
    """review 通過後的收尾動作：把這次的 OpenSpec change 併入目標專案持久的 openspec/specs/。
    純機械式判斷（review 通過就 archive），不需要 Claude 的判斷力，直接呼叫 openspec CLI。
    失敗只印警告、不讓整個工作流程失敗——程式碼已經審查通過，archive 只是收尾動作，
    失敗頂多之後手動補跑。
    """
    print(f"\n{_BANNER}{'═'*50}\n  [Archive] 開始\n{'═'*50}{_RESET}\n", flush=True)

    project_dir = state.get("project_dir", "")
    change_name = state.get("change_name", "")
    if not project_dir or not change_name:
        print(f"{_YELLOW}  [Archive] 缺少 project_dir/change_name，略過{_RESET}\n", flush=True)
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
