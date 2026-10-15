from langgraph.graph import StateGraph, START, END
from .state import AgentState
from . import stages
from ..nodes import analyze_plan_node, execute_node, review_node, human_confirm_node, archive_node

MAX_ITERATIONS = 3


def _tracked(stage: str, fn):
    """包裝節點函式：開始時記為 running（其後各階段重設 pending），結束時依回傳的
    status 記為 done／error。只碰 stages／stage_notes，不改節點回傳的其他欄位。

    上游已經是 error 時，這個節點只是沿著既有的無條件邊被呼叫一次、內部立刻短路
    回傳（例如 review_node／human_confirm_node 各自的 `status == "error"` guard），
    並沒有真的執行這個階段的工作，所以不記錄狀態轉換，讓它維持尚未開始。
    """
    def wrapped(state: AgentState) -> dict:
        if state.get("status") == "error":
            return fn(state)
        start_update = stages.start(state, stage)
        working_state = {**state, **start_update}
        result = fn(working_state)
        status = result.get("status", state.get("status"))
        finish_update = stages.finish({**working_state, **result}, stage, status)
        return {**start_update, **result, **finish_update}
    return wrapped


def _route_start(state: AgentState) -> str:
    return state.get("start_from", "") or "analyze_plan"


def route_after_review(state: AgentState) -> str:
    """review_node 已完成嚴重問題判定與（非嚴重建議的）人工確認，
    這裡只讀取其結論 review_blocking：
    - status 為 error → end（跳過 archive）
    - review_blocking 為 False（真正通過）→ archive（把這次的 change 併入持久 specs/）
    - review_blocking 為 True 且已達 iteration 上限（放棄重試）→ end（跳過 archive：
      沒有通過審查的東西不併入持久 specs/）
    - 其餘（review_blocking 為 True 且還能重試）→ replan"""
    if state.get("status") == "error":
        return "end"
    if not state.get("review_blocking", False):
        return "archive"
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

    graph.add_node("analyze_plan", _tracked("analyze_plan", analyze_plan_node))
    graph.add_node("human_confirm", _tracked("human_confirm", human_confirm_node))
    graph.add_node("execute", _tracked("execute", execute_node))
    graph.add_node("review", _tracked("review", review_node))
    graph.add_node("increment", increment_iteration)
    graph.add_node("archive_change", _tracked("archive", archive_node))

    # 流程：
    #   analyze_plan → human_confirm → [y] → execute → review → [pass] → archive_change → END
    #                       |                   ↑           |
    #                      [N]                  |       [fail, iter < MAX]
    #                       ↓                  |           ↓
    #                      END      increment → analyze_plan → human_confirm
    #
    # - human_confirm：規劃後人工審閱，輸入 y 才繼續，否則中止
    # - execute 內部自動修復測試失敗（最多重試 3 次），再交給 review 判定
    # - review 失敗回到 analyze_plan 重新規劃（需再次人工確認）
    # - review 通過 → archive_change：把這次的 OpenSpec change 併入目標專案持久的 openspec/specs/
    #   （放棄重試、或發生 error 時直接 END，不 archive）

    graph.add_conditional_edges(
        START,
        _route_start,
        {
            "analyze_plan": "analyze_plan",
            "human_confirm": "human_confirm",
            "execute": "execute",
            "review": "review",
            "increment": "increment",
            "archive_change": "archive_change",
        },
    )
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
        {"end": END, "replan": "increment", "archive": "archive_change"},
    )

    graph.add_edge("increment", "analyze_plan")
    graph.add_edge("archive_change", END)

    return graph.compile()


app = build_workflow()
