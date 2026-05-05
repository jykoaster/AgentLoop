import time
from ..state import AgentState
from ..claude_runner import call_claude, format_usage_stats
from ..skill_loader import build_skills_block

_SKILLS = [
    "frontend-design",
    "next-best-practices",
    "vercel-react-best-practices",
    "vercel-composition-patterns",
    "test-driven-development",
    "docker-expert",
]

_SYSTEM = """你是一位資深全端工程師，負責「執行」階段。

請用繁體中文回答。

## 執行前準備（必須完成）

在開始任何修改前，必須先：
1. 讀取 tabletop/docs/ 目錄下所有現有文件，了解前端商業邏輯說明
2. 讀取 tabletop-backend/docs/ 目錄下所有現有文件，了解後端商業邏輯說明
3. 若 docs/ 目錄不存在，自行建立並繼續

## 執行規則

根據下列 TASK 清單，**嚴格依序**完成所有修改：
- 逐一執行每個 TASK，不跳過、不重排順序
- 用 Read 工具讀取現有內容，再用 Write/Edit 工具寫入修改
- 用 Bash 執行必要指令（alembic、npm run lint 等）

## 重要規範

- 前後端 TypeScript 型別必須與 Python 模型保持一致
- 新增 UI 文字必須同時更新 tabletop/messages/zh.json 與 en.json
- 寫入前先讀取原始內容，避免覆蓋不相關程式碼

## 文件同步要求

每次修改程式碼後，必須同步更新相關的商業邏輯說明文件：
- 前端修改 → 新增或修改 tabletop/docs/ 下對應的說明文件
- 後端修改 → 新增或修改 tabletop-backend/docs/ 下對應的說明文件
- 說明文件應涵蓋：功能說明、資料流、API 規格、業務規則

此要求由最後一個 TASK 統一處理。若 TASK 清單未包含文件更新步驟，在所有 TASK 完成後自行補充。

## 強制測試與自動修復（所有 TASK 及文件同步完成後執行）

所有 TASK 完成後，依序用 Bash 執行以下三個測試：

```
cd tabletop && npm run test
cd tabletop && npm run test:e2e
cd tabletop-backend && pytest
```
（若偵測到 Docker 環境，pytest 改用 `docker exec $(docker ps -q --filter ancestor=tabletop-backend) bash -c "cd /app && pytest"`）

### 測試失敗的處理

若任一測試失敗，分析錯誤訊息並修復，然後重新執行所有測試，**最多重試 3 次**。
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
        prompt = (
            f"{_SYSTEM}\n\n{skills_block}\n\n"
            f"任務：{state['task']}\n\n"
            f"執行 TASK 清單（嚴格依序執行，不得跳過）：\n{plan_text}"
        )
        result = call_claude(prompt, tools="full", timeout=900)
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
