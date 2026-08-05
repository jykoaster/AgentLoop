import re
import time
import os
from pathlib import Path
from datetime import datetime
from ..state import AgentState
from ..claude_runner import call_claude, format_usage_stats
from ..skill_loader import build_skills_block
from ..project_context import build_project_docs_hint, latest_plan_file

# 使用的模型（"haiku" | "sonnet" | "opus" | "fable"，見 claude_runner.MODEL_IDS；
# None 則沿用 claude CLI 本身的預設模型）
_MODEL = "sonnet"

_SYSTEM = """你是一位資深程式碼審查者，負責「Code Review」階段。

請依照下方 code-review skill 的流程進行審查（Standards 與 Spec 兩軸，各自透過平行 sub-agent 產出報告）：

<<CODE_REVIEW_SKILL>>

---

## 審查背景

任務：<<TASK>>

執行計畫（TASK 清單）：
<<PLAN_TEXT>>

執行摘要：
<<EXECUTION_SUMMARY>>

## 依 code-review skill 執行時的具體參數

- **Fixed point**：本次修改尚未 commit，固定點為 `HEAD`（直接執行 `git diff HEAD` 取得完整異動即可，不需詢問使用者）
- **Spec 來源**：<<SPEC_SOURCE>>
- **Standards 來源**：依下方「專案說明檔」判斷本次任務涉及的專案，讀取該專案的 CLAUDE.md / AGENT.md，
  以及其中提及或專案根目錄下的 CODING_STANDARDS.md / CONTRIBUTING.md（若有）作為 Standards 依據；
  若任務同時涉及多個專案（例如前後端），分別讀取

<<PROJECT_CONTEXT>>

## 額外操作指示

1. 確認 TASK 清單完整性：列出未完成的 TASK 編號
2. 依偵測到的專案，讀取其 CLAUDE.md / AGENT.md 中列出的測試指令並實際用 Bash 執行測試
   （若說明檔未列出，探索 package.json / pyproject.toml 等設定檔判斷）；測試失敗計入 Standards 軸的問題
3. 確認相關的商業邏輯說明文件（該專案 docs/ 目錄）是否已依本次修改更新

## 最終輸出格式

先依 code-review skill 輸出 `## Standards` 與 `## Spec` 兩軸報告，接著再附上以下總結（供工作流程解析，必須包含）：
   - 各 TASK 完成狀態（✅ 已完成 / ❌ 未完成）
   - 一行「Ready to merge? Yes」或「Ready to merge? No」結論
   - 若結論為 No，下一行必須輸出審查等級：
     REVIEW_LEVEL: 重寫
     （條件：核心邏輯錯誤、架構根本偏差、多個互相關聯的根本性問題、TASK 大量未完成）
     或
     REVIEW_LEVEL: 修補
     （條件：小 bug、測試失敗、遺漏文件同步、個別 TASK 未完成、小幅修正）

請用繁體中文回答。
"""

_BANNER = "\033[1;33m"
_RED    = "\033[1;31m"
_RESET  = "\033[0m"

_REVIEW_SAVE_DIR = Path(os.path.dirname(__file__)).parent / "docs" / "nodes" / "review"


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

    code_review_skill = build_skills_block(["code-review"])
    if not code_review_skill:
        print(f"{_BANNER}  [Review Agent] 找不到 code-review skill，跳過{_RESET}\n", flush=True)
        return {"review_result": "SKIPPED", "review_level": ""}

    exec_summary = state.get("execution_result", "")
    if len(exec_summary) > 2000:
        exec_summary = exec_summary[-2000:]

    plan_text = "\n".join(
        f"TASK {i+1}: {s}" for i, s in enumerate(state.get("plan", []))
    )

    spec_file = latest_plan_file()
    spec_source = (
        f"{spec_file}（由分析規劃階段依 to-spec 產生，請用 Read 讀取）"
        if spec_file
        else "找不到規格文件，改以上方「審查背景」中的任務描述與 TASK 清單作為 Spec 依據"
    )

    start = time.monotonic()

    try:
        prompt = (
            _SYSTEM
            .replace("<<CODE_REVIEW_SKILL>>", code_review_skill)
            .replace("<<TASK>>", state["task"])
            .replace("<<PLAN_TEXT>>", plan_text)
            .replace("<<EXECUTION_SUMMARY>>", exec_summary)
            .replace("<<SPEC_SOURCE>>", spec_source)
            .replace("<<PROJECT_CONTEXT>>", build_project_docs_hint())
        )
        result = call_claude(prompt, tools="review", timeout=600, model=_MODEL)
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
