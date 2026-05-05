from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import analyze_plan_node, execute_node, review_node
from .nodes.review import has_blocking_issues

MAX_ITERATIONS = 3


def route_after_review(state: AgentState) -> str:
    """Review 通過 → end；未通過（含 TASK 未完成）→ 重新規劃。"""
    review_result = state.get("review_result", "")
    if state.get("status") == "error":
        return "end"
    if review_result == "SKIPPED" or not has_blocking_issues(review_result):
        return "end"
    if state.get("iteration", 0) >= MAX_ITERATIONS:
        return "end"
    return "replan"


def increment_iteration(state: AgentState) -> dict:
    return {
        "iteration": state.get("iteration", 0) + 1,
        "status": "pending",
    }


def build_workflow() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("analyze_plan", analyze_plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("review", review_node)
    graph.add_node("increment", increment_iteration)

    # 流程：
    #   analyze_plan → execute → review → [pass] → END
    #                    ↑           |
    #                    |       [fail, iter < MAX]
    #                    |           ↓
    #                    └─────── increment → analyze_plan
    #
    # - execute 內部自動修復測試失敗（最多重試 3 次），再交給 review 判定
    # - review 失敗回到 analyze_plan 重新規劃
    # - analyze_plan 根據 review_level（重寫/修補）決定是否 rollback

    graph.set_entry_point("analyze_plan")
    graph.add_edge("analyze_plan", "execute")
    graph.add_edge("execute", "review")

    graph.add_conditional_edges(
        "review",
        route_after_review,
        {"end": END, "replan": "increment"},
    )

    graph.add_edge("increment", "analyze_plan")

    return graph.compile()


app = build_workflow()
