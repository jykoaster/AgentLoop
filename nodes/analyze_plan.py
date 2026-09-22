import os
import re
import sys
import time
from ..core import AgentState
from ..lib import (
    call_claude, format_usage_stats, QUESTION_MARKER,
    build_skills_block,
    build_project_doc_hint_for, REPO_ROOT,
    ensure_on_branch, rollback_except_openspec,
    ensure_initialized, ensure_change_created, validate_change,
)

# 初始規劃／依人工意見調整：完整 grilling + domain-modeling（人工意見可能牽涉詞彙或架構決策）
_SKILLS = [
    "grilling",
    "domain-modeling",
    "tdd",
    "openspec-authoring",
]

# 重新規劃（review 觸發）：只針對 review 結果 grill，不重跑 domain-modeling 文件同步，
# 不需要注入其完整內容（省下的是 skill_loader 白名單裡最大的一塊）
_SKILLS_REPLAN = [
    "grilling",
    "tdd",
    "openspec-authoring",
]

# 使用的模型（"haiku" | "sonnet" | "opus" | "fable"，見 claude_runner.MODEL_IDS）
_MODEL = "opus"

_QUESTION_FORMAT = """- 每個問題附上數字選項，窮舉合理答案（至少 2 個），並在你建議的選項後加註「（建議）」
- 若需要提問，該輪回應「只能」輸出下列格式，不得包含其他文字：即使你已經做完部分分析、找到相關檔案、或想好了初步計畫草稿，只要本輪要提問，也不可以先把這些內容輸出出來，必須整輪只有下列格式：

QUESTION: <你的問題>
1. <選項一>（建議）
2. <選項二>
3. <選項三，視需要增減>

- 使用者可能回覆選項編號（例如「1」）或自訂文字，兩者都視為有效答案並據以判斷後續動作
- 輸出後立即結束本輪回應，等待使用者回覆後再繼續"""

_QUESTION_PROTOCOL = f"""## 提問規則（grilling 互動式釐清）

依照 grilling 對本任務逐一提問、以 domain-modeling 即時記錄詞彙與 ADR。

{_QUESTION_FORMAT}
- 初始規劃：強制三項（見「OpenSpec 產出規則」的 Specine 規格對齊）若無法從任務描述＋程式碼探索寫出具體內容（不是任務原句複述），必須繼續提問直到有共識；其餘七項只在需要使用者決策時提問
- 依人工意見調整：只在修改意見影響強制三項或某項其餘要素時，針對受影響的項提問；不要重跑完整 Specine 清單
- 當所有需要釐清的決策都已有共識，且強制三項已有可寫進規格的具體內容，才可以繼續進行規格撰寫與最終輸出（此後不得再輸出 QUESTION）"""

_REVIEW_QUESTION_PROTOCOL = f"""## 提問規則（針對 review 結果 grill）

依照 grilling：針對審查結果（Review Result）中每一個被標記的問題點逐一提出質疑性問題，確認：
- 該問題點的判斷是否成立、影響範圍是否如審查所述
- 若修正方向有多種可能取捨，請使用者拍板
不重跑完整 Specine grilling；更新規格時仍須維持強制三項寫在對應檔案位置（見「OpenSpec 產出規則」）。

{_QUESTION_FORMAT}
- 當 review 標記的每個問題點都已確認完畢，才可以繼續進行後續流程與最終輸出（此後不得再輸出 QUESTION）"""

_DOMAIN_CONTEXT_EXISTING = """沿用以下既有 domain（specs/**/*.md 不加 `## Purpose`）：<<DOMAIN_LIST_VALUE>>
若任務內容確實還涉及上述以外的 domain，可依語意自訂新 domain 名稱（視為「domain 首次建立」，該
delta 檔案最上面需加 `## Purpose`，與 proposal Intent 對齊）。"""

_DOMAIN_CONTEXT_NEW = """使用者已確認本次為建立新 domain：請依任務語意自訂新 domain 名稱，視為
「domain 首次建立」，specs/<domain>/spec.md 最上面需加 `## Purpose`（與 proposal Intent 對齊）。"""

_DOMAIN_CONTEXT_NEW_WITH_PURPOSE = """使用者已確認本次為建立新 domain，並指定了這個 domain 的
Purpose：<<DOMAIN_PURPOSE_VALUE>>

請依任務語意自訂新 domain 名稱，視為「domain 首次建立」，specs/<domain>/spec.md 最上面的
`## Purpose` 直接採用使用者這段文字（不要自己另外改寫或簡化），並確認 proposal.md 的 `## Intent`
與其對齊。"""

_PROJECT_AND_DOMAIN_INFO = """## 目標專案與 Domain（已由系統確認，不需再詢問或用 Bash 檢查）

目標專案目錄：<<PROJECT_DIR_VALUE>>（相對 workspace root；`openspec/` 已確認存在）

<<DOMAIN_CONTEXT_VALUE>>"""

_CHANGE_SETUP_INITIAL = """## OpenSpec Change 位置

change 資料夾已由系統建立於 `<<PROJECT_DIR_VALUE>>/openspec/changes/<<CHANGE_NAME_VALUE>>/`
（工作分支 `<<BRANCH_NAME_VALUE>>` 也已切換完成），change name 固定為 <<CHANGE_NAME_VALUE>>，
不要另取。依下方「OpenSpec 產出規則」用 Write 在該資料夾底下寫 proposal.md / specs/**/*.md /
tasks.md；非小改動時才寫 design.md。"""

_CHANGE_SETUP_EXISTING = """## 既有的 OpenSpec Change 位置

本次沿用先前已建立的 change：
- 目標專案：<<PROJECT_DIR_VALUE>>（工作分支 <<BRANCH_NAME_VALUE>> 已切換完成）
- Change 位置：`<<PROJECT_DIR_VALUE>>/openspec/changes/<<CHANGE_NAME_VALUE>>/`

直接在這個資料夾下用 Read 讀取、Edit/Write 更新 proposal.md / specs/**/*.md / tasks.md
（維持既有內容裡跟本次無關的部分，只改需要調整的段落）。已有 design.md 則一併更新；尚未有
且本輪仍是小改動則不必新增；本輪已不再是小改動才 Write design.md。"""

_ANALYZE_PROHIBITIONS = """## 嚴格禁止事項

以下事項**嚴格禁止**，違反即為執行錯誤：

- **不得修改任何應用程式原始碼**（`.py`、`.ts`、`.vue`、`.go` 等實作檔案）——程式碼修改由 execute node 負責；
  此階段僅允許讀取程式碼（Read/Glob/Grep），以及寫入 OpenSpec change 資料夾下的規格文件
- **不得將 `tasks.md` 中的 `- [ ]` 改為 `- [x]`**——task 完成標記由 execute node 在實作後即時更新；
  analyze 階段只寫或改 task 的文字描述，不能標記完成"""

_SYSTEM_INITIAL = f"""你是一位資深全端工程師，負責「分析與規劃」階段。

<<PROJECT_CONTEXT>>

## 執行步驟

1. 用 Read/Glob/Grep 閱讀相關程式碼，找出需修改的位置與潛在衝突（目標專案與 domain 已由系統確認，見下方）
2. 依 grilling 對本任務進行互動式釐清（見下方「提問規則」），過程中依 domain-modeling 即時記錄詞彙與 ADR；
   grill 結果須能支撐 Specine 強制三項的具體內容（見下方「OpenSpec 產出規則」），其餘七項依適用納入
3. 共識達成後，依下方「OpenSpec 產出規則」完成規格文件（change 資料夾已由系統建立，見下方
   「OpenSpec Change 位置」；探索程式碼以確認測試 seam，優先使用既有 seam、避免新增）

{_PROJECT_AND_DOMAIN_INFO}
{_CHANGE_SETUP_INITIAL}

{_ANALYZE_PROHIBITIONS}

## 最終輸出

規格內容只寫在 OpenSpec change 資料夾，不要在聊天裡重複輸出分析／計畫／TASK 清單，一句話回報
完成狀態即可。

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

### 若為「重寫」（系統已還原目標專案未提交的程式碼變更，openspec/ 不受影響）：
1. 重新閱讀現有程式碼；依下方「提問規則」針對審查結果逐點 grill 確認，不需重新進行完整的 grilling 釐清或文件同步
2. 依下方「更新既有的 OpenSpec Change」與「OpenSpec 產出規則」重新撰寫規格文件（強制三項仍須寫在對應位置）

### 若為「修補」：
1. 不需要 rollback，保留已完成的修改
2. 閱讀現有程式碼，精確定位需要修正的地方；依下方「提問規則」針對審查結果逐點 grill 確認
3. 依下方「更新既有的 OpenSpec Change」與「OpenSpec 產出規則」更新規格文件相關段落（不必整份重寫，但維持章節結構，不可整段刪除某章節；強制三項仍須保留）

{_CHANGE_SETUP_EXISTING}

{_ANALYZE_PROHIBITIONS}

## 最終輸出

規格內容以既有 OpenSpec change 資料夾為準，不要在聊天裡重複輸出分析／計畫／TASK 清單，一句話
回報完成狀態即可。

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
4. 依下方「更新既有的 OpenSpec Change」與「OpenSpec 產出規則」更新規格文件（維持章節結構，不可整段刪除某章節）；
   強制三項若被意見改到就一併改寫，沒被改到也不可刪掉

{_CHANGE_SETUP_EXISTING}

{_ANALYZE_PROHIBITIONS}

## 最終輸出

規格內容以既有 OpenSpec change 資料夾為準，不要在聊天裡重複輸出分析／計畫／TASK 清單，一句話
回報完成狀態即可。

{_QUESTION_PROTOCOL}

請用繁體中文回答。
"""

_BANNER = "\033[1;34m"
_RED    = "\033[1;31m"
_YELLOW = "\033[1;33m"
_RESET  = "\033[0m"

_MAX_QUESTIONS = 15
_MAX_VALIDATE_RETRIES = 5


_QUESTION_LINE_RE = re.compile(r"^\s*" + re.escape(QUESTION_MARKER), re.MULTILINE)
_TASK_CHECKBOX_RE = re.compile(r"^-\s\[[ xX]\]\s*(.+)$", re.MULTILINE)

_KEBAB_INVALID_RE = re.compile(r"[^a-z0-9-]+")
_MULTI_HYPHEN_RE = re.compile(r"-{2,}")


def _sanitize_change_name(raw: str) -> str:
    """轉成 OpenSpec 要求的 kebab-case：小寫字母/數字/單一連字號，去除底線、空白、大寫、
    路徑分隔符、連續連字號與開頭結尾連字號。"""
    s = raw.strip().lower()
    s = s.replace("/", "-")
    s = re.sub(r"[\s_]+", "-", s)
    s = _KEBAB_INVALID_RE.sub("", s)
    s = _MULTI_HYPHEN_RE.sub("-", s)
    return s.strip("-")


def _is_valid_branch_name(name: str) -> bool:
    """git 分支名稱的基本檢查：非空、不含空白、不是 . / ..、不以 - 開頭、不含 ..。"""
    if not name or any(c.isspace() for c in name):
        return False
    if name in (".", "..") or name.startswith("-") or name.endswith("/") or ".." in name:
        return False
    return True


def _read_change_artifacts(project_dir: str, change_name: str) -> tuple[str, list[str]]:
    """規格文件的事實來源是 OpenSpec CLI 自己會驗證的檔案，不是 Claude 聊天回覆：
    analysis 讀 proposal.md 全文，plan 讀 tasks.md 的 checkbox 清單。讀不到則回傳空值，
    由呼叫端視為錯誤。"""
    change_dir = os.path.join(REPO_ROOT, project_dir, "openspec", "changes", change_name)

    analysis = ""
    try:
        with open(os.path.join(change_dir, "proposal.md"), encoding="utf-8") as f:
            analysis = f.read().strip()
    except OSError:
        pass

    plan: list[str] = []
    try:
        with open(os.path.join(change_dir, "tasks.md"), encoding="utf-8") as f:
            plan = _TASK_CHECKBOX_RE.findall(f.read())
    except OSError:
        pass

    return analysis, plan


def _is_question(text: str) -> bool:
    """判斷本輪回應是否包含提問。

    不能只用 startswith 判斷：模型有時會違反「只能輸出 QUESTION 格式」的規則，
    在 QUESTION 前面多輸出分析／計畫草稿等文字。只要文字中任一行以
    QUESTION: 開頭，就視為提問，避免漏判導致跳過互動式選項、直接進入
    human_confirm 的 y/N 關卡。
    """
    return bool(_QUESTION_LINE_RE.search(text))


def _run_with_grilling(prompt: str, tools: str, model: str, timeout: int, resume: str | None = None):
    """執行 call_claude；遇到 QUESTION: 提問時（已由 claude_runner 即時印出）
    立即等待使用者回覆，並以 --resume 延續同一 session 把回答帶回去。

    `resume` 讓呼叫端可以接續一個既有 session（例如 openspec validate 失敗後
    要求修正時），而不是每次都從一個全新 session 開始。
    """
    session_id = resume
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


def _run_with_validate(result, project_dir: str, change_name: str, tools: str, model: str) -> str:
    """驗證迴圈：`openspec validate` 有 error 就把錯誤訊息回傳給同一個 session 修正，
    重試到通過或達上限為止（取代原本要求 Claude 自己在 Bash 裡跑 validate 迴圈）。

    回傳空字串表示驗證通過；否則回傳失敗原因，由呼叫端視為錯誤。
    """
    session_id = result.session_id
    project_dir_abs = os.path.join(REPO_ROOT, project_dir)

    for attempt in range(1, _MAX_VALIDATE_RETRIES + 1):
        validation = validate_change(project_dir_abs, change_name)
        if validation.ok:
            return ""

        print(
            f"{_YELLOW}  [分析+規劃 Agent] openspec validate 發現問題（第 {attempt} 次）：\n"
            f"{validation.error_text}{_RESET}\n",
            flush=True,
        )
        if not session_id:
            return f"openspec validate 失敗且沒有可延續的 session：\n{validation.error_text}"

        fix_prompt = (
            "`openspec validate --strict` 發現以下 error，請修正對應檔案後我會重新驗證，"
            "不需要自己執行 validate：\n\n" + validation.error_text
        )
        result = _run_with_grilling(fix_prompt, tools=tools, model=model, timeout=300, resume=session_id)
        session_id = result.session_id or session_id
        if result.is_error:
            return result.text

    return f"openspec validate 重試 {_MAX_VALIDATE_RETRIES} 次仍未通過"


def _reset_task_checkboxes(project_dir: str, change_name: str) -> None:
    """「重寫」等級時，把 tasks.md 所有 `- [x]` 重設回 `- [ ]`（重寫代表要重新執行整份計畫）。"""
    path = os.path.join(REPO_ROOT, project_dir, "openspec", "changes", change_name, "tasks.md")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return
    reset = re.sub(r"^(-\s)\[[xX]\]", r"\1[ ]", content, flags=re.MULTILINE)
    if reset != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(reset)


def _list_existing_domains(project_dir: str) -> list[str]:
    specs_dir = os.path.join(REPO_ROOT, project_dir, "openspec", "specs")
    if not os.path.isdir(specs_dir):
        return []
    return sorted(
        d for d in os.listdir(specs_dir)
        if not d.startswith(".") and os.path.isdir(os.path.join(specs_dir, d))
    )


def _ask_new_domain_name() -> str:
    """選擇「以上皆非，建立新 domain」後詢問 domain 名稱（選填；留白由 Claude 依任務語意自行命名）。
    呼叫方已確認為互動式環境，不需再做 isatty 檢查。
    """
    print(
        f"\n{_YELLOW}  [分析+規劃 Agent] 新 domain 名稱為何？"
        f"（選填，建議英文 kebab-case；直接 Enter 由 Agent 依任務語意自行命名）：{_RESET}",
        flush=True,
    )
    try:
        return input(f"{_YELLOW}  > {_RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{_YELLOW}  已中止，由 Agent 依任務語意自行命名{_RESET}\n", flush=True)
        return ""


def _ask_domain_selection(project_dir: str) -> tuple[list[str], str]:
    """初始規劃時（僅一次）列出既有 domain，讓使用者選擇本次歸屬哪個（可複選、逗號分隔），
    或選「以上皆非，建立新 domain」。

    回傳 (selected_existing_domains, new_domain_name)：
    - 使用者選擇既有 domain：([domain, ...], "")
    - 使用者選擇「以上皆非」：([], domain_name_or_"")
    - 沒有既有 domain 或非互動式環境：([], "")
    """
    domains = _list_existing_domains(project_dir)
    if not domains:
        return [], ""

    new_idx = len(domains) + 1
    print(f"\n{_YELLOW}  [分析+規劃 Agent] 本次需求歸屬於哪一個既有 domain？{_RESET}", flush=True)
    for i, d in enumerate(domains, 1):
        print(f"{_YELLOW}  {i}. {d}{_RESET}", flush=True)
    print(f"{_YELLOW}  {new_idx}. 以上皆非，建立新 domain{_RESET}", flush=True)
    print(f"{_YELLOW}  （同時涉及多個既有 domain 可用逗號輸入多個編號，例如 1,3）{_RESET}", flush=True)

    if not sys.stdin.isatty():
        print(f"{_YELLOW}  非互動式環境，預設建立新 domain{_RESET}\n", flush=True)
        return [], ""

    while True:
        try:
            answer = input(f"{_YELLOW}  > {_RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{_YELLOW}  已中止，預設建立新 domain{_RESET}\n", flush=True)
            return [], ""
        if not answer:
            continue

        parts = [p.strip() for p in answer.split(",") if p.strip()]
        selected: list[str] = []
        wants_new = False
        valid = True
        for p in parts:
            if p.isdigit():
                idx = int(p)
                if idx == new_idx:
                    wants_new = True
                    continue
                if 1 <= idx <= len(domains):
                    selected.append(domains[idx - 1])
                    continue
                valid = False
                break
            elif p in domains:
                selected.append(p)
                continue
            else:
                valid = False
                break

        if not valid:
            print(f"{_YELLOW}  請輸入清單中的編號{_RESET}", flush=True)
            continue

        if wants_new and selected:
            print(f"{_YELLOW}  「以上皆非」與既有 domain 不可同時選擇{_RESET}", flush=True)
            continue

        if wants_new:
            new_name = _ask_new_domain_name()
            return [], new_name

        return selected, ""


def _drain_stdin() -> None:
    """清除 stdin buffer 中剩餘的輸入，防止使用者貼上多行文字時，
    未被消耗的行混入後續的 input() 呼叫。"""
    try:
        import termios
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass


def _ask_domain_purpose() -> str:
    """本次確定會建立新 domain 時（僅初始規劃）詢問使用者這個 domain 的 Purpose，選填——
    留白（含非互動式環境、使用者中止）就交由 Claude 依當次任務語意自行撰寫，不視為錯誤。

    支援多行貼上：連續兩個空行（Enter Enter）或 Ctrl+D 結束輸入。
    使用「雙空行」而非「單空行」為終止符，允許 Purpose 本文內含有 markdown 段落分隔（單空行）。
    結束後一律 drain stdin，防止剩餘 buffer 行污染後續 grilling 的 input()。
    """
    print(
        f"\n{_YELLOW}  [分析+規劃 Agent] 這是新建立的 domain，若要指定它的 Purpose 請輸入"
        f"（選填；支援多行，貼上後連按兩次 Enter 結束；直接 Enter 由 Agent 依本次任務自行撰寫）：{_RESET}",
        flush=True,
    )
    if not sys.stdin.isatty():
        return ""
    lines: list[str] = []
    consecutive_empty = 0
    try:
        while True:
            line = input(f"{_YELLOW}  > {_RESET}")
            if not line:
                if not lines:
                    # 第一行就是空行 → 使用者選擇略過
                    break
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
                lines.append(line)  # 保留單一空行（markdown 段落分隔）
            else:
                consecutive_empty = 0
                lines.append(line)
    except (EOFError, KeyboardInterrupt):
        if not lines:
            print(f"\n{_YELLOW}  已略過，由 Agent 自行撰寫 Purpose{_RESET}\n", flush=True)
    finally:
        _drain_stdin()
    # 去除結尾空行
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


def _build_new_domain_context(name: str, purpose: str) -> str:
    """依使用者提供的 domain 名稱與 Purpose 組合出適當的提示文字（四種組合）。"""
    if name and purpose:
        return (
            f"使用者已確認本次為建立新 domain，domain 名稱為 `{name}`，"
            f"並指定了它的 Purpose：{purpose}\n\n"
            f"specs/{name}/spec.md 最上面的 `## Purpose` 直接採用使用者這段文字"
            f"（不要自己另外改寫或簡化），並確認 proposal.md 的 `## Intent` 與其對齊。"
        )
    if name:
        return (
            f"使用者已確認本次為建立新 domain，domain 名稱為 `{name}`，視為"
            f"「domain 首次建立」，specs/{name}/spec.md 最上面需加 `## Purpose`"
            f"（與 proposal Intent 對齊）。"
        )
    if purpose:
        return _DOMAIN_CONTEXT_NEW_WITH_PURPOSE.replace("<<DOMAIN_PURPOSE_VALUE>>", purpose)
    return _DOMAIN_CONTEXT_NEW


def _resolve_project_dir() -> str:
    """初始規劃時（僅一次）決定目標專案目錄：workspace 只支援掛載單一目標專案，直接讀
    .env 的 TARGET_PROJECT，不再掃描 workspace 或詢問使用者。缺少環境變數、或對應目錄
    不存在時，回傳空字串，由呼叫端視為錯誤。
    """
    target = os.environ.get("TARGET_PROJECT", "").strip()
    if not target:
        print(f"{_RED}  [分析+規劃 Agent] 缺少環境變數 TARGET_PROJECT{_RESET}\n", flush=True)
        return ""
    if not os.path.isdir(os.path.join(REPO_ROOT, target)):
        print(
            f"{_RED}  [分析+規劃 Agent] TARGET_PROJECT={target} 對應的目錄不存在{_RESET}\n",
            flush=True,
        )
        return ""
    return target


def _ask_branch_name() -> str:
    """任務開始時（僅初始規劃）詢問使用者本次要使用的 git 分支名稱，不可為空。
    非互動式環境或使用者中止時回傳空字串，由呼叫端視為錯誤。"""
    print(
        f"\n{_YELLOW}  [分析+規劃 Agent] 請輸入本次任務要使用的 git 分支名稱"
        f"（必填，例如 feature/add-login；已存在則切過去，不存在則新建）：{_RESET}",
        flush=True,
    )
    if not sys.stdin.isatty():
        print(f"{_RED}  非互動式環境，無法輸入分支名稱{_RESET}\n", flush=True)
        return ""
    while True:
        try:
            answer = input(f"{_YELLOW}  > {_RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{_RED}  已取消，分支名稱為必填{_RESET}\n", flush=True)
            return ""
        if not answer:
            print(f"{_YELLOW}  不可為空，請重新輸入{_RESET}", flush=True)
            continue
        if not _is_valid_branch_name(answer):
            print(
                f"{_YELLOW}  分支名稱不合法（不可含空白、不可為 . / ..、不可以 - 開頭），請重新輸入{_RESET}",
                flush=True,
            )
            continue
        return answer


def analyze_plan_node(state: AgentState) -> dict:
    review_result = state.get("review_result", "")
    review_level = state.get("review_level", "") or "修補"
    human_feedback = state.get("human_feedback", "")
    is_replan = bool(review_result)
    is_human_revise = bool(human_feedback) and not is_replan

    change_name = state.get("change_name", "")
    branch_name = state.get("branch_name", "")
    project_dir = state.get("project_dir", "")

    def _fail(analysis: str) -> dict:
        return {
            "status": "error",
            "analysis": analysis,
            "plan": [],
            "change_name": change_name,
            "branch_name": branch_name,
            "project_dir": project_dir,
        }

    # Guard: 初始規劃已完成，不可再次執行初始規劃（只允許重新規劃或修補）
    if not is_replan and not is_human_revise and state.get("analysis"):
        print(
            f"{_RED}  [分析+規劃 Agent] 此 change 已完成初始規劃，"
            f"不可重複執行初始規劃（僅允許重新規劃或修補）{_RESET}\n",
            flush=True,
        )
        return _fail("此 change 已完成初始規劃，不可重複執行初始規劃")

    # Guard: review_blocking=True 但 review_result 為空 → 狀態不一致，無法重新規劃
    # human_feedback 提供的人工修補不依賴 review_result，不受此 guard 限制
    if not is_human_revise and state.get("review_blocking") and not review_result:
        print(
            f"{_RED}  [分析+規劃 Agent] review_blocking=True 但 review_result 為空，"
            f"無法執行重新規劃{_RESET}\n",
            flush=True,
        )
        return _fail("review_result 為空，無法重新規劃")

    model = _MODEL
    domain_context_value = ""

    if is_replan:
        label = f"重新規劃（{review_level}）"
        tools = "revise"  # 要 Edit 既有規格文件；rollback／validate 已由系統處理，不需 Bash
    elif is_human_revise:
        label = "依人工意見調整計畫"
        tools = "revise"  # 同樣要 Edit 既有規格文件
    else:
        label = "初始規劃"
        tools = "plan"  # 只新增規格文件，不需要 Edit 或 Bash
        if not branch_name:
            branch_name = _ask_branch_name()
            if not branch_name:
                return _fail("未提供 git 分支名稱，無法繼續規劃")
            change_name = _sanitize_change_name(branch_name)
            if not change_name:
                return _fail(f"分支名稱「{branch_name}」無法轉成 OpenSpec change name")

        if not project_dir:
            project_dir = _resolve_project_dir()
            if not project_dir:
                return _fail("無法決定目標專案目錄，無法繼續規劃")

    if not branch_name:
        print(f"{_RED}  [分析+規劃 Agent] 缺少 branch_name{_RESET}\n", flush=True)
        return _fail("缺少 branch_name")

    if project_dir:
        ok, msg = ensure_on_branch(project_dir, branch_name)
        print(f"{_YELLOW}  [git] {msg}{_RESET}", flush=True)
        if not ok:
            return _fail(f"無法切換到分支 {branch_name}：{msg}")

    if is_replan and review_level == "重寫":
        ok, msg = rollback_except_openspec(project_dir)
        print(f"{_YELLOW}  [git] {msg}{_RESET}", flush=True)
        if not ok:
            return _fail(f"rollback 失敗：{msg}")

    if not is_replan and not is_human_revise:
        project_dir_abs = os.path.join(REPO_ROOT, project_dir)

        init_result = ensure_initialized(project_dir_abs)
        if not init_result.ok:
            print(f"{_RED}  [分析+規劃 Agent] openspec init 失敗：{init_result.error_text}{_RESET}\n", flush=True)
            return _fail(f"openspec init 失敗：{init_result.error_text}")

        domains, new_domain_name = _ask_domain_selection(project_dir)
        if domains:
            domain_context_value = _DOMAIN_CONTEXT_EXISTING.replace(
                "<<DOMAIN_LIST_VALUE>>", "、".join(domains)
            )
        else:
            domain_purpose = _ask_domain_purpose()
            domain_context_value = _build_new_domain_context(new_domain_name, domain_purpose)

        change_result = ensure_change_created(project_dir_abs, change_name)
        if not change_result.ok:
            print(
                f"{_RED}  [分析+規劃 Agent] openspec new change 失敗：{change_result.error_text}{_RESET}\n",
                flush=True,
            )
            return _fail(f"openspec new change 失敗：{change_result.error_text}")

    print(f"\n{_BANNER}{'═'*50}\n  [分析+規劃 Agent] 開始 — {label}\n{'═'*50}{_RESET}\n", flush=True)

    start = time.monotonic()

    try:
        skills_block = build_skills_block(_SKILLS_REPLAN if is_replan else _SKILLS)

        project_context = build_project_doc_hint_for(project_dir)

        if is_replan:
            review_ctx = review_result
            if len(review_ctx) > 3000:
                review_ctx = review_ctx[-3000:]
            system = (
                _SYSTEM_REPLAN
                .replace("<<PROJECT_CONTEXT>>", project_context)
                .replace("<<REVIEW_CONTEXT>>", review_ctx)
                .replace("<<REVIEW_LEVEL>>", review_level)
                .replace("<<PROJECT_DIR_VALUE>>", project_dir)
                .replace("<<CHANGE_NAME_VALUE>>", change_name)
                .replace("<<BRANCH_NAME_VALUE>>", branch_name)
            )
        elif is_human_revise:
            system = (
                _SYSTEM_HUMAN_REVISE
                .replace("<<PROJECT_CONTEXT>>", project_context)
                .replace("<<HUMAN_FEEDBACK>>", human_feedback)
                .replace("<<PROJECT_DIR_VALUE>>", project_dir)
                .replace("<<CHANGE_NAME_VALUE>>", change_name)
                .replace("<<BRANCH_NAME_VALUE>>", branch_name)
            )
        else:
            system = (
                _SYSTEM_INITIAL
                .replace("<<PROJECT_CONTEXT>>", project_context)
                .replace("<<PROJECT_DIR_VALUE>>", project_dir)
                .replace("<<DOMAIN_CONTEXT_VALUE>>", domain_context_value)
                .replace("<<CHANGE_NAME_VALUE>>", change_name)
                .replace("<<BRANCH_NAME_VALUE>>", branch_name)
            )

        prompt = f"{system}\n\n{skills_block}\n\n任務：{state['task']}"
        result = _run_with_grilling(prompt, tools=tools, model=model, timeout=300)
    except Exception as e:
        print(f"{_RED}  [分析+規劃 Agent] 發生例外：{e}{_RESET}\n", flush=True)
        return _fail(f"分析階段發生例外：{e}")

    elapsed = time.monotonic() - start

    print(f"\n{_BANNER}{'─'*50}  [分析+規劃 Agent] 完成  {'─'*50}", flush=True)
    print(format_usage_stats(result, elapsed), flush=True)
    print(f"{'─'*50}{_RESET}\n", flush=True)

    if result.is_error:
        print(f"{_RED}  [分析+規劃 Agent] Claude 執行失敗：{result.text}{_RESET}\n", flush=True)
        return _fail(result.text)

    validate_error = _run_with_validate(result, project_dir, change_name, tools, model)
    if validate_error:
        print(f"{_RED}  [分析+規劃 Agent] {validate_error}{_RESET}\n", flush=True)
        return _fail(validate_error)

    if is_replan and review_level == "重寫":
        _reset_task_checkboxes(project_dir, change_name)

    analysis, plan = _read_change_artifacts(project_dir, change_name)
    if not analysis or not plan:
        print(
            f"{_RED}  [分析+規劃 Agent] 讀不到 "
            f"{project_dir}/openspec/changes/{change_name}/ 下的 proposal.md 或 tasks.md{_RESET}\n",
            flush=True,
        )
        return _fail("讀不到 proposal.md 或 tasks.md")

    return {
        "analysis": analysis,
        "plan": plan,
        "status": "pending",
        "review_result": "",
        "review_level": "",
        "review_blocking": False,
        "human_feedback": "",
        "change_name": change_name,
        "branch_name": branch_name,
        "project_dir": project_dir,
    }
