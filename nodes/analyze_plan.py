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
]

# 重新規劃（review 觸發）：只針對 review 結果 grill，不重跑 domain-modeling 文件同步，
# 不需要注入其完整內容（省下的是 skill_loader 白名單裡最大的一塊）
_SKILLS_REPLAN = [
    "grilling",
    "tdd",
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

_SPECINE_ALIGNMENT = """## Specine 規格對齊（grill 結果與規格正文）

規格必須讓後續實作 LLM 對齊使用者目的，而不是只複述任務原句。內容涵蓋 Specine 的十項對齊要素；其中下列三項為**強制、規格裡一定要有具體內容**（即使任務只有一句話，也必須寫出可執行的細節），其餘七項依任務適用才納入、不適用不必硬湊。

### 強制三項（缺一不可）

1. **規範目的（Specification Purpose）**：強調本改動的詳細目標或核心任務，讓實作始終專注預期目標、降低偏離所需功能。
   - 寫在 `proposal.md` 的 `## Intent`。新建 domain 時，`specs/<domain>/spec.md` 的 `## Purpose` 與 Intent 對齊、不要另寫一套目標。
2. **輸出要求（Output Requirements）**：強調可觀察輸出的資料類型、格式與約束（例如必顯欄位、精確度、分隔符號、排序規則、狀態列舉）。
   - 寫進對應 Requirement 的 SHALL/MUST，以及每個主路徑 Scenario 的 THEN。
3. **範例及解釋（Examples with Explanations）**：提供測試案例的逐步分析，詳細闡述從輸入到輸出的邏輯，讓實作 LLM 看懂程式設計邏輯。
   - 寫進 Scenario：不得只重述 Requirement。至少一個主路徑 Scenario 要逐步寫清「誰做了什麼 → 系統如何處理 → 使用者看到什麼」。
   - 若有 `design.md`，測試案例矩陣須與這些逐步範例對齊。

任務只有「幫我實作一個購物車功能」時，規格仍必須具體寫出例如：
- 範例及解釋：購物車透過點擊商品頁「加入購物車」加入；畫面顯示目前已加入的商品；重新登入後仍看得到購物車。
- 規範目的：讓使用者一目瞭然看到所有商品價格、數量，並前往結帳頁面。
- 輸出要求：必須顯示物品名稱、數量、結帳按鈕。

### 其餘七項（適用才寫，不適用可省略）

4. **規範背景（Specification Background）**：問題脈絡、動機、領域知識 → 補在 Intent（目的之後）或 Approach
5. **關鍵概念（Key Concepts）**：關鍵詞彙定義 → 依 domain-modeling 記錄；Scenario 用詞必須與之一致
6. **輸入要求（Input Requirements）**：輸入的型別、格式、範圍、前置條件 → Scenario 的 GIVEN/WHEN
7. **邊界／極端案例（Edge/Corner Cases）**：異常或邊界 → 額外 Scenario，不可只靠主路徑
8. **APIs**：相關外部 API／函式庫名稱與用途 → Approach 或 `design.md` 的 Technical Approach
9. **錯誤處理（Error Handling Requirements）**：無效輸入時的預期行為（預設值、例外、特殊機制）→ 獨立 Requirement 或錯誤 Scenario
10. **提示或建議（Hints or Tips）**：建議演算法、資料結構、既有模組 → Approach / `design.md`；不可用來取代強制三項

純重構／文件／設定且 `skip_specs: true` 時：Intent 仍須寫規範目的；輸出要求與範例及解釋可註明「無外部可觀察行為變化」。"""

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

_OPENSPEC_ARTIFACT_RULES = f"""## OpenSpec 產出規則（規格文件的實際格式）

規格文件不寫成單一 Markdown 檔案，而是遵照 OpenSpec 的 change 資料夾格式，寫在目標專案的
`openspec/changes/<change-name>/` 底下。章節結構維持 OpenSpec，**不要另開「Specine」專章**；
把對齊要素寫進既有欄位（對照見下方「Specine 規格對齊」）。

{_SPECINE_ALIGNMENT}

自檢：強制三項是否已落在對應欄位且非任務原句複述；其餘七項適用者是否已納入，缺一項就補寫。

### proposal.md
`## Intent`（規範目的，適用時補規範背景）/ `## Scope`（In scope / Out of scope）/
`## Approach`（適用時寫相關 APIs、建議演算法／資料結構／既有模組）

### design.md（小改動可略過，採 OpenSpec 預設）
符合以下情況可整份略過、不要建立空的 design.md：改動範圍小、沒有新的架構決策、沒有新的測試 seam 需要說明、也沒有要記錄的技術債。有架構取捨、新模組／接縫、或需要留下技術債時才寫。一旦撰寫，`## Technical Approach` / `## Architecture Decisions` / `## Testing Strategy`（含「Seam（測試接縫）」「測試案例矩陣（Test Matrix）」固定小節，矩陣須涵蓋主路徑逐步範例）/ `## Technical Debt & Follow-up Notes` 四個小節都要保留標題，沒有內容也要填「無」，不可留白或整段刪除。

### specs/<domain>/spec.md（delta，可能有多個 domain，各自建一個檔案）
只描述本次「改了什麼」，不是整份系統規格：`## ADDED Requirements` / `## MODIFIED Requirements` /
`## REMOVED Requirements` 三種分節，每個 `### Requirement:`（SHALL/MUST/SHOULD）底下至少一個
`#### Scenario:`（逐步邏輯 + GIVEN/WHEN/THEN）。規則：
- 先用 Read/Grep 讀 `<project_dir>/openspec/specs/<domain>/spec.md`（已合併進主規格的既有內容，不是這次 change 自己的 delta 檔案），逐一分析既有 Requirement 的規範範圍——不是只比對標題或關鍵字：本次要規範的行為若與某個既有 Requirement 完全相同、或屬於同一件事可以合併進去（而不是另開一個涵蓋範圍重疊的新 Requirement），就用 `MODIFIED Requirements` 改寫該 Requirement（須含合併後完整的新版本內容 + 一行說明改了什麼）；找不到可合併或重複的既有 Requirement，才用 `ADDED Requirements` 視為新規則。domain 首次建立時該檔案還不存在，一律視為 ADDED
- Requirement 與 Scenario 標題（`### Requirement:` / `#### Scenario:`）用抽象、涵蓋規則本身的措辭命名，不要寫死具體數量或列舉值：寫死的標題（連帶內文）在功能擴充時（例如權限或分頁數量增加）會對不上新情況，被迫另開一個 Requirement/Scenario，而不是原本的規則自然涵蓋。
  錯誤：`Scenario: user 端兩個權限皆為 true 時兩個子分頁都顯示`；正確：`Scenario: 登入者具備全部受管功能時顯示對應開關`
- 每個 Requirement 只講一件事、一個 SHALL/MUST/SHOULD；不要把好幾個「而且」塞進同一個 Requirement
- 每個 Requirement 至少要有一個 Scenario；Scenario 要測到具體情境（含邊界/錯誤情況），不是重述 Requirement
- 涉及使用者可觀察行為的 change：主路徑 Scenario 須含「逐步邏輯」、THEN 須含輸出要求（見上方 Specine 對齊強制三項），不可只寫「購物車可用」這類空泛結果
- Requirement 與 Scenario（含逐步邏輯）都只能用自然語言描述規範（系統對外呈現的行為與約束），
  不寫實作細節——不限特定技術棧，泛指任何屬於「怎麼做到」而非「對外呈現什麼」的內容：不寫具體程式碼
  片段或條件式（例如 `a.b === true`）、不點名元件／模組／類別／函式／變數名稱、不使用框架特定的
  生命週期或渲染機制用語（掛載、mount、render、re-render 等）、不寫 DOM 屬性／CSS selector／
  資料庫欄位型別／SQL／特定框架 API。判斷依據一律換成使用者或系統看得到的業務語言（例如「具備某項
  權限」而不是引用實際的欄位與比較式）；實作方式（用什麼元件、屬性、條件判斷式達成）留給 design.md
  的 Technical Approach。
  錯誤：`THEN 該 a-textarea 的 DOM maxlength 屬性為 1024`；正確：`THEN 字元計數以 1024 為上限` + `AND 使用者無法讓該欄位保留超過 1024 字`
  錯誤：`逐步邏輯：系統依 selfInformation.allowOriginAuth === true 判定...使用者點擊後 OriginAuthModule 才會被掛載並發出請求`；
  正確：`逐步邏輯：系統依登入者是否具備回源鑒權權限判定...使用者點擊該分頁後，右側才顯示回源鑒權模組的列表內容`
- 適用時另寫邊界／錯誤 Scenario（Edge/Corner Cases、Error Handling），不可只靠主路徑
- 依下方「目標專案與 Domain」已確認的歸屬：沿用既有 domain 不需要加 `## Purpose`；domain 首次建立才在 delta 檔案最上面加一段 `## Purpose`（一兩句話，與 proposal Intent 的規範目的對齊）
- 不需要獨立的「User Stories」章節——Scenario 已經是驗收條件的正式化版本
- 若本次任務純粹是重構/文件/設定調整、完全沒有外部可觀察行為變化，可以在該 change 的 `.openspec.yaml` 加 `skip_specs: true` 並略過 specs delta；若 REMOVED 移除了某個 domain 的最後一個 Requirement，需在 `.openspec.yaml` 加 `retire_capabilities: true` 才能讓 archive 一併刪除該 domain 的 spec 檔

### tasks.md
`## N. <群組名稱>` + `- [ ] N.M <具體任務>` checkbox，依實作順序階層編號（1.1、1.2...）。
- 涉及新增或修改行為的任務，須額外安排一個對應的「撰寫／更新測試」任務（優先在既有測試 seam 上以 tdd skill 的紅-綠循環進行）；純文件、設定調整或不改變行為的重構可不需要
- 是否需要「更新文件」任務，依該任務所屬專案的 CLAUDE.md / AGENT.md 判斷：若說明檔要求同步維護 docs/ 下的商業邏輯說明文件，安排對應任務（通常放在最後）；未提及此類慣例時不強制新增
- 這份檔案會被執行 Agent 逐項勾選、被審查 Agent 讀取確認完成度，是任務清單的唯一事實來源；不要另外在聊天輸出一份分析／計畫摘要

（完成後系統會自動執行 `openspec validate --strict`；只有 error 等級會擋下並把訊息傳回來給你修正，
warning 可視情況保留、不必為了消除 warning 硬湊內容，你不需要自己執行 validate。）"""

# 檔案骨架範本：只有從零建立新 change 時才需要（僅初始規劃注入）。replan／依人工意見調整都是
# Edit 既有檔案，實際格式直接 Read 現有內容就看得到，注入範本只是白佔 token。
_OPENSPEC_TEMPLATES = """## 新建檔案時的骨架範本（格式規則見上方「OpenSpec 產出規則」）

### proposal.md
```markdown
# Proposal: <Feature/Fix Name>

## Intent
<規範目的（強制，見上方 Specine 對齊第 1 項）；適用時補規範背景>

## Scope
In scope:
- <本次要做的事項>

Out of scope:
- <明確排除、避免範疇蔓延的事項；沒有則寫「無」>

## Approach
<高階解決方案概述；適用時寫入相關 APIs、建議演算法／資料結構／既有模組>
```

### design.md
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
| <案例；須涵蓋主路徑的逐步範例，適用時加邊界／錯誤> | ... | ... |

## Technical Debt & Follow-up Notes
<需追蹤的技術債；沒有則寫「無」>
```

### specs/<domain>/spec.md
```markdown
## ADDED Requirements

### Requirement: <名稱>
The system SHALL/MUST <一個明確、可觀察的行為；含輸出要求（資料類型、格式、約束）>。

#### Scenario: <情境名稱>
逐步邏輯：<從觸發（輸入）到可觀察結果（輸出）的處理步驟>
- GIVEN <前提；適用時含輸入型別／格式／約束>
- WHEN <觸發>
- THEN <結果；必須寫清可觀察輸出的資料類型、格式、約束>

## MODIFIED Requirements
（改變既有行為時使用，須包含完整的新版本內容 + 一行說明改了什麼）

## REMOVED Requirements
（行為被移除時使用，須說明原因）
```

### tasks.md
```markdown
# Tasks

## 1. <群組名稱>
- [ ] 1.1 <具體任務>
- [ ] 1.2 <具體任務>

## 2. <群組名稱>
- [ ] 2.1 <具體任務>
```"""

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

{_OPENSPEC_ARTIFACT_RULES}

{_OPENSPEC_TEMPLATES}

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

{_OPENSPEC_ARTIFACT_RULES}

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

{_OPENSPEC_ARTIFACT_RULES}

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


def _ask_domain_selection(project_dir: str) -> list[str]:
    """初始規劃時（僅一次）列出既有 domain，讓使用者選擇本次歸屬哪個（可複選、逗號分隔），
    或選「建立新 domain」。回傳選定的既有 domain 名稱清單；空清單表示本次視為建立新
    domain（沒有任何既有 domain、或非互動式環境時也回傳空清單，不中止流程，交由 Claude
    依任務語意自訂新名稱）。
    """
    domains = _list_existing_domains(project_dir)
    if not domains:
        return []

    new_idx = len(domains) + 1
    print(f"\n{_YELLOW}  [分析+規劃 Agent] 本次需求歸屬於哪一個既有 domain？{_RESET}", flush=True)
    for i, d in enumerate(domains, 1):
        print(f"{_YELLOW}  {i}. {d}{_RESET}", flush=True)
    print(f"{_YELLOW}  {new_idx}. 以上皆非，建立新 domain{_RESET}", flush=True)
    print(f"{_YELLOW}  （同時涉及多個既有 domain 可用逗號輸入多個編號，例如 1,3）{_RESET}", flush=True)

    if not sys.stdin.isatty():
        print(f"{_YELLOW}  非互動式環境，預設建立新 domain{_RESET}\n", flush=True)
        return []

    while True:
        try:
            answer = input(f"{_YELLOW}  > {_RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{_YELLOW}  已中止，預設建立新 domain{_RESET}\n", flush=True)
            return []
        if not answer:
            continue

        parts = [p.strip() for p in answer.split(",") if p.strip()]
        selected: list[str] = []
        valid = True
        for p in parts:
            if p.isdigit():
                idx = int(p)
                if idx == new_idx:
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

        if valid:
            return selected
        print(f"{_YELLOW}  請輸入清單中的編號{_RESET}", flush=True)


def _ask_domain_purpose() -> str:
    """本次確定會建立新 domain 時（僅初始規劃）詢問使用者這個 domain 的 Purpose，選填——
    留白（含非互動式環境、使用者中止）就交由 Claude 依當次任務語意自行撰寫，不視為錯誤。
    """
    print(
        f"\n{_YELLOW}  [分析+規劃 Agent] 這是新建立的 domain，若要指定它的 Purpose 請輸入"
        f"（選填，直接 Enter 留白則由 Agent 依本次任務自行撰寫）：{_RESET}",
        flush=True,
    )
    if not sys.stdin.isatty():
        return ""
    try:
        return input(f"{_YELLOW}  > {_RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{_YELLOW}  已略過，由 Agent 自行撰寫 Purpose{_RESET}\n", flush=True)
        return ""


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

        domains = _ask_domain_selection(project_dir)
        if domains:
            domain_context_value = _DOMAIN_CONTEXT_EXISTING.replace(
                "<<DOMAIN_LIST_VALUE>>", "、".join(domains)
            )
        else:
            domain_purpose = _ask_domain_purpose()
            domain_context_value = (
                _DOMAIN_CONTEXT_NEW_WITH_PURPOSE.replace("<<DOMAIN_PURPOSE_VALUE>>", domain_purpose)
                if domain_purpose else _DOMAIN_CONTEXT_NEW
            )

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
