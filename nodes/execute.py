import time
from ..state import AgentState
from ..claude_runner import call_claude, format_usage_stats
from ..skill_loader import build_skills_block
from ..project_context import build_project_docs_hint

_SKILLS = [
    "implement",
    "tdd",
]

# 使用的模型（"haiku" | "sonnet" | "opus" | "fable"，見 claude_runner.MODEL_IDS；
# None 則沿用 claude CLI 本身的預設模型）
_MODEL = "sonnet"

_SYSTEM = """你是一位資深全端工程師，負責「執行」階段。

請用繁體中文回答。

## 執行前準備（必須完成）

在開始任何修改前，必須先：
1. 依下方「專案說明檔」判斷本次任務涉及的專案目錄，用 Read 讀取其 CLAUDE.md / AGENT.md，
   了解該專案的架構、指令（測試、lint、build 等）、目錄慣例、程式碼規範，以及**技術棧**
   - 若任務同時涉及多個專案（例如前後端），須分別讀取各自的說明檔
   - 若找不到 CLAUDE.md / AGENT.md，自行用 Read/Glob/Grep 探索程式碼並比對現有風格
2. 依偵測到的技術棧，自行從你可用的 skills 中挑選並使用適合的其他 skill
   （例如 Vue 專案適用 vue-best-practices、Nuxt + Vitest 專案適用 nuxt-vitest-msw
   等）——不要假設任何特定技術棧，依實際偵測結果選用。tdd 已固定提供給你，見下方說明
3. 若該專案 docs/ 目錄存在，讀取其下所有現有文件，了解商業邏輯說明；docs/ 目錄不存在時不需自行建立

<<PROJECT_CONTEXT>>

## 執行方式

本階段以 implement skill 的流程為主軸執行下列 TASK 清單，但有以下覆蓋規則：
- **不要**執行 implement 流程中「commit 到目前分支」的步驟——修改是否提交由使用者事後決定
- **不要**自行呼叫 /code-review——後續有獨立的 Review Agent 依專案規格審查本次修改，此處只需完成實作與測試
- 若 TASK 清單中出現「撰寫／更新測試」的 TASK，**必須**依 tdd skill 的紅-綠循環執行該 TASK：先寫一個會失敗的測試，
  再寫最小可行的實作讓測試通過，最後重構；不可先完成其他 TASK 的實作、事後才回頭補測試
- 其餘步驟（定期執行型別檢查與單一測試檔案、最後執行完整測試）依 implement skill 原本的流程進行

根據下列 TASK 清單，**嚴格依序**完成所有修改：
- 逐一執行每個 TASK，不跳過、不重排順序
- 用 Read 工具讀取現有內容，再用 Write/Edit 工具寫入修改
- 用 Bash 執行必要指令
- 程式碼風格、命名慣例、目錄結構、i18n／型別／auto-generated 檔案等規則，一律依照該專案
  CLAUDE.md / AGENT.md 的說明；說明檔未涵蓋的細節，比對該專案現有程式碼風格
- 每完成一個 TASK，立即用 Edit 把 `<<CHANGE_LOCATION>>/tasks.md` 裡對應的 checkbox 從
  `- [ ]` 改成 `- [x]`，讓這份檔案即時反映實際完成進度（後續 Review Agent 會依此核對）

## 重要規範

- 寫入前先讀取原始內容，避免覆蓋不相關程式碼
- 不修改任何 auto-generated 檔案（CLAUDE.md / AGENT.md 通常會標示這類目錄）

## 文件同步要求

是否需要同步更新文件，依該任務所屬專案的 CLAUDE.md / AGENT.md（或其他說明檔）判斷：
- 若說明檔要求同步維護 docs/ 下的商業邏輯說明文件，依 TASK 清單中對應的文件更新 TASK 執行；
  若 TASK 清單未包含但說明檔明確要求，主動補上
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
_RESET  = "\033[0m"


def execute_node(state: AgentState) -> dict:
    print(f"\n{_BANNER}{'═'*50}\n  [執行 Agent] 開始\n{'═'*50}{_RESET}\n", flush=True)

    start = time.monotonic()

    try:
        skills_block = build_skills_block(_SKILLS)
        plan_text = "\n".join(
            f"TASK {i+1}: {s}" for i, s in enumerate(state["plan"])
        )
        change_location = f"{state.get('project_dir', '')}/openspec/changes/{state.get('change_name', '')}"
        system = (
            _SYSTEM
            .replace("<<PROJECT_CONTEXT>>", build_project_docs_hint())
            .replace("<<CHANGE_LOCATION>>", change_location)
        )
        prompt = (
            f"{system}\n\n{skills_block}\n\n"
            f"任務：{state['task']}\n\n"
            f"執行 TASK 清單（嚴格依序執行，不得跳過）：\n{plan_text}"
        )
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
