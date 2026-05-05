import re
import time
from ..state import AgentState
from ..claude_runner import call_claude, format_usage_stats, REPO_ROOT
from ..skill_loader import build_skills_block

_SKILLS = [
    "writing-plans",
    "architecture-patterns",
    "architecture-decision-records",
    "next-best-practices",
    "test-driven-development",
]

_SYSTEM_INITIAL = """你是一位資深全端工程師，負責「分析與規劃」階段。

本專案是一個 monorepo：
- tabletop/         → Next.js 15 前端（App Router、TypeScript、Tailwind CSS 4）
- tabletop-backend/ → Python FastAPI 後端（SQLModel、Alembic）

## 執行步驟

1. 用 Read/Glob/Grep 閱讀相關程式碼，找出需修改的位置與潛在衝突
2. 依照 writing-plans skill 的格式，撰寫完整的繁體中文實作計畫文件
3. 用 Write 工具將計畫存到 docs/superpowers/plans/YYYY-MM-DD-<feature>.md
   - 日期使用今天的日期；feature 為任務的簡短英文描述（kebab-case）
4. 存檔後，在最終輸出中附上以下摘要（供後續 Agent 使用）：

## 分析
[2-5 行摘要：需求、涉及檔案、潛在問題]

## 計畫
TASK 1: [操作] [路徑] — [說明]
TASK 2: [操作] [路徑] — [說明]
...

規則：
- 每個 TASK 對應計畫文件中的一個可執行步驟，讓執行 Agent 可逐一嚴格處理
- 最後一個 TASK 必須是：更新 tabletop/docs/ 及 tabletop-backend/docs/ 中相關的商業邏輯說明文件
- 說明文件應涵蓋：功能說明、資料流、API 規格、業務規則

請用繁體中文回答。
"""

_SYSTEM_REPLAN = """你是一位資深全端工程師，負責「重新分析與規劃」階段。

本專案是一個 monorepo：
- tabletop/         → Next.js 15 前端（App Router、TypeScript、Tailwind CSS 4）
- tabletop-backend/ → Python FastAPI 後端（SQLModel、Alembic）

## 背景

上一輪執行被審查標記為需要修正。審查結果如下：

{review_context}

審查等級：{review_level}

## 根據審查等級採取行動

### 若為「重寫」：
1. **先執行 rollback**：用 Bash 執行 `git stash` 還原所有未提交的修改
   - 若 git stash 失敗或沒有 stash 可用，嘗試 `git checkout -- .` 還原已修改的追蹤檔案
   - 確認 rollback 完成後再繼續
2. 重新閱讀現有程式碼，從頭制定全新計畫
3. 刪除舊的計畫文件並建立新的計畫文件

### 若為「修補」：
1. 不需要 rollback，保留已完成的修改
2. 閱讀現有程式碼，精確定位需要修正的地方
3. 更新計畫文件，在原有基礎上增加修補步驟

## 輸出格式

依照 writing-plans skill 的格式撰寫更新後的計畫文件，並存到 docs/superpowers/plans/ 目錄下。

最終輸出：

## 分析
[2-5 行摘要：問題根因、涉及檔案、修正方向]

## 計畫
TASK 1: [操作] [路徑] — [說明]
TASK 2: [操作] [路徑] — [說明]
...

規則：
- 每個 TASK 對應計畫文件中的一個可執行步驟，讓執行 Agent 可逐一嚴格處理
- 最後一個 TASK 必須是：更新 tabletop/docs/ 及 tabletop-backend/docs/ 中相關的商業邏輯說明文件

請用繁體中文回答。
"""

_BANNER = "\033[1;34m"
_RED    = "\033[1;31m"
_RESET  = "\033[0m"


def analyze_plan_node(state: AgentState) -> dict:
    review_result = state.get("review_result", "")
    review_level = state.get("review_level", "")
    is_replan = bool(review_result)

    if is_replan:
        label = f"重新規劃（{review_level or '修補'}）"
        tools = "full"  # needs Bash for rollback on 重寫
        model = "sonnet"
    else:
        label = "初始規劃"
        tools = "plan"
        model = "sonnet"

    print(f"\n{_BANNER}{'═'*50}\n  [分析+規劃 Agent] 開始 — {label}\n{'═'*50}{_RESET}\n", flush=True)

    start = time.monotonic()

    try:
        skills_block = build_skills_block(_SKILLS)

        if is_replan:
            review_ctx = review_result
            if len(review_ctx) > 3000:
                review_ctx = review_ctx[-3000:]
            system = _SYSTEM_REPLAN.format(
                review_context=review_ctx,
                review_level=review_level or "修補",
            )
        else:
            system = _SYSTEM_INITIAL

        prompt = f"{system}\n\n{skills_block}\n\n任務：{state['task']}"
        result = call_claude(prompt, tools=tools, model=model, timeout=300)
    except Exception as e:
        print(f"{_RED}  [分析+規劃 Agent] 發生例外：{e}{_RESET}\n", flush=True)
        return {"status": "error", "analysis": f"分析階段發生例外：{e}", "plan": []}

    elapsed = time.monotonic() - start

    print(f"\n{_BANNER}{'─'*50}  [分析+規劃 Agent] 完成  {'─'*50}", flush=True)
    print(format_usage_stats(result, elapsed), flush=True)
    print(f"{'─'*50}{_RESET}\n", flush=True)

    if result.is_error:
        print(f"{_RED}  [分析+規劃 Agent] Claude 執行失敗：{result.text}{_RESET}\n", flush=True)
        return {"status": "error", "analysis": result.text, "plan": []}

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
    }
