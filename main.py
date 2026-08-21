"""
CLI 入口點：執行 LangGraph 四 Agent 工作流，或單獨呼叫任一 node。

用法：
  # 完整工作流
  python -m AgentLoop.main "幫我在後端新增一個 GET /tables/featured 端點，同時在前端首頁顯示精選桌遊"

  # 單獨呼叫 node
  python -m AgentLoop.main --node review "任務描述"
  python -m AgentLoop.main --node execute "任務描述"
  python -m AgentLoop.main --node analyze_plan "任務描述"

  # 帶前置狀態的單獨呼叫（JSON 檔案）
  python -m AgentLoop.main --node review --state-file /tmp/state.json "任務描述"

  # archive 不需要 task，但需靠 --state-file 帶入 project_dir / change_name（與 branch_name）
  python -m AgentLoop.main --node archive --state-file /tmp/archive_state.json "封存"
"""
import sys
import os
import json
import argparse
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from .workflow import app
from .state import AgentState

_BOLD  = "\033[1m"
_RESET = "\033[0m"

_NODES = ("analyze_plan", "execute", "review", "archive")


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
    }


def run(task: str) -> None:
    print(f"\n{_BOLD}{'═'*60}")
    print(f"  任務：{task}")
    print(f"{'═'*60}{_RESET}\n")

    initial_state = _empty_state(task)

    final_status = "pending"
    try:
        for step in app.stream(initial_state):
            if "increment" in step:
                iteration = step["increment"].get("iteration", "?")
                print(f"\n\033[1;33m  ↩ 重試第 {iteration} 次（檢查未通過）\033[0m\n")
            for updates in step.values():
                if isinstance(updates, dict) and "status" in updates:
                    final_status = updates["status"]
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


def run_node(node_name: str, task: str, state_file: str | None = None) -> None:
    from .nodes import analyze_plan_node, execute_node, review_node, archive_node

    node_fn = {
        "analyze_plan": analyze_plan_node,
        "execute": execute_node,
        "review": review_node,
        "archive": archive_node,
    }[node_name]

    state = _empty_state(task)
    if state_file:
        try:
            with open(state_file, encoding="utf-8") as f:
                overrides = json.load(f)
            state.update(overrides)
            state["task"] = task  # CLI task 優先
        except Exception as e:
            print(f"\033[1;31m  [錯誤] 讀取 state-file 失敗：{e}\033[0m")
            sys.exit(1)

    print(f"\n{_BOLD}{'═'*60}")
    print(f"  單獨執行 node：{node_name}")
    print(f"  任務：{task}")
    print(f"{'═'*60}{_RESET}\n")

    result = node_fn(state)

    print(f"\n{_BOLD}{'═'*60}")
    print(f"  Node {node_name} 完成")
    if result.get("status") == "error":
        print(f"\033[1;31m  狀態：error\033[0m")
    print(f"{'═'*60}{_RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m AgentLoop.main",
        description="執行 LangGraph 工作流或單獨呼叫 node",
    )
    parser.add_argument("task", help="任務描述")
    parser.add_argument(
        "--node",
        choices=_NODES,
        metavar="NODE",
        help=f"單獨執行指定 node（{', '.join(_NODES)}）",
    )
    parser.add_argument(
        "--state-file",
        metavar="PATH",
        help="帶入前置狀態的 JSON 檔案路徑（配合 --node 使用）",
    )
    args = parser.parse_args()

    if args.node:
        run_node(args.node, args.task, args.state_file)
    else:
        if args.state_file:
            print("警告：--state-file 只在 --node 模式下有效，已忽略")
        run(args.task)


if __name__ == "__main__":
    main()
