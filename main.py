"""
CLI 入口點：執行 LangGraph 四 Agent 工作流，或單獨呼叫任一 node。

用法：
  # 完整工作流（任務描述必填）
  python -m AgentLoop.main "幫我在後端新增一個 GET /tables/featured 端點，同時在前端首頁顯示精選桌遊"

  # 單獨呼叫 node：不帶任務描述。列出目標專案已有 state.json 的 changes 供選擇，
  # 任務描述與其餘欄位一律沿用該 change 的 state，跑完後繼續後面的流程。
  python -m AgentLoop.main --node analyze_plan
  python -m AgentLoop.main --node execute
  python -m AgentLoop.main --node review
  python -m AgentLoop.main --node archive
"""
import sys
import os
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from .core import app, AgentState, MAX_ITERATIONS
from .lib import REPO_ROOT

_BOLD  = "\033[1m"
_RESET = "\033[0m"

_NODES = ("analyze_plan", "execute", "review", "archive")


def _agentloop_dir(project_dir: str, change_name: str) -> Path:
    return Path(REPO_ROOT) / project_dir / ".agentloop" / "changes" / change_name


def _save_state(state: dict) -> None:
    project_dir = state.get("project_dir", "")
    change_name = state.get("change_name", "")
    if not project_dir or not change_name:
        return
    try:
        d = _agentloop_dir(project_dir, change_name)
        d.mkdir(parents=True, exist_ok=True)
        to_save = {k: v for k, v in state.items() if k not in ("project_dir", "start_from")}
        text = json.dumps(to_save, ensure_ascii=False, indent=2)
        # Claude output may contain lone surrogates; strip them before writing UTF-8
        text = text.encode("utf-8", errors="replace").decode("utf-8")
        (d / "state.json").write_text(text, encoding="utf-8")
    except Exception as e:
        print(f"\033[1;31m  [state] 儲存失敗：{e}\033[0m", flush=True)


def _list_and_select_change() -> dict:
    """列出目標專案內已有 state.json 的 changes，讓使用者選擇後回傳載入的 state。

    找不到任何 change 就中止：`--node` 不收任務描述，任務只能來自既有 state，
    所以沒有 state 可載入時無事可做——全新任務請用完整工作流的形式。
    """
    target = os.environ.get("TARGET_PROJECT", "").strip()
    if not target:
        print("\033[1;31m  錯誤：TARGET_PROJECT 環境變數未設定\033[0m")
        sys.exit(1)

    changes_root = Path(REPO_ROOT) / target / ".agentloop" / "changes"
    changes: list[str] = []
    if changes_root.is_dir():
        changes = sorted(
            d.name for d in changes_root.iterdir()
            if d.is_dir() and (d / "state.json").is_file()
        )

    if not changes:
        print(
            f"\033[1;31m  找不到任何已存在的 change state（{changes_root}）\033[0m\n"
            f"  全新任務請用完整工作流：python -m AgentLoop.main \"<任務描述>\""
        )
        sys.exit(1)

    print(f"\n{_BOLD}  可用的 changes：{_RESET}")
    for i, c in enumerate(changes, 1):
        print(f"    {i}. {c}")

    while True:
        try:
            answer = input(f"\n  請輸入編號（1–{len(changes)}）：").strip()
            idx = int(answer) - 1
            if 0 <= idx < len(changes):
                break
        except (ValueError, EOFError, KeyboardInterrupt):
            pass
        print("  請輸入有效的編號")

    change_name = changes[idx]
    state_path = changes_root / change_name / "state.json"
    with state_path.open(encoding="utf-8") as f:
        state_data = json.load(f)
    state_data["project_dir"] = target
    print(f"\n  已載入 change：{change_name}\n")
    return state_data


def _empty_state(task: str) -> AgentState:
    return {
        "task": task,
        "analysis": "",
        "plan": [],
        "execution_result": "",
        "review_result": "",
        "review_level": "",
        "review_blocking": False,
        "status": "pending",
        "iteration": 0,
        "human_feedback": "",
        "change_name": "",
        "branch_name": "",
        "project_dir": "",
        "domains": [],
        "session_node": "",
        "session_id": "",
        "start_from": "",
    }


def _stream_and_save(initial_state: dict, start_from: str | None = None) -> str:
    """執行 app.stream()，每個 node 結束後存 state，回傳最終 status。
    start_from 不為 None 時注入 state["start_from"]，由 _route_start 讀取決定 entry point。
    """
    current_state = dict(initial_state)
    if start_from:
        current_state["start_from"] = start_from
    final_status = current_state.get("status", "pending")
    for step in app.stream(current_state):
        if "increment" in step:
            iteration = step["increment"].get("iteration", "?")
            print(f"\n\033[1;33m  ↩ 重試第 {iteration} 次（檢查未通過）\033[0m\n")
        for node_name, updates in step.items():
            if isinstance(updates, dict):
                current_state.update(updates)
                if "status" in updates:
                    final_status = updates["status"]
        _save_state(current_state)
    return final_status


def run(task: str) -> None:
    print(f"\n{_BOLD}{'═'*60}")
    print(f"  任務：{task}")
    print(f"{'═'*60}{_RESET}\n")

    final_status = "pending"
    try:
        final_status = _stream_and_save(_empty_state(task))
    except Exception as e:
        print(f"\n\033[1;31m{'═'*60}")
        print(f"  工作流發生未預期錯誤：{e}")
        print(f"{'═'*60}\033[0m\n")
        return

    print(f"\n{_BOLD}{'═'*60}")
    if final_status == "error":
        print(f"\033[1;31m  工作流結束（發生錯誤，詳見上方日誌）\033[0m")
    else:
        print("  工作流結束")
    print(f"{'═'*60}{_RESET}\n")


_NEXT_NODE: dict[str, str] = {
    "analyze_plan": "human_confirm",
    "execute": "review",
}


def _route_after_review(state: dict) -> str | None:
    """複製 workflow.route_after_review 的路由邏輯，回傳下一個 start_from 或 None（END）。"""
    if state.get("status") == "error":
        return None
    if not state.get("review_blocking", False):
        return "archive_change"
    if state.get("iteration", 0) >= MAX_ITERATIONS:
        return None
    return "increment"


def run_node(node_name: str) -> None:
    from .nodes import analyze_plan_node, execute_node, review_node, archive_node

    node_fn = {
        "analyze_plan": analyze_plan_node,
        "execute": execute_node,
        "review": review_node,
        "archive": archive_node,
    }[node_name]

    # 任務描述與其餘欄位全部來自選定 change 的 state；_empty_state 只負責補上
    # 舊版 state.json 可能缺少的欄位預設值（例如後來才加的 session 插槽）。
    state = _empty_state("")
    state.update(_list_and_select_change())

    print(f"\n{_BOLD}{'═'*60}")
    print(f"  單獨執行 node：{node_name}")
    print(f"  任務：{state['task']}")
    print(f"{'═'*60}{_RESET}\n")

    result = node_fn(state)
    state.update(result)
    _save_state(state)

    print(f"\n{_BOLD}{'═'*60}")
    print(f"  Node {node_name} 完成")
    if result.get("status") == "error":
        print(f"\033[1;31m  狀態：error\033[0m")
    print(f"{'═'*60}{_RESET}\n")

    # archive 是終點，不繼續
    if node_name == "archive":
        return

    # 決定下一個 entry point
    if node_name == "review":
        start_from = _route_after_review(state)
        if start_from is None:
            return
    else:
        start_from = _NEXT_NODE[node_name]

    # 繼續後面的流程
    print(f"\n{_BOLD}{'═'*60}")
    print(f"  繼續流程（從 {start_from}）")
    print(f"{'═'*60}{_RESET}\n")

    try:
        final_status = _stream_and_save(state, start_from=start_from)
    except Exception as e:
        print(f"\n\033[1;31m{'═'*60}")
        print(f"  工作流發生未預期錯誤：{e}")
        print(f"{'═'*60}\033[0m\n")
        return

    print(f"\n{_BOLD}{'═'*60}")
    if final_status == "error":
        print(f"\033[1;31m  工作流結束（發生錯誤，詳見上方日誌）\033[0m")
    else:
        print("  工作流結束")
    print(f"{'═'*60}{_RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m AgentLoop.main",
        description="執行 LangGraph 工作流或單獨呼叫 node",
    )
    parser.add_argument(
        "task",
        nargs="?",
        help="任務描述（完整工作流必填；--node 模式不接受，任務描述取自選定 change 的 state）",
    )
    parser.add_argument(
        "--node",
        choices=_NODES,
        metavar="NODE",
        help=f"從指定 node 開始執行（{', '.join(_NODES)}）；state 從目標專案的 .agentloop/changes/ 載入",
    )
    args = parser.parse_args()

    if args.node:
        if args.task:
            parser.error(
                "--node 模式不接受任務描述：任務描述取自選定 change 的 state.json。"
                "傳入佔位字串會覆蓋掉原本的任務並寫回 state"
            )
        run_node(args.node)
    else:
        if not args.task:
            parser.error("缺少任務描述")
        run(args.task)


if __name__ == "__main__":
    main()
