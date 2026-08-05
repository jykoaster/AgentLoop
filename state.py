from typing import TypedDict


class AgentState(TypedDict):
    task: str
    analysis: str
    plan: list[str]
    execution_result: str
    review_result: str   # output from review_node
    review_level: str    # "重寫" | "修補" | "" — set by review_node, read by analyze_plan
    status: str          # "pending" | "needs_revision" | "error" | "confirmed" | "aborted"
    iteration: int
    human_feedback: str  # user revision comments when rejecting the plan with N
