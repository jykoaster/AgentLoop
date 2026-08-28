import re
import sys
import unicodedata
from ..state import AgentState

_CYAN   = "\033[1;36m"
_YELLOW = "\033[1;33m"
_GREEN  = "\033[1;32m"
_RED    = "\033[1;31m"
_RESET  = "\033[0m"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _normalize_confirm(text: str) -> str:
    """正規化 y/N 輸入：去掉 ANSI／控制字元，全形轉半形，忽略空白，轉小寫。"""
    text = _ANSI_RE.sub("", text)
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    return "".join(text.split()).lower()


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

    project_dir = state.get("project_dir", "")
    change_name = state.get("change_name", "")
    branch_name = state.get("branch_name", "")
    if project_dir and change_name:
        print(f"\n{_YELLOW}## OpenSpec Change{_RESET}", flush=True)
        print(f"  {project_dir}/openspec/changes/{change_name}/", flush=True)
        if branch_name:
            print(f"  工作分支：{branch_name}", flush=True)

    print(f"\n{_CYAN}{'─'*60}{_RESET}", flush=True)

    if not sys.stdin.isatty():
        print(f"{_RED}  [人工確認] 非互動式模式，自動中止執行。{_RESET}\n", flush=True)
        return {"status": "aborted"}

    # 中文／全形字元不可放進 input() 的 prompt：GNU readline 用字元數而非
    # 顯示欄寬計算游標，會把第一個輸入字元吃掉或混進控制碼，導致畫面上看
    # 得到 y、比對卻失敗。提示改由 print 輸出，input() 只負責讀一行。
    print(f"{_YELLOW}  繼續執行？[y/N] {_RESET}", end="", flush=True)
    try:
        answer = _normalize_confirm(input())
    except (EOFError, KeyboardInterrupt):
        print(f"\n{_RED}  [人工確認] 已取消。{_RESET}\n", flush=True)
        return {"status": "aborted"}

    if answer in {"y", "yes"}:
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
