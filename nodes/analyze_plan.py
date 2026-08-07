import re
import sys
import time
from datetime import datetime
from ..state import AgentState
from ..claude_runner import call_claude, format_usage_stats, QUESTION_MARKER
from ..skill_loader import build_skills_block
from ..project_context import build_project_docs_hint

_SKILLS = [
    "grill-with-docs",
    "grilling",
    "domain-modeling",
    "to-spec",
    "tdd",
]

# 使用的模型（"haiku" | "sonnet" | "opus" | "fable"，見 claude_runner.MODEL_IDS）
_MODEL = "opus"

_QUESTION_PROTOCOL = """## 提問規則（grill-with-docs 互動式釐清）

依照 grill-with-docs：以 grilling 對本任務逐一提問、以 domain-modeling 即時記錄詞彙與 ADR。

- 可透過 Read/Glob/Grep 自行查證的「事實」不要拿來提問；只對真正需要使用者決策的事項提問
- 一次只問一個問題
- 每個問題附上數字選項（比照 grill-with-docs 互動時的做法），窮舉合理答案（至少 2 個），並在你建議的選項後加註「（建議）」
- 若需要提問，該輪回應「只能」輸出下列格式，不得包含其他文字：即使你已經做完部分分析、找到相關檔案、或想好了初步計畫草稿，只要本輪要提問，也不可以先把這些內容輸出出來，必須整輪只有下列格式：

QUESTION: <你的問題>
1. <選項一>（建議）
2. <選項二>
3. <選項三，視需要增減>

- 使用者可能回覆選項編號（例如「1」）或自訂文字，兩者都視為有效答案並據以判斷後續動作
- 輸出後立即結束本輪回應，等待使用者回覆後再繼續
- 當所有需要釐清的決策都已有共識，才可以繼續進行 to-spec 與最終輸出（此後不得再輸出 QUESTION）"""

_REVIEW_QUESTION_PROTOCOL = """## 提問規則（針對 review 結果 grill）

依照 grilling：針對審查結果（Review Result）中每一個被標記的問題點逐一提出質疑性問題，確認：
- 該問題點的判斷是否成立、影響範圍是否如審查所述
- 若修正方向有多種可能取捨，請使用者拍板

- 可透過 Read/Glob/Grep 自行查證的「事實」不要拿來提問；只對真正需要使用者決策的事項提問
- 一次只問一個問題
- 每個問題附上數字選項，窮舉合理答案（至少 2 個），並在你建議的選項後加註「（建議）」
- 若需要提問，該輪回應「只能」輸出下列格式，不得包含其他文字：即使你已經做完部分分析、找到相關檔案、或想好了初步計畫草稿，只要本輪要提問，也不可以先把這些內容輸出出來，必須整輪只有下列格式：

QUESTION: <你的問題>
1. <選項一>（建議）
2. <選項二>
3. <選項三，視需要增減>

- 使用者可能回覆選項編號（例如「1」）或自訂文字，兩者都視為有效答案並據以判斷後續動作
- 輸出後立即結束本輪回應，等待使用者回覆後再繼續
- 當 review 標記的每個問題點都已確認完畢，才可以繼續進行後續流程與最終輸出（此後不得再輸出 QUESTION）"""

_SPEC_TEMPLATE = """```markdown
# [Feature/Fix Name] 需求與設計規格書

**Date**: <<TODAY>>
**Scope**: `受影響的目錄/檔案結構`

## Problem Statement
<!-- 說明現有系統的痛點、Bug 或新需求背景，明確列出要解決的問題項目 -->

## Solution
<!-- 高階解決方案概述，包含驗證規則調整、UI 變更、錯誤處理機制等 -->

## User Stories
<!-- 條列各角色（使用者、系統管理員等）的操作情境與期望結果 -->

## Implementation Decisions
<!-- 詳細的技術決策與架構邏輯 -->
### 影響模組
- `受影響檔案 A`: 具體修改內容
- `受影響檔案 B`: 具體修改內容

### 關鍵機制與流程
- **單一真理來源 (SOT)**: 前端 UI 與 Validator 的分工
- **錯誤處理流 (Error Handling Flow)**: API 錯誤與前端 Validation 的分流邏輯
- **i18n 多語系策略**: 新增/修改 key 的管理方式

## Testing Strategy
<!-- 定義如何驗證此變更，不包含實際執行 Log -->
### Seam（測試接縫）
- **首選接縫**: 測試對象與測試方法（如單元測試）
- **次要接縫**: Vue Test Utils / Component 層級驗證

### 測試案例矩陣（Test Matrix）
| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| 案例 1 | ... | ... |

## Out of Scope
<!-- 明確指出本次開發「不做」的事項，避免範疇蔓延 -->

## Technical Debt & Follow-up Notes
<!-- 需追蹤的技術債（如 ESLint 警告、Google Sheet 同步等） -->
```

**章節結構規則：**
- 上方 `#`/`##`/`###` 標題結構（含「影響模組」「關鍵機制與流程」「Seam（測試接縫）」「測試案例矩陣（Test Matrix）」四個固定小節）**必須完整保留**，不可增減或改名
- 每個章節（含四個固定小節）都必須填寫內容；某章節在本次任務沒有內容時，仍須保留該標題並填寫「無」，不可留白或整個刪除
- 標題底下的 `<!-- -->` 為填寫指引、非文件正式內容；「SOT / Error Handling Flow / i18n 多語系策略」「首選/次要接縫」「案例 1」與「受影響檔案 A/B」等**都只是範例內容**，用來示範這個小節通常會寫什麼——實際要寫的是本次任務真正涉及的模組、機制、測試情境，不是照抄範例文字"""

_SYSTEM_INITIAL = f"""你是一位資深全端工程師，負責「分析與規劃」階段。

<<PROJECT_CONTEXT>>

## 執行步驟

1. 用 Read/Glob/Grep 閱讀相關程式碼，找出需修改的位置與潛在衝突
2. 依 grill-with-docs 對本任務進行互動式釐清（見下方「提問規則」），過程中依 domain-modeling 規則即時更新 CONTEXT.md / docs/adr/
3. 共識達成後，依 to-spec 的探索流程整理規格文件，但規格文件的**範本與檔名規則改用下方指定版本**（覆蓋 to-spec 原本的範本與檔名慣例）：
   - 探索程式碼以確認測試 seam，優先使用既有 seam、避免新增
   - 本專案未串接 issue tracker，略過 to-spec 中「發布並標記 triage label」的步驟
   - 依下方「規格文件範本」撰寫
   - 用 Write 工具存到 docs/superpowers/plans/<filename>.md：
     - 若使用者於任務開始時提供了自訂檔名，本次為：<<PLAN_FILENAME_VALUE>>，直接以此作為 <filename>（不含副檔名）
     - 若上方顯示為空（使用者未提供自訂檔名），改用 Bash 執行 `git branch --show-current`（或 `git rev-parse --abbrev-ref HEAD`）取得本次修改所屬目標專案的目前 git branch 名稱作為 <filename>；若含 `/` 等不適合檔名的字元，替換為 `-`

## 規格文件範本

{_SPEC_TEMPLATE}

## 執行步驟（續）

4. 存檔後，將規格轉譯為可執行 TASK 清單，在最終輸出中附上以下摘要（供後續 Agent 使用）：

## 分析
[2-5 行摘要：需求、涉及檔案、潛在問題]

## 計畫
TASK 1: [操作] [路徑] — [說明]
TASK 2: [操作] [路徑] — [說明]
...

規則：
- 每個 TASK 對應規格文件中的一個可執行步驟，讓執行 Agent 可逐一嚴格處理
- 涉及新增或修改行為的 TASK，須額外安排一個對應的「撰寫／更新測試」TASK（優先在既有測試 seam 上以 tdd skill 的紅-綠循環進行）；純文件、設定調整或不改變行為的重構可不需要
- 是否需要新增「更新文件」TASK，依該任務所屬專案的 CLAUDE.md / AGENT.md（或其他說明檔）判斷：
  若說明檔要求同步維護 docs/ 下的商業邏輯說明文件，安排對應的文件更新 TASK（通常放在最後，涵蓋範圍依說明檔慣例）；
  說明檔未提及此類慣例時，不強制新增文件 TASK

{_QUESTION_PROTOCOL}

請用繁體中文回答。
"""

_SYSTEM_REPLAN = f"""你是一位資深全端工程師，負責「重新分析與規劃」階段。

<<PROJECT_CONTEXT>>

## 背景

上一輪執行被審查標記為需要修正。審查結果如下：

<<REVIEW_CONTEXT>>

審查等級：<<REVIEW_LEVEL>>

## 根據審查等級採取行動

### 若為「重寫」：
1. **先執行 rollback**：用 Bash 執行 `git stash` 還原所有未提交的修改
   - 若 git stash 失敗或沒有 stash 可用，嘗試 `git checkout -- .` 還原已修改的追蹤檔案
   - 確認 rollback 完成後再繼續
2. 重新閱讀現有程式碼；依下方「提問規則」針對審查結果逐點 grill 確認，不需重新進行完整的 grill-with-docs 釐清或文件同步
3. 依 to-spec 的探索流程、下方「規格文件範本」重新撰寫規格文件，取代 `docs/superpowers/plans/` 下的舊規格文件——
   **檔名維持不變**（沿用舊規格文件的檔名，不重新命名）；略過發布 issue tracker 的步驟，改用 Write 存檔

### 若為「修補」：
1. 不需要 rollback，保留已完成的修改
2. 閱讀現有程式碼，精確定位需要修正的地方；依下方「提問規則」針對審查結果逐點 grill 確認
3. 依下方「規格文件範本」更新既有規格文件的相關段落（不必整份重寫，但維持範本的章節結構，不可整段刪除某章節）

## 規格文件範本

{_SPEC_TEMPLATE}

## 輸出格式

最終輸出：

## 分析
[2-5 行摘要：問題根因、涉及檔案、修正方向]

## 計畫
TASK 1: [操作] [路徑] — [說明]
TASK 2: [操作] [路徑] — [說明]
...

規則：
- 每個 TASK 對應規格文件中的一個可執行步驟，讓執行 Agent 可逐一嚴格處理
- 涉及新增或修改行為的 TASK，須額外安排一個對應的「撰寫／更新測試」TASK（優先在既有測試 seam 上以 tdd skill 的紅-綠循環進行）；純文件、設定調整或不改變行為的重構可不需要
- 是否需要新增「更新文件」TASK，依該任務所屬專案的 CLAUDE.md / AGENT.md（或其他說明檔）判斷：
  若說明檔要求同步維護 docs/ 下的商業邏輯說明文件，安排對應的文件更新 TASK（通常放在最後）；
  說明檔未提及此類慣例時，不強制新增文件 TASK

{_REVIEW_QUESTION_PROTOCOL}

請用繁體中文回答。
"""

_SYSTEM_HUMAN_REVISE = f"""你是一位資深全端工程師，負責「根據人工意見調整規劃」階段。

<<PROJECT_CONTEXT>>

## 背景

你先前已提出一份規格與計畫，但使用者在審閱後提出了以下修改意見：

<<HUMAN_FEEDBACK>>

## 執行步驟

1. 仔細理解使用者的修改意見；若意見不夠明確，依下方「提問規則」提問確認，不要自行臆測
2. 視需要用 Read/Glob/Grep 重新閱讀相關程式碼
3. 若修改意見牽涉到詞彙或架構決策的變更，依 domain-modeling 更新 CONTEXT.md / docs/adr/
4. 依下方「規格文件範本」更新 docs/superpowers/plans/ 下的規格文件——**檔名維持不變**（不重新命名），
   維持範本的章節結構，不可整段刪除某章節
5. 存檔後，在最終輸出中附上調整後的摘要與 TASK 清單

## 規格文件範本

{_SPEC_TEMPLATE}

## 輸出格式

## 分析
[2-5 行摘要：根據人工意見的修正方向與涉及檔案]

## 計畫
TASK 1: [操作] [路徑] — [說明]
TASK 2: [操作] [路徑] — [說明]
...

規則：
- 每個 TASK 對應規格文件中的一個可執行步驟，讓執行 Agent 可逐一嚴格處理
- 涉及新增或修改行為的 TASK，須額外安排一個對應的「撰寫／更新測試」TASK（優先在既有測試 seam 上以 tdd skill 的紅-綠循環進行）；純文件、設定調整或不改變行為的重構可不需要
- 是否需要新增「更新文件」TASK，依該任務所屬專案的 CLAUDE.md / AGENT.md（或其他說明檔）判斷：
  若說明檔要求同步維護 docs/ 下的商業邏輯說明文件，安排對應的文件更新 TASK（通常放在最後）；
  說明檔未提及此類慣例時，不強制新增文件 TASK

{_QUESTION_PROTOCOL}

請用繁體中文回答。
"""

_BANNER = "\033[1;34m"
_RED    = "\033[1;31m"
_YELLOW = "\033[1;33m"
_RESET  = "\033[0m"

_MAX_QUESTIONS = 15


_QUESTION_LINE_RE = re.compile(r"^\s*" + re.escape(QUESTION_MARKER), re.MULTILINE)


def _is_question(text: str) -> bool:
    """判斷本輪回應是否包含提問。

    不能只用 startswith 判斷：模型有時會違反「只能輸出 QUESTION 格式」的規則，
    在 QUESTION 前面多輸出分析／計畫草稿等文字。只要文字中任一行以
    QUESTION: 開頭，就視為提問，避免漏判導致跳過互動式選項、直接進入
    human_confirm 的 y/N 關卡。
    """
    return bool(_QUESTION_LINE_RE.search(text))


def _run_with_grilling(prompt: str, tools: str, model: str, timeout: int):
    """執行 call_claude；遇到 QUESTION: 提問時（已由 claude_runner 即時印出）
    立即等待使用者回覆，並以 --resume 延續同一 session 把回答帶回去。
    """
    session_id = None
    rounds = 0
    while True:
        result = call_claude(prompt, tools=tools, model=model, timeout=timeout, resume=session_id)
        session_id = result.session_id or session_id

        if result.is_error or not _is_question(result.text):
            return result

        rounds += 1
        if rounds > _MAX_QUESTIONS:
            print(
                f"{_RED}  [分析+規劃 Agent] 提問次數過多（>{_MAX_QUESTIONS}），中止互動式釐清{_RESET}\n",
                flush=True,
            )
            return result

        if not sys.stdin.isatty():
            print(
                f"{_YELLOW}  [分析+規劃 Agent] 非互動式環境，無法提問，採用建議答案繼續{_RESET}\n",
                flush=True,
            )
            prompt = "請採用你自己建議的答案，並繼續下一個問題或流程。"
            continue

        try:
            answer = input(f"{_YELLOW}  > {_RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{_YELLOW}  [分析+規劃 Agent] 已中止提問，採用建議答案繼續{_RESET}\n", flush=True)
            answer = ""

        prompt = answer if answer else "請採用你自己建議的答案，並繼續下一個問題或流程。"


def _ask_plan_filename() -> str:
    """任務開始時（僅初始規劃）詢問使用者規劃文件自訂檔名，留空則由 Claude 改用 git branch 名稱。
    非互動式環境或使用者直接按 Enter／中止時，留空繼續。
    """
    print(f"\n{_YELLOW}  [分析+規劃 Agent] 請輸入規劃文件檔名（不含副檔名，可直接按 Enter 改用目前 git branch 名稱）：{_RESET}", flush=True)
    if not sys.stdin.isatty():
        print(f"{_YELLOW}  非互動式環境，規劃文件檔名留空，改用 branch name{_RESET}\n", flush=True)
        return ""
    try:
        answer = input(f"{_YELLOW}  > {_RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{_YELLOW}  已跳過，規劃文件檔名留空，改用 branch name{_RESET}\n", flush=True)
        return ""
    return answer


def analyze_plan_node(state: AgentState) -> dict:
    review_result = state.get("review_result", "")
    review_level = state.get("review_level", "")
    human_feedback = state.get("human_feedback", "")
    is_replan = bool(review_result)
    is_human_revise = bool(human_feedback) and not is_replan

    plan_filename = state.get("plan_filename", "")

    model = _MODEL
    if is_replan:
        label = f"重新規劃（{review_level or '修補'}）"
        tools = "full"  # needs Bash for rollback on 重寫
    elif is_human_revise:
        label = "依人工意見調整計畫"
        tools = "plan"
    else:
        label = "初始規劃"
        tools = "plan"
        if not plan_filename:
            plan_filename = _ask_plan_filename()

    print(f"\n{_BANNER}{'═'*50}\n  [分析+規劃 Agent] 開始 — {label}\n{'═'*50}{_RESET}\n", flush=True)

    start = time.monotonic()

    try:
        skills_block = build_skills_block(_SKILLS)

        project_context = build_project_docs_hint()

        today = datetime.now().strftime("%Y-%m-%d")

        if is_replan:
            review_ctx = review_result
            if len(review_ctx) > 3000:
                review_ctx = review_ctx[-3000:]
            system = (
                _SYSTEM_REPLAN
                .replace("<<PROJECT_CONTEXT>>", project_context)
                .replace("<<REVIEW_CONTEXT>>", review_ctx)
                .replace("<<REVIEW_LEVEL>>", review_level or "修補")
                .replace("<<TODAY>>", today)
            )
        elif is_human_revise:
            system = (
                _SYSTEM_HUMAN_REVISE
                .replace("<<PROJECT_CONTEXT>>", project_context)
                .replace("<<HUMAN_FEEDBACK>>", human_feedback)
                .replace("<<TODAY>>", today)
            )
        else:
            system = (
                _SYSTEM_INITIAL
                .replace("<<PROJECT_CONTEXT>>", project_context)
                .replace("<<PLAN_FILENAME_VALUE>>", plan_filename or "（未提供，留空）")
                .replace("<<TODAY>>", today)
            )

        prompt = f"{system}\n\n{skills_block}\n\n任務：{state['task']}"
        result = _run_with_grilling(prompt, tools=tools, model=model, timeout=300)
    except Exception as e:
        print(f"{_RED}  [分析+規劃 Agent] 發生例外：{e}{_RESET}\n", flush=True)
        return {"status": "error", "analysis": f"分析階段發生例外：{e}", "plan": [], "plan_filename": plan_filename}

    elapsed = time.monotonic() - start

    print(f"\n{_BANNER}{'─'*50}  [分析+規劃 Agent] 完成  {'─'*50}", flush=True)
    print(format_usage_stats(result, elapsed), flush=True)
    print(f"{'─'*50}{_RESET}\n", flush=True)

    if result.is_error:
        print(f"{_RED}  [分析+規劃 Agent] Claude 執行失敗：{result.text}{_RESET}\n", flush=True)
        return {"status": "error", "analysis": result.text, "plan": [], "plan_filename": plan_filename}

    raw = result.text
    tasks = re.findall(r"TASK\s*\d+:\s*(.+)", raw)
    if not tasks:
        tasks = re.findall(r"STEP\s*\d+:\s*(.+)", raw)
    plan = tasks if tasks else [raw]

    analysis_match = re.search(r"## 分析\n([\s\S]*?)(?=## 計畫|$)", raw)
    analysis = analysis_match.group(1).strip() if analysis_match else raw[:500]

    return {
        "analysis": analysis,
        "plan": plan,
        "status": "pending",
        "review_result": "",
        "review_level": "",
        "review_blocking": False,
        "human_feedback": "",
        "plan_filename": plan_filename,
    }
