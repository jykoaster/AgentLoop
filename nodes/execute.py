import os
import time
from ..core import AgentState, take_session, store_session
from ..lib import (
    call_claude, call_resuming, format_usage_stats, build_skills_block,
    build_project_doc_hint_for, ensure_on_branch, is_usage_limit_error,
    LANGUAGE_POLICY, REPO_ROOT,
)

_SKILLS = [
    "tdd",
]

# 使用的模型（"haiku" | "sonnet" | "opus" | "fable"，見 claude_runner.MODEL_IDS；
# None 則沿用 claude CLI 本身的預設模型）
_MODEL = "sonnet"

_TIMEOUT = 900

# 中斷 session 插槽的 owner 名稱（見 core/session.py）
_SESSION_KEY = "execute"

_SYSTEM = f"""你是一位資深全端工程師，負責「執行」階段。

## 執行前準備（必須完成）

在開始任何修改前，必須先：
1. 用 Read 讀取 `<<CHANGE_LOCATION>>` 下的 proposal.md、specs/**/*.md、tasks.md
   （若有 design.md 一併讀取；小改動可能沒有此檔，不視為缺漏）。
2. 依下方「目標專案」讀取其 CLAUDE.md / AGENT.md，了解該專案的架構、指令（測試、lint、build 等）、
   目錄慣例、程式碼規範，以及**技術棧**；找不到說明檔則自行用 Read/Glob/Grep 探索程式碼並比對現有風格
3. 依偵測到的技術棧，自行從你可用的 skills 中挑選並使用適合的其他 skill
   （例如 Vue 專案適用 vue-best-practices、Nuxt + Vitest 專案適用 nuxt-vitest-msw
   等）——不要假設任何特定技術棧，依實際偵測結果選用。tdd 已固定提供給你，見下方說明
4. 若該專案 docs/ 目錄存在，讀取其下所有現有文件，了解商業邏輯說明；docs/ 目錄不存在時不需自行建立

<<PROJECT_CONTEXT>>

## 執行方式

依 `<<CHANGE_LOCATION>>/tasks.md` 的順序**嚴格依序**處理（不重排）：
- `- [ ]` 的 TASK 必須執行，不得跳過
- `- [x]` 的 TASK **預設略過，不要重做**。略過前先用 Read/Grep 核對該 TASK 聲稱完成的檔案是否真的在磁碟上、內容是否對得上規格；對得上就略過，對不上（checkbox 已勾但實作缺漏或不完整）才重做該項並維持勾選。這個規則在全新 session 與接回中斷 session 都適用——不要因為 prompt 說「完成所有修改」就把已完成的項目重做一遍
- 用 Read 工具讀取現有內容，再用 Write/Edit 工具寫入修改
- 用 Bash 執行必要指令
- 程式碼風格、命名慣例、目錄結構、i18n／型別／auto-generated 檔案等規則，一律依照該專案
  CLAUDE.md / AGENT.md 的說明；說明檔未涵蓋的細節，比對該專案現有程式碼風格
- 每完成一個 TASK，立即用 Edit 把 `<<CHANGE_LOCATION>>/tasks.md` 裡對應的 checkbox 從
  `- [ ]` 改成 `- [x]`，讓這份檔案即時反映實際完成進度（後續 Review Agent 會依此核對）
- 若 tasks.md 中出現「撰寫／更新測試」的 TASK，**必須**依 tdd skill 的紅-綠循環執行該 TASK：
  先寫一個會失敗的測試，再寫最小可行的實作讓測試通過，最後重構；不可先完成其他 TASK 的實作、事後才回頭補測試
- 撰寫或更新測試前，先用 Grep/Read **讀取現有測試**，確認此次變動涉及的 Scenario 是否已有相同或可覆蓋情境的測試：
  - 若現有測試已覆蓋相同情境，**不重複撰寫**；若情境相似但覆蓋範圍不完整，**合併**成一個測試即可
  - 允許刪除或合併舊有重複測試，但**刪除後必須確認每個 Scenario 仍有至少一個對應測試**；
    不可讓原本有測試的 Scenario 在修改後變成沒有任何測試
- **Scenario ↔ 測試名稱對應**：`<<CHANGE_LOCATION>>/specs/**/*.md` 裡每一個 `#### Scenario:` 標題，
  都必須有一個名稱**完全相同**的 `describe(...)` / `test(...)` / `it(...)`（或對應語言的測試語法）。
- 全部 TASK 完成後再跑完整測試（見下方）
- **不要** commit——修改是否提交由使用者事後決定
- **不要**自行呼叫 /code-review——後續有獨立的 Review Agent 依專案規格審查本次修改，此處只需完成實作與測試

## 重要規範

- 寫入前先讀取原始內容，避免覆蓋不相關程式碼
- 不修改任何 auto-generated 檔案（CLAUDE.md / AGENT.md 通常會標示這類目錄）
- **非必要不撰寫程式碼註解**：只在「為什麼」非顯而易見時（隱藏限制、微妙不變量、特定 bug 的繞過方式）才加一行短註解；說明程式碼「做什麼」的註解一律省略

## 文件同步要求

是否需要同步更新文件，依該任務所屬專案的 CLAUDE.md / AGENT.md（或其他說明檔）判斷：
- 若說明檔要求同步維護 docs/ 下的商業邏輯說明文件，依 tasks.md 中對應的文件更新 TASK 執行；
  若 tasks.md 未包含但說明檔明確要求，主動補上
- 說明檔未提及此類慣例時，不需要主動撰寫或更新文件

## 強制測試與自動修復（所有 TASK 完成後執行，含視需要的文件同步）

依照該專案 CLAUDE.md / AGENT.md 中列出的測試指令執行測試；若說明檔未列出，
探索 package.json / pyproject.toml 等設定檔判斷正確的測試指令。

### 測試失敗的處理

若測試失敗，分析錯誤訊息並修復，然後重新執行測試，**最多重試 3 次**。
3 次之後不論結果如何，繼續輸出最終摘要（測試輸出已由 Bash 工具印出，無需在文字摘要中重複）。

## 最終輸出格式（文字摘要，不含測試輸出）

1. 所有已修改的程式碼檔案清單
2. 所有已新增/修改的說明文件清單
3. 每個 TASK 的完成狀態（✅ 已完成 / ❌ 未完成 + 原因）

{LANGUAGE_POLICY}
"""

_BANNER = "\033[1;32m"
_RED    = "\033[1;31m"
_YELLOW = "\033[1;33m"
_RESET  = "\033[0m"


def execute_node(state: AgentState) -> dict:
    print(f"\n{_BANNER}{'═'*50}\n  [執行 Agent] 開始\n{'═'*50}{_RESET}\n", flush=True)

    project_dir = state.get("project_dir", "")
    change_name = state.get("change_name", "")
    change_dir = os.path.join(REPO_ROOT, project_dir, "openspec", "changes", change_name)
    if not os.path.isdir(change_dir):
        print(
            f"{_RED}  [執行 Agent] 找不到 OpenSpec change 目錄：{change_dir}，"
            f"請先執行 analyze_plan{_RESET}\n",
            flush=True,
        )
        return {"status": "error", "execution_result": f"找不到 OpenSpec change 目錄：{change_dir}"}

    prior_session = take_session(state, _SESSION_KEY)

    start = time.monotonic()

    try:
        branch_name = state.get("branch_name", "")
        if project_dir and branch_name:
            ok, msg = ensure_on_branch(project_dir, branch_name)
            print(f"{_YELLOW}  [git] {msg}{_RESET}", flush=True)
            if not ok:
                return {"status": "error", "execution_result": f"無法切換到分支 {branch_name}：{msg}"}
        elif not branch_name:
            return {"status": "error", "execution_result": "缺少 branch_name，無法在指定分支上實作"}

        skills_block = build_skills_block(_SKILLS)
        change_location = f"{project_dir}/openspec/changes/{change_name}"
        system = (
            _SYSTEM
            .replace("<<PROJECT_CONTEXT>>", build_project_doc_hint_for(project_dir))
            .replace("<<CHANGE_LOCATION>>", change_location)
            .replace("<<BRANCH_NAME_VALUE>>", branch_name)
        )
        prompt = (
            f"{system}\n\n{skills_block}\n\n"
            f"請依 `{change_location}` 的 OpenSpec change 執行："
            "讀取該目錄後，依 tasks.md 處理未完成項。"
        )
        result = call_resuming(
            lambda p, resume: call_claude(p, tools="full", timeout=_TIMEOUT, model=_MODEL, resume=resume),
            prompt, prior_session, "執行 Agent",
        )
    except Exception as e:
        print(f"{_RED}  [執行 Agent] 發生例外：{e}{_RESET}\n", flush=True)
        return {"status": "error", "execution_result": f"執行階段發生例外：{e}"}

    elapsed = time.monotonic() - start

    print(f"\n{_BANNER}{'─'*50}  [執行 Agent] 完成  {'─'*50}", flush=True)
    print(format_usage_stats(result, elapsed), flush=True)
    print(f"{'─'*50}{_RESET}\n", flush=True)

    if result.is_error:
        print(f"{_RED}  [執行 Agent] Claude 執行失敗：{result.text}{_RESET}\n", flush=True)
        if is_usage_limit_error(result.text):
            print(
                f"{_YELLOW}  [執行 Agent] 用量重置後重跑 `--node execute` 並選同一個 change，"
                f"即會接回這次的 session 續作{_RESET}\n",
                flush=True,
            )
        return {
            "status": "error",
            "execution_result": result.text,
            **store_session(_SESSION_KEY, result.session_id or prior_session),
        }

    trimmed = result.text[-4000:] if len(result.text) > 4000 else result.text
    return {
        "status": "ok",
        "execution_result": trimmed,
        **store_session(_SESSION_KEY, ""),
    }
