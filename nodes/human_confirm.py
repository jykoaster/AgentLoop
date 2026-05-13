import sys
import glob
import os
from ..state import AgentState

_CYAN   = "\033[1;36m"
_YELLOW = "\033[1;33m"
_GREEN  = "\033[1;32m"
_RED    = "\033[1;31m"
_RESET  = "\033[0m"


def _latest_plan_file() -> str | None:
    """回傳 docs/superpowers/plans/ 下最新的計畫文件路徑，找不到則回傳 None。"""
    pattern = os.path.join("docs", "superpowers", "plans", "*.md")
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def human_confirm_node(state: AgentState) -> dict:
    """規劃完成後的人工確認中斷點，輸入 y 才繼續執行。"""
    if state.get("status") == "error":
        return {"status": "error"}

    analysis = state.get("analysis", "（無）")
    plan = state.get("plan", [])

    print(f"\n{_CYAN}{'═'*60}", flush=True)
    print("  [人工確認] 規劃完成，請審閱後決定是否繼續執行", flush=True)
    print(f"{'═'*60}{_RESET}\n", flush=True)

    print(f"{_YELLOW}## 分析摘要{_RESET}", flush=True)
    print(analysis, flush=True)

    if plan:
        print(f"\n{_YELLOW}## 執行計畫（共 {len(plan)} 個 TASK）{_RESET}", flush=True)
        for i, task in enumerate(plan, 1):
            print(f"  TASK {i}: {task}", flush=True)

    plan_file = _latest_plan_file()
    if plan_file:
        print(f"\n{_YELLOW}## 計畫文件{_RESET}", flush=True)
        print(f"  {plan_file}", flush=True)

    print(f"\n{_CYAN}{'─'*60}{_RESET}", flush=True)

    if not sys.stdin.isatty():
        print(f"{_RED}  [人工確認] 非互動式模式，自動中止執行。{_RESET}\n", flush=True)
        return {"status": "aborted"}

    try:
        answer = input(f"{_YELLOW}  繼續執行？[y/N] {_RESET}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{_RED}  [人工確認] 已取消。{_RESET}\n", flush=True)
        return {"status": "aborted"}

    if answer == "y":
        print(f"\n{_GREEN}  [人工確認] 確認，開始執行。{_RESET}\n", flush=True)
        return {"status": "confirmed"}

    # User rejected — ask for revision comments before aborting
    print(f"\n{_YELLOW}  請輸入修改意見，讓 Agent 調整計畫（直接按 Enter 則中止執行）：{_RESET}", flush=True)
    try:
        feedback = input(f"{_YELLOW}  > {_RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        feedback = ""

    if feedback:
        print(f"\n{_CYAN}  [人工確認] 已收到意見，交由 Agent 重新規劃。{_RESET}\n", flush=True)
        return {"status": "needs_revision", "human_feedback": feedback}

    print(f"\n{_RED}  [人工確認] 已中止，工作流結束。{_RESET}\n", flush=True)
    return {"status": "aborted"}
