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
    change_name: str     # OpenSpec change 名稱（由 branch_name 轉 kebab-case）；任務開始時問一次，全程沿用
    branch_name: str     # 使用者指定的 git 分支（必填）；規劃／執行／審查都在此分支上進行
    project_dir: str     # target project directory (relative to workspace root) this task's OpenSpec change lives in; resolved by analyze_plan before its initial-plan call, unchanged across replan/human-revise
