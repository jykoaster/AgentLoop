from typing import TypedDict


class AgentState(TypedDict):
    task: str
    analysis: str          # proposal.md 全文，供 human_confirm 顯示
    plan: list[str]        # tasks.md checkbox 清單，供 human_confirm 顯示（execute／review 自行讀檔）
    execution_result: str  # 執行節點的文字摘要（除錯／state-file；review 不注入）
    review_result: str   # output from review_node
    review_level: str    # "重寫" | "修補" | "" — set by review_node, read by analyze_plan
    review_blocking: bool  # set by review_node: True → replan (severe issue, or human-selected suggestions); False → pass
    status: str          # "pending" | "needs_revision" | "error" | "confirmed" | "aborted"
    iteration: int
    human_feedback: str  # user revision comments when rejecting the plan with N
    change_name: str     # asked once at initial planning; kebab-case OpenSpec change name; empty -> falls back to git branch name (sanitized)
    project_dir: str     # target project directory (relative to workspace root) this task's OpenSpec change lives in; reported by analyze_plan's initial-plan call, unchanged across replan/human-revise
