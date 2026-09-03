import time
from ..state import AgentState
from ..claude_runner import call_claude, format_usage_stats
from ..skill_loader import build_skills_block
from ..project_context import build_project_doc_hint_for
from ..git_ops import ensure_on_branch

_SKILLS = [
    "tdd",
]

# 使用的模型（"haiku" | "sonnet" | "opus" | "fable"，見 claude_runner.MODEL_IDS；
# None 則沿用 claude CLI 本身的預設模型）
_MODEL = "sonnet"

_SYSTEM = """你是一位資深全端工程師，負責「執行」階段。

請用繁體中文回答。

## 執行前準備（必須完成）

在開始任何修改前，必須先：
1. 已由系統確認目前在分支 `<<BRANCH_NAME_VALUE>>` 上（呼叫端已切換完成，不需要再檢查或
   checkout）；本階段所有程式碼修改都必須留在這個分支，不要切去其他分支。
2. 用 Read 讀取 `<<CHANGE_LOCATION>>` 下的 proposal.md、specs/**/*.md、tasks.md
   （若有 design.md 一併讀取；小改動可能沒有此檔，不視為缺漏）。
   規格、驗收條件與任務清單以這些檔案為準，不要依賴本 prompt 是否貼上 TASK 正文。
3. 依下方「目標專案」讀取其 CLAUDE.md / AGENT.md，了解該專案的架構、指令（測試、lint、build 等）、
   目錄慣例、程式碼規範，以及**技術棧**；找不到說明檔則自行用 Read/Glob/Grep 探索程式碼並比對現有風格
4. 依偵測到的技術棧，自行從你可用的 skills 中挑選並使用適合的其他 skill
   （例如 Vue 專案適用 vue-best-practices、Nuxt + Vitest 專案適用 nuxt-vitest-msw
   等）——不要假設任何特定技術棧，依實際偵測結果選用。tdd 已固定提供給你，見下方說明
5. 若該專案 docs/ 目錄存在，讀取其下所有現有文件，了解商業邏輯說明；docs/ 目錄不存在時不需自行建立

<<PROJECT_CONTEXT>>

## 執行方式

依 `<<CHANGE_LOCATION>>/tasks.md` 的順序**嚴格依序**完成所有修改：
- 逐一執行每個 TASK，不跳過、不重排順序
- 用 Read 工具讀取現有內容，再用 Write/Edit 工具寫入修改
- 用 Bash 執行必要指令
- 程式碼風格、命名慣例、目錄結構、i18n／型別／auto-generated 檔案等規則，一律依照該專案
  CLAUDE.md / AGENT.md 的說明；說明檔未涵蓋的細節，比對該專案現有程式碼風格
- 每完成一個 TASK，立即用 Edit 把 `<<CHANGE_LOCATION>>/tasks.md` 裡對應的 checkbox 從
  `- [ ]` 改成 `- [x]`，讓這份檔案即時反映實際完成進度（後續 Review Agent 會依此核對）
- 若 tasks.md 中出現「撰寫／更新測試」的 TASK，**必須**依 tdd skill 的紅-綠循環執行該 TASK：
  先寫一個會失敗的測試，再寫最小可行的實作讓測試通過，最後重構；不可先完成其他 TASK 的實作、事後才回頭補測試
- 過程中定期執行型別檢查與單一測試檔案；全部 TASK 完成後再跑完整測試（見下方）
- **不要** commit——修改是否提交由使用者事後決定
- **不要**自行呼叫 /code-review——後續有獨立的 Review Agent 依專案規格審查本次修改，此處只需完成實作與測試

## 重要規範

- 寫入前先讀取原始內容，避免覆蓋不相關程式碼
- 不修改任何 auto-generated 檔案（CLAUDE.md / AGENT.md 通常會標示這類目錄）

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
"""

_BANNER = "\033[1;32m"
_RED    = "\033[1;31m"
_YELLOW = "\033[1;33m"
_RESET  = "\033[0m"


def execute_node(state: AgentState) -> dict:
    print(f"\n{_BANNER}{'═'*50}\n  [執行 Agent] 開始\n{'═'*50}{_RESET}\n", flush=True)

    start = time.monotonic()

    try:
        project_dir = state.get("project_dir", "")
        branch_name = state.get("branch_name", "")
        if project_dir and branch_name:
            ok, msg = ensure_on_branch(project_dir, branch_name)
            print(f"{_YELLOW}  [git] {msg}{_RESET}", flush=True)
            if not ok:
                return {"status": "error", "execution_result": f"無法切換到分支 {branch_name}：{msg}"}
        elif not branch_name:
            return {"status": "error", "execution_result": "缺少 branch_name，無法在指定分支上實作"}

        skills_block = build_skills_block(_SKILLS)
        change_location = f"{project_dir}/openspec/changes/{state.get('change_name', '')}"
        system = (
            _SYSTEM
            .replace("<<PROJECT_CONTEXT>>", build_project_doc_hint_for(project_dir))
            .replace("<<CHANGE_LOCATION>>", change_location)
            .replace("<<BRANCH_NAME_VALUE>>", branch_name)
        )
        prompt = f"{system}\n\n{skills_block}\n\n任務：{state['task']}"
        result = call_claude(prompt, tools="full", timeout=900, model=_MODEL)
    except Exception as e:
        print(f"{_RED}  [執行 Agent] 發生例外：{e}{_RESET}\n", flush=True)
        return {"status": "error", "execution_result": f"執行階段發生例外：{e}"}

    elapsed = time.monotonic() - start

    print(f"\n{_BANNER}{'─'*50}  [執行 Agent] 完成  {'─'*50}", flush=True)
    print(format_usage_stats(result, elapsed), flush=True)
    print(f"{'─'*50}{_RESET}\n", flush=True)

    if result.is_error:
        print(f"{_RED}  [執行 Agent] Claude 執行失敗：{result.text}{_RESET}\n", flush=True)
        return {"status": "error", "execution_result": result.text}

    trimmed = result.text[-4000:] if len(result.text) > 4000 else result.text
    return {"execution_result": trimmed}
