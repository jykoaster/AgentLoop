import re
import time
from pathlib import Path
from datetime import datetime
from ..state import AgentState
from ..claude_runner import call_claude, format_usage_stats, REPO_ROOT
from ..skill_loader import load_skill_file

_SYSTEM = """你是一位資深程式碼審查者，負責「Code Review」階段。

請依照下方 code-reviewer 規格，審查本次修改：

{code_reviewer_spec}

---

## 審查背景

任務：{task}

執行計畫（TASK 清單）：
{plan_text}

執行摘要：
{execution_summary}

## 操作指示

1. 執行 `git diff` 查看實際修改內容
2. 用 Read / Glob / Grep 閱讀相關檔案確認正確性
3. 確認以下各項：
   a. **計畫完整性**：TASK 清單中的每一個 TASK 是否都已完成？列出未完成的 TASK 編號
   b. **程式碼品質**：依照 code-reviewer 規格逐項審查
   c. **文件同步**：tabletop/docs/ 及 tabletop-backend/docs/ 是否已依本次修改更新？
   d. **Migration 審查**：若本次修改涉及資料庫 migration，請到 `tabletop-backend/migrations_extra/` 目錄審查（非 `tabletop-backend/migrations/`）
4. 輸出完整審查報告，必須包含：
   - 各 TASK 完成狀態（✅ 已完成 / ❌ 未完成）
   - 發現問題按等級列出：Critical / Important / Minor
   - 一行「Ready to merge? Yes」或「Ready to merge? No」結論
   - 若結論為 No，下一行必須輸出審查等級：
     REVIEW_LEVEL: 重寫
     （條件：核心邏輯錯誤、架構根本偏差、多個互相關聯的根本性問題、TASK 大量未完成）
     或
     REVIEW_LEVEL: 修補
     （條件：小 bug、型別不符、遺漏 i18n key、個別 TASK 未完成、小幅修正）

請用繁體中文回答。
"""

_BANNER = "\033[1;33m"
_RED    = "\033[1;31m"
_RESET  = "\033[0m"

_REVIEW_SAVE_DIR = Path(REPO_ROOT) / "docs" / "nodes" / "review"


def has_blocking_issues(review_text: str) -> bool:
    """Review 報告結論不是 Yes → 需要重新規劃。"""
    match = re.search(r"Ready to merge\?[^\n]*", review_text, re.IGNORECASE)
    if match:
        return "yes" not in match.group(0).lower()
    return True


def extract_review_level(review_text: str) -> str:
    """從 review 輸出中抽取 REVIEW_LEVEL（重寫 or 修補）。"""
    match = re.search(r"REVIEW_LEVEL:\s*(重寫|修補)", review_text)
    if match:
        return match.group(1)
    return "修補"


def _save_review_report(task: str, review_text: str, review_level: str, iteration: int) -> None:
    try:
        _REVIEW_SAVE_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_str}-iter{iteration}.md"
        filepath = _REVIEW_SAVE_DIR / filename
        content = (
            f"# Review Report — Iteration {iteration}\n\n"
            f"**Task:** {task}\n\n"
            f"**Date:** {date_str}\n\n"
            f"**Review Level:** {review_level}\n\n"
            f"---\n\n"
            f"{review_text}"
        )
        filepath.write_text(content, encoding="utf-8")
        print(f"{_BANNER}  [Review Agent] 已儲存報告：docs/nodes/review/{filename}{_RESET}", flush=True)
    except Exception as e:
        print(f"{_RED}  [Review Agent] 儲存報告失敗：{e}{_RESET}", flush=True)


def review_node(state: AgentState) -> dict:
    if state.get("status") == "error":
        print(f"\n{_BANNER}{'═'*50}\n  [Review Agent] 上游發生錯誤，跳過\n{'═'*50}{_RESET}\n", flush=True)
        return {"review_result": "", "review_level": "", "status": "error"}

    print(f"\n{_BANNER}{'═'*50}\n  [Review Agent] 開始\n{'═'*50}{_RESET}\n", flush=True)

    code_reviewer_spec = load_skill_file("requesting-code-review", "code-reviewer.md")
    if not code_reviewer_spec:
        print(f"{_BANNER}  [Review Agent] 找不到 code-reviewer.md，跳過{_RESET}\n", flush=True)
        return {"review_result": "SKIPPED", "review_level": ""}

    exec_summary = state.get("execution_result", "")
    if len(exec_summary) > 2000:
        exec_summary = exec_summary[-2000:]

    plan_text = "\n".join(
        f"TASK {i+1}: {s}" for i, s in enumerate(state.get("plan", []))
    )

    start = time.monotonic()

    try:
        prompt = _SYSTEM.format(
            code_reviewer_spec=code_reviewer_spec,
            task=state["task"],
            plan_text=plan_text,
            execution_summary=exec_summary,
        )
        result = call_claude(prompt, tools="check", timeout=300)
    except Exception as e:
        print(f"{_RED}  [Review Agent] 發生例外：{e}{_RESET}\n", flush=True)
        return {"status": "error", "review_result": f"Review 發生例外：{e}", "review_level": ""}

    elapsed = time.monotonic() - start

    print(f"\n{_BANNER}{'─'*50}  [Review Agent] 完成  {'─'*50}", flush=True)
    print(format_usage_stats(result, elapsed), flush=True)
    print(f"{'─'*50}{_RESET}\n", flush=True)

    if result.is_error:
        print(f"{_RED}  [Review Agent] Claude 執行失敗：{result.text}{_RESET}\n", flush=True)
        return {"status": "error", "review_result": result.text, "review_level": ""}

    review_text = result.text
    blocking = has_blocking_issues(review_text)
    review_level = extract_review_level(review_text) if blocking else ""

    if blocking:
        _save_review_report(state["task"], review_text, review_level, state.get("iteration", 0))
        print(f"{_BANNER}  [Review Agent] 未通過，審查等級：{review_level}{_RESET}\n", flush=True)
    else:
        print(f"{_BANNER}  [Review Agent] 通過，直接前往 Check{_RESET}\n", flush=True)

    return {
        "review_result": review_text,
        "review_level": review_level,
    }
