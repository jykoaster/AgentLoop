import re
import sys
import time
import os
from pathlib import Path
from datetime import datetime
from ..state import AgentState
from ..claude_runner import call_claude, format_usage_stats
from ..skill_loader import build_skills_block
from ..project_context import build_project_docs_hint

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
- **Spec 來源**：`<<CHANGE_LOCATION>>`（由分析規劃階段依 OpenSpec 規則產生的 change 資料夾，
  用 Read 讀取其下 proposal.md / design.md / tasks.md / specs/**/*.md 取得完整內容；也可用
  `openspec show <<CHANGE_NAME_VALUE>> --json` 快速確認結構。若該 change 已被前一輪迭代
  archive，改讀 `<<PROJECT_DIR_VALUE>>/openspec/specs/` 下對應 domain 的 spec.md）
- **Standards 來源**：依下方「專案說明檔」判斷本次任務涉及的專案，讀取該專案的 CLAUDE.md / AGENT.md，
  以及其中提及或專案根目錄下的 CODING_STANDARDS.md / CONTRIBUTING.md（若有）作為 Standards 依據；
  若任務同時涉及多個專案（例如前後端），分別讀取

<<PROJECT_CONTEXT>>

## 額外操作指示

1. 確認 TASK 清單完整性：Read `<<CHANGE_LOCATION>>/tasks.md`，依其 checkbox 狀態
   （`- [x]` 已完成／`- [ ]` 未完成）逐項核對，列出未完成的 TASK 編號
2. 依偵測到的專案，讀取其 CLAUDE.md / AGENT.md 中列出的測試指令並實際用 Bash 執行測試
   （若說明檔未列出，探索 package.json / pyproject.toml 等設定檔判斷）；測試失敗計入 Standards 軸的問題
3. 若該任務所屬專案的 CLAUDE.md / AGENT.md（或其他說明檔）要求同步維護 docs/ 下的商業邏輯說明文件，
   確認是否已依本次修改更新；說明檔未提及此類慣例時，不需要求有文件變更

## 最終輸出格式

先依 code-review skill 輸出 `## Standards` 與 `## Spec` 兩軸報告，接著再附上以下總結（供工作流程解析，必須包含）：
   - 各 TASK 完成狀態（✅ 已完成 / ❌ 未完成）
   - 一行「Ready to merge? Yes」或「Ready to merge? No」結論
     - **No** 僅限「嚴重影響功能」的問題：核心邏輯錯誤、功能無法正常運作、資料損毀或資安風險、
       架構根本偏差、多個互相關聯的根本性問題、TASK 大量未完成
     - 其餘問題（風格、可讀性、效能微調、小幅優化、非阻塞的小瑕疵等**不影響功能正確性**者）
       即使有修改建議，仍回答 **Yes**，改用下方 SUGGESTION 標記逐條列出，交由人工決定要修哪幾條
   - 若結論為 No，下一行必須輸出審查等級：
     REVIEW_LEVEL: 重寫
     （條件：核心邏輯錯誤、架構根本偏差、多個互相關聯的根本性問題、TASK 大量未完成）
     或
     REVIEW_LEVEL: 修補
     （條件：小 bug、測試失敗、遺漏文件同步、個別 TASK 未完成、小幅修正）
   - 若結論為 Yes 但仍有不影響功能的修改建議，附上一個 `## 建議事項（不影響功能）` 小節，
     每條建議獨立一行、依序編號，格式必須是：
     SUGGESTION 1: <建議內容與理由>
     SUGGESTION 2: <建議內容與理由>
     ...
     （沒有任何建議時，不需要輸出這個小節）

請用繁體中文回答。
"""

_BANNER = "\033[1;33m"
_YELLOW = "\033[1;33m"
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


def extract_suggestions(review_text: str) -> list[str]:
    """從 review 輸出中抽取不影響功能的建議事項清單（SUGGESTION n: ...），依序排列。"""
    return re.findall(r"SUGGESTION\s*\d+:\s*(.+)", review_text)


def _parse_suggestion_selection(answer: str, count: int) -> list[int]:
    """解析人工輸入的建議編號選擇：'all' 全選、逗號分隔編號、空白則不選任何一條。"""
    answer = answer.strip().lower()
    if not answer:
        return []
    if answer == "all":
        return list(range(1, count + 1))
    selected = set()
    for token in answer.split(","):
        token = token.strip()
        if token.isdigit():
            n = int(token)
            if 1 <= n <= count:
                selected.add(n)
    return sorted(selected)


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
        return {"review_result": "", "review_level": "", "review_blocking": False, "status": "error"}

    print(f"\n{_BANNER}{'═'*50}\n  [Review Agent] 開始\n{'═'*50}{_RESET}\n", flush=True)

    code_review_skill = build_skills_block(["code-review"])
    if not code_review_skill:
        print(f"{_BANNER}  [Review Agent] 找不到 code-review skill，跳過{_RESET}\n", flush=True)
        return {"review_result": "SKIPPED", "review_level": "", "review_blocking": False}

    exec_summary = state.get("execution_result", "")
    if len(exec_summary) > 2000:
        exec_summary = exec_summary[-2000:]

    plan_text = "\n".join(
        f"TASK {i+1}: {s}" for i, s in enumerate(state.get("plan", []))
    )

    project_dir = state.get("project_dir", "")
    change_name = state.get("change_name", "")
    change_location = f"{project_dir}/openspec/changes/{change_name}"

    start = time.monotonic()

    try:
        prompt = (
            _SYSTEM
            .replace("<<CODE_REVIEW_SKILL>>", code_review_skill)
            .replace("<<TASK>>", state["task"])
            .replace("<<PLAN_TEXT>>", plan_text)
            .replace("<<EXECUTION_SUMMARY>>", exec_summary)
            .replace("<<CHANGE_LOCATION>>", change_location)
            .replace("<<PROJECT_DIR_VALUE>>", project_dir)
            .replace("<<CHANGE_NAME_VALUE>>", change_name)
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
    iteration = state.get("iteration", 0)

    if has_blocking_issues(review_text):
        # 嚴重影響功能的問題：維持原本嚴格行為，不詢問人工，直接產出報告並重新規劃
        review_level = extract_review_level(review_text)
        _save_review_report(state["task"], review_text, review_level, iteration)
        print(f"{_BANNER}  [Review Agent] 發現嚴重影響功能的問題，審查等級：{review_level}{_RESET}\n", flush=True)
        return {"review_result": review_text, "review_level": review_level, "review_blocking": True}

    suggestions = extract_suggestions(review_text)
    if not suggestions:
        print(f"{_BANNER}  [Review Agent] 通過，無嚴重問題亦無其他建議，直接前往 Check{_RESET}\n", flush=True)
        return {"review_result": review_text, "review_level": "", "review_blocking": False}

    print(f"\n{_BANNER}{'─'*50}", flush=True)
    print("  [Review Agent] 無嚴重影響功能的問題，但有以下修改建議：", flush=True)
    print(f"{'─'*50}{_RESET}", flush=True)
    for i, s in enumerate(suggestions, 1):
        print(f"  {i}. {s}", flush=True)
    print(f"{_BANNER}{'─'*50}{_RESET}\n", flush=True)

    if not sys.stdin.isatty():
        print(f"{_YELLOW}  [Review Agent] 非互動式環境，預設不修改任何建議，直接前往 Check{_RESET}\n", flush=True)
        selected = []
    else:
        try:
            answer = input(
                f"{_YELLOW}  請輸入要修改的建議編號（例如 1,3；all=全部；直接 Enter=不修改）：{_RESET}"
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{_YELLOW}  [Review Agent] 已取消，預設不修改任何建議{_RESET}\n", flush=True)
            answer = ""
        selected = _parse_suggestion_selection(answer, len(suggestions))

    if not selected:
        print(f"{_BANNER}  [Review Agent] 維持現狀，直接前往 Check{_RESET}\n", flush=True)
        return {"review_result": review_text, "review_level": "", "review_blocking": False}

    selected_block = "\n".join(f"SUGGESTION {i}: {suggestions[i - 1]}" for i in selected)
    review_result = (
        f"{review_text}\n\n---\n\n## 人工確認：選定修改的建議事項\n\n"
        f"以下為經人工確認、需要處理的建議（其餘未選中的建議維持現狀，不需修改）：\n\n"
        f"{selected_block}"
    )
    _save_review_report(state["task"], review_result, "修補", iteration)
    print(f"{_BANNER}  [Review Agent] 已選定 {len(selected)} 項建議進行修補，重新規劃{_RESET}\n", flush=True)
    return {"review_result": review_result, "review_level": "修補", "review_blocking": True}
