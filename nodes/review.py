import re
import sys
import time
import os
from pathlib import Path
from datetime import datetime
from ..state import AgentState
from ..claude_runner import call_claude, format_usage_stats
from ..skill_loader import build_skills_block
from ..project_context import build_project_doc_hint_for
from ..git_ops import ensure_on_branch

# 使用的模型（"haiku" | "sonnet" | "opus" | "fable"，見 claude_runner.MODEL_IDS；
# None 則沿用 claude CLI 本身的預設模型）
_MODEL = "sonnet"

_SYSTEM = """你是一位資深程式碼審查者，負責「Code Review」階段。

請依照下方 code-review skill 的流程進行審查（Standards 與 Spec 兩軸，各自透過平行 sub-agent 產出報告）。
fixed point 與 spec 來源見下方「依 code-review skill 執行時的具體參數」，已由本節點固定，不需再自行判斷。

<<CODE_REVIEW_SKILL>>

---

## 審查背景

任務：<<TASK>>

異動與規格都以檔案為準，不要依賴執行階段的文字自述。

## 依 code-review skill 執行時的具體參數（覆蓋 skill 前半）

- **Fixed point**：本次修改尚未 commit，固定點為 `HEAD`。審查前應已在分支 `<<BRANCH_NAME_VALUE>>` 上；
  直接執行 `git diff HEAD` 取得完整異動，不需詢問使用者，也不用三點 diff。
- **Spec 來源**：`<<CHANGE_LOCATION>>`（由分析規劃階段依 OpenSpec 規則產生的 change 資料夾，
  用 Read 讀取其下 proposal.md / tasks.md / specs/**/*.md 取得完整內容（若有 design.md 一併讀取；
  小改動可能沒有此檔，不視為缺漏）；也可用
  `openspec show <<CHANGE_NAME_VALUE>> --json` 快速確認結構。若該 change 已被前一輪迭代
  archive，改讀 `<<PROJECT_DIR_VALUE>>/openspec/specs/` 下對應 domain 的 spec.md）
- **Standards 來源**：依下方「目標專案」讀取其 CLAUDE.md / AGENT.md，以及其中提及或專案根目錄下的
  CODING_STANDARDS.md / CONTRIBUTING.md（若有）作為 Standards 依據
- 其餘仍依 skill：Fowler smell baseline、平行 sub-agent、以 `## Standards` / `## Spec` 並陳報告

<<PROJECT_CONTEXT>>

## 額外操作指示

1. 確認 TASK 清單完整性：Read `<<CHANGE_LOCATION>>/tasks.md`，依其 checkbox 狀態
   （`- [x]` 已完成／`- [ ]` 未完成）逐項核對，列出未完成的 TASK 編號
2. 依目標專案的 CLAUDE.md / AGENT.md 中列出的測試指令並實際用 Bash 執行測試
   （若說明檔未列出，探索 package.json / pyproject.toml 等設定檔判斷）；測試失敗計入 Standards 軸的問題

## 完整性要求（絕對不可省略）

本節點是一次性、非互動的呼叫：這輪回應結束後不會再有下一輪讓你補完，工作流程只會讀這輪回應的
最終文字，不會等你「之後再回來整合」。

- 呼叫 Task 工具做平行 sub-agent 審查、或用 Bash 執行測試，都必須等到真的拿到結果（tool_result）
  後才能繼續下一步；不可以把這些呼叫丟到背景執行、自己先把這輪回應結束
- 不可以用「稍後」「等結果回來後」「等測試跑完再補」這類說法取代真正等待結果——這輪回應只能在
  你已經拿到所有 sub-agent 報告與實際測試結果之後才能結束
- 最終回應**必須**已經包含完整的 `## Standards`／`## Spec` 報告、實際測試結果，以及下方
  「最終輸出格式」要求的所有項目；缺少任何一項都視為還沒做完，必須先完成才能結束回應

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

_MAX_REVIEW_ATTEMPTS = 3

_REVIEW_CONTINUE_PROMPT = (
    "你上一輪的回應在還沒完成前就結束了（缺少完整的 `## Standards` / `## Spec` 報告，"
    "疑似把 sub-agent 或測試丟出去後就提前結束回應，而不是真的等到結果）。"
    "請確認 sub-agent 與測試的結果是否已經拿到——沒拿到就繼續等待，拿到後直接在這一輪把"
    "完整報告（依「最終輸出格式」的所有要求）寫出來，不要再次省略或延後。"
)


def _is_well_formed_review(review_text: str) -> bool:
    """判斷這輪回應是不是真的跑完整個 code-review 流程，而不是中途把 sub-agent／測試丟出去
    後就提前結束這輪回應（例如只寫「等測試結果回來後整合最終報告」）。code-review skill 的
    aggregate 步驟一定會產出這兩個標題，缺一個就代表流程沒跑完。

    這是唯一真正可靠的防線：`_SYSTEM` 裡的「完整性要求」只是自然語言指示，深層多步驟的
    agentic 流程走了幾輪 sub-agent／工具呼叫之後，指示的影響力會被稀釋，不能單獨依賴；
    這裡的檢查不管 Claude 是為什麼提前結束，都能攔下來並要求它接續補完。
    """
    return "## Standards" in review_text and "## Spec" in review_text


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

    project_dir = state.get("project_dir", "")
    change_name = state.get("change_name", "")
    branch_name = state.get("branch_name", "")
    if project_dir and branch_name:
        ok, msg = ensure_on_branch(project_dir, branch_name)
        print(f"{_YELLOW}  [git] {msg}{_RESET}", flush=True)
        if not ok:
            return {
                "status": "error",
                "review_result": f"無法切換到分支 {branch_name}：{msg}",
                "review_level": "",
                "review_blocking": False,
            }

    code_review_skill = build_skills_block(["code-review"])
    if not code_review_skill:
        print(f"{_BANNER}  [Review Agent] 找不到 code-review skill，跳過{_RESET}\n", flush=True)
        return {"review_result": "SKIPPED", "review_level": "", "review_blocking": False}

    change_location = f"{project_dir}/openspec/changes/{change_name}"

    start = time.monotonic()

    try:
        prompt = (
            _SYSTEM
            .replace("<<CODE_REVIEW_SKILL>>", code_review_skill)
            .replace("<<TASK>>", state["task"])
            .replace("<<CHANGE_LOCATION>>", change_location)
            .replace("<<PROJECT_DIR_VALUE>>", project_dir)
            .replace("<<CHANGE_NAME_VALUE>>", change_name)
            .replace("<<BRANCH_NAME_VALUE>>", branch_name)
            .replace("<<PROJECT_CONTEXT>>", build_project_doc_hint_for(project_dir))
        )
        attempt = 0
        session_id = None
        while True:
            attempt += 1
            result = call_claude(prompt, tools="review", timeout=600, model=_MODEL, resume=session_id)
            session_id = result.session_id or session_id
            if result.is_error or _is_well_formed_review(result.text):
                break
            print(
                f"{_YELLOW}  [Review Agent] 回應疑似提前結束（缺少 ## Standards／## Spec），"
                f"第 {attempt} 次，接續同一 session 要求補完{_RESET}\n",
                flush=True,
            )
            if attempt >= _MAX_REVIEW_ATTEMPTS:
                break
            prompt = _REVIEW_CONTINUE_PROMPT
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

    if not _is_well_formed_review(result.text):
        print(
            f"{_RED}  [Review Agent] 連續 {attempt} 次回應都不完整（疑似提前結束），放棄重試{_RESET}\n",
            flush=True,
        )
        return {
            "status": "error",
            "review_result": (
                f"review 連續 {attempt} 次回應不完整（缺少 ## Standards／## Spec，"
                f"疑似把 sub-agent 或測試丟給背景執行就中止回應）：\n\n{result.text}"
            ),
            "review_level": "",
        }

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
