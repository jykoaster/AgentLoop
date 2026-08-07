from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import analyze_plan_node, execute_node, review_node, human_confirm_node

MAX_ITERATIONS = 3


def route_after_review(state: AgentState) -> str:
    """review_node 已完成嚴重問題判定與（非嚴重建議的）人工確認，
    這裡只讀取其結論 review_blocking：False → end；True（且未達 iteration 上限）→ 重新規劃。"""
    if state.get("status") == "error":
        return "end"
    if not state.get("review_blocking", False):
        return "end"
    if state.get("iteration", 0) >= MAX_ITERATIONS:
        return "end"
    return "replan"


def increment_iteration(state: AgentState) -> dict:
    return {
        "iteration": state.get("iteration", 0) + 1,
        "status": "pending",
    }


def route_after_confirm(state: AgentState) -> str:
    """人工確認通過 → execute；有修改意見 → analyze_plan；中止或錯誤 → end。"""
    status = state.get("status")
    if status == "confirmed":
        return "execute"
    if status == "needs_revision":
        return "replan"
    return "end"  # covers "aborted", "error", unexpected values


def build_workflow() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("analyze_plan", analyze_plan_node)
    graph.add_node("human_confirm", human_confirm_node)
    graph.add_node("execute", execute_node)
    graph.add_node("review", review_node)
    graph.add_node("increment", increment_iteration)

    # 流程：
    #   analyze_plan → human_confirm → [y] → execute → review → [pass] → END
    #                       |                   ↑           |
    #                      [N]                  |       [fail, iter < MAX]
    #                       ↓                  |           ↓
    #                      END      increment → analyze_plan → human_confirm
    #
    # - human_confirm：規劃後人工審閱，輸入 y 才繼續，否則中止
    # - execute 內部自動修復測試失敗（最多重試 3 次），再交給 review 判定
    # - review 失敗回到 analyze_plan 重新規劃（需再次人工確認）

    graph.set_entry_point("analyze_plan")
    graph.add_edge("analyze_plan", "human_confirm")

    graph.add_conditional_edges(
        "human_confirm",
        route_after_confirm,
        {"execute": "execute", "replan": "analyze_plan", "end": END},
    )

    graph.add_edge("execute", "review")

    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"end": END, "replan": "increment"},
    )

    graph.add_edge("increment", "analyze_plan")

    return graph.compile()


app = build_workflow()
