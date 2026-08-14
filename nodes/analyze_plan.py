import os
import re
import sys
import time
from datetime import datetime
from ..state import AgentState
from ..claude_runner import call_claude, format_usage_stats, QUESTION_MARKER
from ..skill_loader import build_skills_block
from ..project_context import build_project_docs_hint, REPO_ROOT

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

_OPENSPEC_ARTIFACT_RULES = """## OpenSpec 產出規則（規格文件的實際格式）

規格文件不寫成單一 Markdown 檔案，而是遵照 OpenSpec 的 change 資料夾格式，寫在目標專案的
`openspec/changes/<change-name>/` 底下：

### proposal.md
```markdown
# Proposal: <Feature/Fix Name>

## Intent
<為什麼要做這個改動、要解決的問題>

## Scope
In scope:
- <本次要做的事項>

Out of scope:
- <明確排除、避免範疇蔓延的事項；沒有則寫「無」>

## Approach
<高階解決方案概述>
```

### design.md（本專案規定必寫，不採用 OpenSpec 預設「小改動可略過 design.md」的作法）
```markdown
# Design: <Feature/Fix Name>

## Technical Approach
<技術實作方式>

## Architecture Decisions
### Decision: <決策名稱>
<決策內容與理由；沒有值得記錄的架構決策則寫「無」>

## Testing Strategy
### Seam（測試接縫）
- **首選接縫**：<測試對象與測試方法>
- **次要接縫**：<次要驗證方式，沒有則寫「無」>

### 測試案例矩陣（Test Matrix）
| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| <案例> | ... | ... |

## Technical Debt & Follow-up Notes
<需追蹤的技術債；沒有則寫「無」>
```
「Testing Strategy」「Technical Debt & Follow-up Notes」兩個小節必須保留標題，沒有內容也要填「無」，不可留白或整段刪除。

### specs/<domain>/spec.md（delta，可能有多個 domain，各自建一個檔案）
只描述本次「改了什麼」，不是整份系統規格：
```markdown
## ADDED Requirements

### Requirement: <名稱>
The system SHALL/MUST <一個明確、可觀察的行為>。

#### Scenario: <情境名稱>
- GIVEN <前提>
- WHEN <觸發>
- THEN <結果>

## MODIFIED Requirements
（改變既有行為時使用，須包含完整的新版本內容 + 一行說明改了什麼）

## REMOVED Requirements
（行為被移除時使用，須說明原因）
```
規則：
- 每個 Requirement 只講一件事、一個 SHALL/MUST/SHOULD；不要把好幾個「而且」塞進同一個 Requirement
- 每個 Requirement 至少要有一個 Scenario；Scenario 要測到具體情境（含邊界/錯誤情況），不是重述 Requirement
- 若這是該 domain 第一次建立 spec（`openspec/specs/<domain>/` 目前不存在），在 delta 檔案最上面加一段 `## Purpose`（一兩句話說明這個 domain 是做什麼的）；domain 已存在則不需要
- 不需要獨立的「User Stories」章節——Scenario 已經是驗收條件的正式化版本
- 若本次任務純粹是重構/文件/設定調整、完全沒有外部可觀察行為變化，可以在該 change 的 `.openspec.yaml` 加 `skip_specs: true` 並略過 specs delta；若 REMOVED 移除了某個 domain 的最後一個 Requirement，需在 `.openspec.yaml` 加 `retire_capabilities: true` 才能讓 archive 一併刪除該 domain 的 spec 檔

### tasks.md
```markdown
# Tasks

## 1. <群組名稱>
- [ ] 1.1 <具體任務>
- [ ] 1.2 <具體任務>

## 2. <群組名稱>
- [ ] 2.1 <具體任務>
```
- 用階層編號（1.1、1.2...），依實作順序排列
- 涉及新增或修改行為的任務，須額外安排一個對應的「撰寫／更新測試」任務（優先在既有測試 seam 上以 tdd skill 的紅-綠循環進行）；純文件、設定調整或不改變行為的重構可不需要
- 是否需要「更新文件」任務，依該任務所屬專案的 CLAUDE.md / AGENT.md 判斷：若說明檔要求同步維護 docs/ 下的商業邏輯說明文件，安排對應任務（通常放在最後）；未提及此類慣例時不強制新增
- 這份檔案會被執行 Agent 逐項勾選、被審查 Agent 讀取確認完成度，內容必須跟你在最終輸出的分析摘要一致

### 完成前的驗證
用 Bash 執行 `openspec validate <change-name> --json --strict`；有 error 等級的問題就修正對應檔案後重新驗證，直到沒有 error 為止（warning 可視情況保留、不必為了消除 warning 硬湊內容）。"""

_CHANGE_SETUP_INITIAL = """## 建立 OpenSpec Change（規格文件的實際存放位置）

1. 依 <<PROJECT_CONTEXT>> 判斷本次任務主要涉及哪一個目標專案目錄，記下其相對於 workspace root
   的路徑（例如 `my-project`）——這個路徑之後要原封不動地放進最終輸出的 `PROJECT_DIR:` 一行
2. 用 Bash 檢查 `<目標專案>/openspec/` 是否存在；不存在的話執行一次性 bootstrap：
   `cd <目標專案> && openspec init --tools claude --force`
3. 決定 change name（必須是 kebab-case：小寫字母、數字、單一連字號，不可有底線／大寫／連續連字號／開頭結尾連字號）：
   - 若使用者於任務開始時提供了自訂名稱，本次為：<<CHANGE_NAME_VALUE>>，直接以此作為 change name
   - 若上方顯示為空（使用者未提供），改用 `git -C <目標專案> branch --show-current` 取得目標專案
     目前的 git branch 名稱，轉成 kebab-case 作為 change name
4. 執行 `cd <目標專案> && openspec new change <change-name>` 建立 change 資料夾
5. 依下方「OpenSpec 產出規則」用 Write 在該 change 資料夾底下寫 proposal.md / specs/**/*.md /
   design.md / tasks.md，並依「完成前的驗證」跑 `openspec validate` 到通過"""

_CHANGE_SETUP_REPLAN = """## 更新既有的 OpenSpec Change

本次沿用先前已建立的 change，不需要 `openspec init` 或 `openspec new change`：
- 目標專案：<<PROJECT_DIR_VALUE>>
- Change name：<<CHANGE_NAME_VALUE>>
- Change 位置：`<<PROJECT_DIR_VALUE>>/openspec/changes/<<CHANGE_NAME_VALUE>>/`

直接在這個資料夾下用 Read 讀取、Edit/Write 更新 proposal.md / specs/**/*.md / design.md /
tasks.md（維持既有內容裡跟本次無關的部分，只改需要調整的段落），完成後依「完成前的驗證」
重新跑 `openspec validate` 到通過。

若本輪為「重寫」等級：完成 rollback 後，同時把 tasks.md 所有 `- [x]` checkbox 重設回 `- [ ]`
（重寫代表要重新執行整份計畫）；「修補」等級不動 checkbox。"""

_CHANGE_SETUP_HUMAN_REVISE = """## 更新既有的 OpenSpec Change

本次沿用先前已建立的 change，不需要 `openspec init` 或 `openspec new change`：
- 目標專案：<<PROJECT_DIR_VALUE>>
- Change name：<<CHANGE_NAME_VALUE>>
- Change 位置：`<<PROJECT_DIR_VALUE>>/openspec/changes/<<CHANGE_NAME_VALUE>>/`

直接在這個資料夾下用 Read 讀取、Edit/Write 更新 proposal.md / specs/**/*.md / design.md /
tasks.md（維持既有內容裡跟本次修改意見無關的部分，只改需要調整的段落），完成後依
「完成前的驗證」重新跑 `openspec validate` 到通過。"""

_SYSTEM_INITIAL = f"""你是一位資深全端工程師，負責「分析與規劃」階段。

<<PROJECT_CONTEXT>>

## 執行步驟

1. 用 Read/Glob/Grep 閱讀相關程式碼，找出需修改的位置與潛在衝突
2. 依 grill-with-docs 對本任務進行互動式釐清（見下方「提問規則」），過程中依 domain-modeling 規則即時更新 CONTEXT.md / docs/adr/
3. 共識達成後，依下方「建立 OpenSpec Change」與「OpenSpec 產出規則」完成規格文件
   （本專案未串接 issue tracker，略過 to-spec 中「發布並標記 triage label」的步驟；探索程式碼以確認測試 seam，優先使用既有 seam、避免新增）

{_CHANGE_SETUP_INITIAL}

{_OPENSPEC_ARTIFACT_RULES}

## 最終輸出格式

## 分析
[2-5 行摘要：需求、涉及檔案、潛在問題]

## 計畫
（已寫入 tasks.md，摘要如下，供人工確認時快速瀏覽）
TASK 1: [操作] [路徑] — [說明]
TASK 2: [操作] [路徑] — [說明]
...

PROJECT_DIR: <目標專案相對 workspace root 的路徑>
CHANGE_NAME: <kebab-case change name>

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
3. 依下方「更新既有的 OpenSpec Change」與「OpenSpec 產出規則」重新撰寫規格文件

### 若為「修補」：
1. 不需要 rollback，保留已完成的修改
2. 閱讀現有程式碼，精確定位需要修正的地方；依下方「提問規則」針對審查結果逐點 grill 確認
3. 依下方「更新既有的 OpenSpec Change」與「OpenSpec 產出規則」更新規格文件相關段落（不必整份重寫，但維持章節結構，不可整段刪除某章節）

{_CHANGE_SETUP_REPLAN}

{_OPENSPEC_ARTIFACT_RULES}

## 輸出格式

最終輸出：

## 分析
[2-5 行摘要：問題根因、涉及檔案、修正方向]

## 計畫
（已更新 tasks.md，摘要如下，供人工確認時快速瀏覽）
TASK 1: [操作] [路徑] — [說明]
TASK 2: [操作] [路徑] — [說明]
...

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
4. 依下方「更新既有的 OpenSpec Change」與「OpenSpec 產出規則」更新規格文件（維持章節結構，不可整段刪除某章節）
5. 完成後在最終輸出中附上調整後的摘要

{_CHANGE_SETUP_HUMAN_REVISE}

{_OPENSPEC_ARTIFACT_RULES}

## 輸出格式

## 分析
[2-5 行摘要：根據人工意見的修正方向與涉及檔案]

## 計畫
（已更新 tasks.md，摘要如下，供人工確認時快速瀏覽）
TASK 1: [操作] [路徑] — [說明]
TASK 2: [操作] [路徑] — [說明]
...

{_QUESTION_PROTOCOL}

請用繁體中文回答。
"""

_BANNER = "\033[1;34m"
_RED    = "\033[1;31m"
_YELLOW = "\033[1;33m"
_RESET  = "\033[0m"

_MAX_QUESTIONS = 15


_QUESTION_LINE_RE = re.compile(r"^\s*" + re.escape(QUESTION_MARKER), re.MULTILINE)
_PROJECT_DIR_RE = re.compile(r"^\s*PROJECT_DIR:\s*(.+?)\s*$", re.MULTILINE)
_CHANGE_NAME_RE = re.compile(r"^\s*CHANGE_NAME:\s*(.+?)\s*$", re.MULTILINE)
_TASK_CHECKBOX_RE = re.compile(r"^-\s\[[ xX]\]\s*(.+)$", re.MULTILINE)

_KEBAB_INVALID_RE = re.compile(r"[^a-z0-9-]+")
_MULTI_HYPHEN_RE = re.compile(r"-{2,}")


def _sanitize_change_name(raw: str) -> str:
    """轉成 OpenSpec 要求的 kebab-case：小寫字母/數字/單一連字號，去除底線、空白、大寫、
    連續連字號與開頭結尾連字號。"""
    s = raw.strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = _KEBAB_INVALID_RE.sub("", s)
    s = _MULTI_HYPHEN_RE.sub("-", s)
    return s.strip("-")


def _read_change_artifacts(project_dir: str, change_name: str, raw: str) -> tuple[str, list[str]]:
    """規格文件的事實來源是 OpenSpec CLI 自己會驗證的檔案，不是 Claude 聊天回覆的摘要文字：
    analysis 讀 proposal.md 全文，plan 讀 tasks.md 的 checkbox 清單。任一檔案讀不到時退回舊有的
    「regex Claude 最終輸出文字」方式，避免整個節點失敗。"""
    change_dir = os.path.join(REPO_ROOT, project_dir, "openspec", "changes", change_name)

    analysis = ""
    try:
        with open(os.path.join(change_dir, "proposal.md"), encoding="utf-8") as f:
            analysis = f.read().strip()
    except OSError:
        pass
    if not analysis:
        analysis_match = re.search(r"## 分析\n([\s\S]*?)(?=## 計畫|$)", raw)
        analysis = analysis_match.group(1).strip() if analysis_match else raw[:500]

    plan: list[str] = []
    try:
        with open(os.path.join(change_dir, "tasks.md"), encoding="utf-8") as f:
            plan = _TASK_CHECKBOX_RE.findall(f.read())
    except OSError:
        pass
    if not plan:
        tasks = re.findall(r"TASK\s*\d+:\s*(.+)", raw)
        if not tasks:
            tasks = re.findall(r"STEP\s*\d+:\s*(.+)", raw)
        plan = tasks if tasks else [raw]

    return analysis, plan


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


def _ask_change_name() -> str:
    """任務開始時（僅初始規劃）詢問使用者 OpenSpec change 名稱，留空則由 Claude 改用目標專案的
    git branch 名稱。非互動式環境或使用者直接按 Enter／中止時，留空繼續。"""
    print(
        f"\n{_YELLOW}  [分析+規劃 Agent] 請輸入 OpenSpec change 名稱"
        f"（kebab-case，可直接按 Enter 改用目標專案目前 git branch 名稱）：{_RESET}",
        flush=True,
    )
    if not sys.stdin.isatty():
        print(f"{_YELLOW}  非互動式環境，change 名稱留空，改用 branch name{_RESET}\n", flush=True)
        return ""
    try:
        answer = input(f"{_YELLOW}  > {_RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{_YELLOW}  已跳過，change 名稱留空，改用 branch name{_RESET}\n", flush=True)
        return ""
    sanitized = _sanitize_change_name(answer)
    if answer and not sanitized:
        print(f"{_YELLOW}  輸入內容正規化後為空，視為未提供，改用 branch name{_RESET}\n", flush=True)
    return sanitized


def analyze_plan_node(state: AgentState) -> dict:
    review_result = state.get("review_result", "")
    review_level = state.get("review_level", "")
    human_feedback = state.get("human_feedback", "")
    is_replan = bool(review_result)
    is_human_revise = bool(human_feedback) and not is_replan

    change_name = state.get("change_name", "")
    project_dir = state.get("project_dir", "")

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
        if not change_name:
            change_name = _ask_change_name()

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
                .replace("<<PROJECT_DIR_VALUE>>", project_dir)
                .replace("<<CHANGE_NAME_VALUE>>", change_name)
                .replace("<<TODAY>>", today)
            )
        elif is_human_revise:
            system = (
                _SYSTEM_HUMAN_REVISE
                .replace("<<PROJECT_CONTEXT>>", project_context)
                .replace("<<HUMAN_FEEDBACK>>", human_feedback)
                .replace("<<PROJECT_DIR_VALUE>>", project_dir)
                .replace("<<CHANGE_NAME_VALUE>>", change_name)
                .replace("<<TODAY>>", today)
            )
        else:
            system = (
                _SYSTEM_INITIAL
                .replace("<<PROJECT_CONTEXT>>", project_context)
                .replace("<<CHANGE_NAME_VALUE>>", change_name or "（未提供，留空）")
                .replace("<<TODAY>>", today)
            )

        prompt = f"{system}\n\n{skills_block}\n\n任務：{state['task']}"
        result = _run_with_grilling(prompt, tools=tools, model=model, timeout=300)
    except Exception as e:
        print(f"{_RED}  [分析+規劃 Agent] 發生例外：{e}{_RESET}\n", flush=True)
        return {"status": "error", "analysis": f"分析階段發生例外：{e}", "plan": [], "change_name": change_name, "project_dir": project_dir}

    elapsed = time.monotonic() - start

    print(f"\n{_BANNER}{'─'*50}  [分析+規劃 Agent] 完成  {'─'*50}", flush=True)
    print(format_usage_stats(result, elapsed), flush=True)
    print(f"{'─'*50}{_RESET}\n", flush=True)

    if result.is_error:
        print(f"{_RED}  [分析+規劃 Agent] Claude 執行失敗：{result.text}{_RESET}\n", flush=True)
        return {"status": "error", "analysis": result.text, "plan": [], "change_name": change_name, "project_dir": project_dir}

    raw = result.text

    parsed_project_dir = _PROJECT_DIR_RE.search(raw)
    if parsed_project_dir:
        project_dir = parsed_project_dir.group(1).strip()

    parsed_change_name = _CHANGE_NAME_RE.search(raw)
    if parsed_change_name:
        sanitized = _sanitize_change_name(parsed_change_name.group(1))
        if sanitized:
            change_name = sanitized

    if not project_dir or not change_name:
        print(
            f"{_RED}  [分析+規劃 Agent] 未能取得 PROJECT_DIR/CHANGE_NAME，"
            f"無法定位 OpenSpec change 位置{_RESET}\n",
            flush=True,
        )
        return {
            "status": "error",
            "analysis": raw,
            "plan": [],
            "change_name": change_name,
            "project_dir": project_dir,
        }

    analysis, plan = _read_change_artifacts(project_dir, change_name, raw)

    return {
        "analysis": analysis,
        "plan": plan,
        "status": "pending",
        "review_result": "",
        "review_level": "",
        "review_blocking": False,
        "human_feedback": "",
        "change_name": change_name,
        "project_dir": project_dir,
    }
