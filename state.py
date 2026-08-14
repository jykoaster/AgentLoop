from typing import TypedDict


class AgentState(TypedDict):
    task: str
    analysis: str
    plan: list[str]
    execution_result: str
    review_result: str   # output from review_node
    review_level: str    # "重寫" | "修補" | "" — set by review_node, read by analyze_plan
    review_blocking: bool  # set by review_node: True → replan (severe issue, or human-selected suggestions); False → pass
    status: str          # "pending" | "needs_revision" | "error" | "confirmed" | "aborted"
    iteration: int
    human_feedback: str  # user revision comments when rejecting the plan with N
    change_name: str     # asked once at initial planning; kebab-case OpenSpec change name; empty -> falls back to git branch name (sanitized)
    project_dir: str     # target project directory (relative to workspace root) this task's OpenSpec change lives in; reported by analyze_plan's initial-plan call, unchanged across replan/human-revise
