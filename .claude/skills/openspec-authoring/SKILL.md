# openspec-authoring

撰寫 OpenSpec change 資料夾的規格文件（proposal.md、specs/<domain>/spec.md、tasks.md、design.md）。

## OpenSpec 產出規則（規格文件的實際格式）

規格文件不寫成單一 Markdown 檔案，而是遵照 OpenSpec 的 change 資料夾格式，寫在目標專案的
`openspec/changes/<change-name>/` 底下。章節結構維持 OpenSpec，**不要另開「Specine」專章**；
把對齊要素寫進既有欄位（對照見下方「Specine 規格對齊」）。

## Specine 規格對齊（grill 結果與規格正文）

規格必須讓後續實作 LLM 對齊使用者目的，而不是只複述任務原句。內容涵蓋 Specine 的十項對齊要素；其中下列三項為**強制、規格裡一定要有具體內容**（即使任務只有一句話，也必須寫出可執行的細節），其餘七項依任務適用才納入、不適用不必硬湊。

### 強制三項（缺一不可）

1. **規範目的（Specification Purpose）**：強調本改動的詳細目標或核心任務，讓實作始終專注預期目標、降低偏離所需功能。
   - 寫在 `proposal.md` 的 `## Intent`。新建 domain 的 `## Purpose` 見下方 spec 寫法。
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

純重構／文件／設定且 `skip_specs: true` 時：Intent 仍須寫規範目的；輸出要求與範例及解釋可註明「無外部可觀察行為變化」。

### proposal.md

`## Scope`（In scope / Out of scope）。`## Intent`、`## Approach` 的落點見上方對齊。

### design.md（小改動可略過，採 OpenSpec 預設）

符合以下情況可整份略過、不要建立空的 design.md：改動範圍小、沒有新的架構決策、沒有新的測試 seam 需要說明、也沒有要記錄的技術債。有架構取捨、新模組／接縫、或需要留下技術債時才寫。一旦撰寫，`## Technical Approach` / `## Architecture Decisions` / `## Testing Strategy`（含「Seam（測試接縫）」「測試案例矩陣（Test Matrix）」固定小節，矩陣須涵蓋主路徑逐步範例）/ `## Technical Debt & Follow-up Notes` 四個小節都要保留標題，沒有內容也要填「無」，不可留白或整段刪除。

### specs/<domain>/spec.md（delta，可能有多個 domain，各自建一個檔案）

只描述本次「改了什麼」：`## ADDED Requirements` / `## MODIFIED Requirements` /
`## REMOVED Requirements` 三種分節，每個 `### Requirement:`（SHALL/MUST/SHOULD）底下至少一個
`#### Scenario:`（逐步邏輯 + GIVEN/WHEN/THEN）。

**【核心原則：spec 是正向契約，不是實作差異紀錄】**
spec 只描述「系統保證具備哪些行為」。讀者不知道歷史版本——不提某個行為，就等同於不保證它存在；
不需要、也絕對不可以另外寫 MUST NOT 或負向 Scenario 來宣告它不在。
在任何 Requirement 主文或 Scenario（含逐步邏輯、GIVEN/WHEN/THEN）中，**禁止以下寫法**：

- 描述 UI 元件缺席：`MUST NOT 顯示分頁元件`、`不顯示總筆數說明` 等
- 標題帶有負向語意：`Scenario: 訪問日誌不顯示統計文字`、`Scenario: 沒有分頁控制` 等
- 以「不存在的行為」為主要斷言的 Scenario

MUST NOT 唯一合法用途：描述正向 Scenario 的副作用約束（例：正向 Scenario 是「滑到底載入下一批」，副作用 AND 子句 MUST NOT 在 hasMore=false 後繼續發出請求）。

**【規格來源：以 openspec/specs 為唯一基準，不從 proposal 的 Scope/Approach 翻譯】**
寫 spec 前先用 Read 讀 `<project_dir>/openspec/specs/<domain>/spec.md`（已合併的主規格），逐一比對規範範圍（不只比對標題）。與既有 Requirement 相同或可合併就用 MODIFIED，找不到重疊才用 ADDED：

- 既有 spec 提及的行為，本次要修改 → `MODIFIED Requirements`（改寫成新版正向內容，不附「改了什麼」說明）
- 既有 spec 提及的行為，本次要完全移除 → `REMOVED Requirements`
- 既有 spec 未提及，本次新增 → `ADDED Requirements`
- 既有 spec 未提及，本次從程式碼移除 → **不寫任何條文**（從未 specced，移除不需要 spec 記錄）

`proposal.md` 的 Scope 與 Approach 段描述的是工程任務（HOW），不是規格項目（WHAT）；
禁止把 Scope 的「移除 X 元件」「刪除 Y API call」翻譯成任何 Requirement 或 Scenario。

新建 domain（openspec/specs/<domain>/spec.md 尚不存在）：一律全 ADDED。

**【MODIFIED 的正確做法】**
直接改寫 Requirement 正文，只保留縮減後仍存在的行為（例：移除某開關就從對照表刪那一列，Scenario 改成描述僅剩開關的正向行為）。
集合變大（頁面加一個 tab／欄／按鈕）時：改寫那一條「初始化組成」Scenario，讓 THEN 涵蓋完整新集合。舊標題不再出現於 delta，tasks.md 為它安排移除測試任務。

**【Requirement 與 Scenario 的寫法規則】**

- **先確認消費者視角**：Requirement 和 Scenario 只寫最外層消費者能從邊界外觀察並驗證的事。以「若完全重寫內部實作，這條規格還成立嗎？」自檢——成立 → 驗收標準；不成立 → 移至 design.md。
- **Scenario 對應行為分支，不列舉資料變體**：每個 Scenario 必須對應一個不同的行為結果、政策或約束（通常是不同的 GIVEN 或 WHEN）。同一條規則套不同輸入資料不另開 Scenario，合進範例或 GIVEN 前提。
  **同一觸發只寫一條**：同一 Requirement 底下，第一個 GIVEN 與第一個 WHEN 都相同的 Scenario 必須合併，把所有 THEN 斷言寫在一起。列出同一個集合的成員（tab 列有哪些標籤、表格有哪些欄）是同一條「初始化組成」規則，不是不同分支。
  錯誤（同是「頁面完成初始化」，拆成兩條）：`Scenario: 頁面顯示訪問日誌單一 tab 標籤` + `Scenario: 頁面 tab 列同時包含 OWASP 日誌 tab`
  正確（一條寫完組成與預設選中）：`Scenario: 頁面載入後 tab 列顯示本頁提供的日誌類型且預設選中訪問日誌`
  真正不同分支才另開：例如 `WHEN 使用者點擊另一個 tab`（切換）、`WHEN 使用者切換語系`（標籤文字更新）。
- **標題抽象化**：用涵蓋規則本身的措辭，不寫死具體數量或列舉值（寫死會使功能擴充時標題失效，被迫另開一條而非改寫舊的）
  錯誤：`Scenario: user 端兩個權限皆為 true 時兩個子分頁都顯示`；正確：`Scenario: 登入者具備全部受管功能時顯示對應開關`
  既有標題已寫死「單一／僅含一個／兩個」時，MODIFIED 必須改寫該 Scenario（含標題），禁止另開並列條目。
- **每個 Requirement 只講一件事**；至少一個 Scenario
- **業務語言，不寫實作細節**。凡屬「怎麼做到」而非「對外呈現什麼」的內容，移至 design.md：
  - 禁止：程式碼片段／條件式（`a.b === true`）、元件／模組／類別／函式名稱、框架生命週期用語（mount、re-render 等）、DOM 屬性、CSS selector、特定框架 API
  - **API 欄位名稱（request body、response 欄位、endpoint path）前端消費端禁止寫入 spec**；用業務描述代替，欄位名稱移至 design.md Technical Approach
  - **【例外：後端 API 合約規格】** 若本次變動的交付物本身就是 API 合約（`backend-api` 類型專案，或任務描述明確指出是定義新 endpoint、修改 response schema），則 endpoint path、HTTP method、request／response 欄位名稱是對外承諾、屬於可觀察輸出的一部分，可直接寫入 Requirement 的 SHALL／MUST 與 Scenario 的 THEN；此例外不適用前端消費端。
    錯誤（frontend）：`THEN 該 a-textarea 的 DOM maxlength 屬性為 1024`；正確：`THEN 字元計數以 1024 為上限，使用者無法讓該欄位保留超過 1024 字`
    錯誤（frontend）：`請求本文 MUST 帶 siteIDs、startTime、endTime、pageSize=20`；正確：`首次查詢 MUST 帶入查詢時間範圍與使用者設定的進階篩選條件；每批固定最多 20 筆`
    錯誤（frontend）：`系統依 selfInformation.allowOriginAuth === true 判定`；正確：`系統依登入者是否具備回源鑒權授權判定`
- **每個 Scenario 必須有至少一個名稱完全相同的** `describe` 或 `test`（Scenario 標題即驗收測試名稱）
- 沿用既有 domain 不加 `## Purpose`；domain 首次建立才在 delta 最上面加一段 `## Purpose`（一兩句話，與 proposal Intent 對齊）
- 不需要獨立的「User Stories」章節
- 純重構/文件/設定調整、無外部可觀察行為變化：在 `.openspec.yaml` 加 `skip_specs: true` 並略過 specs delta；REMOVED 移除了某 domain 最後一個 Requirement 時加 `retire_capabilities: true`
- prompt 若有一行 `skip_specs: true` 或 `skip_specs: false`，那是使用者已確認的決定，照辦、不要自行改判。`true` 依上一條略過 specs；`false` 要寫 specs delta，不要設定 `skip_specs: true`。沒有這一行時，才依上一條自行判斷

### tasks.md

`## N. <群組名稱>` + `- [ ] N.M <具體任務>` checkbox，依實作順序階層編號（1.1、1.2...）。

- 涉及新增或修改行為的任務，須額外安排一個對應的「撰寫／更新測試」任務（優先在既有測試 seam 上以 tdd skill 的紅-綠循環進行）；純文件、設定調整或不改變行為的重構可不需要
- **測試改名任務**：spec 完成後 grep 既有測試，凡行為與某 Scenario 相符但名稱不同的測試，安排「將 `<既有測試名稱>` 改名為 `<Scenario 標題>`」任務，**不另開新測試**；既有測試完全不存在才安排撰寫新測試
- **測試刪除任務（必須安排，不可遺漏）**：比對既有 spec.md，凡有測試需要移除的情況均需在 tasks.md 明確列出；兩種觸發情境，格式各別如下：
  - `MODIFIED Requirements`：Requirement 保留但某些 Scenario 標題不再出現於 delta 新版本 → 安排「移除 `<消失的 Scenario 標題>` 測試」任務，以 **Scenario 標題**為準
  - `REMOVED Requirements`：整個 Requirement 被移除 → 安排「移除 `<Requirement 標題>` 相關測試」任務（Requirement 層級），**並**為其下每個 Scenario 各別安排「移除 `<Scenario 標題>` 測試」任務（Scenario 標題即測試函式名稱）
- 是否需要「更新文件」任務，依該任務所屬專案的 CLAUDE.md / AGENT.md 判斷：若說明檔要求同步維護 docs/ 下的商業邏輯說明文件，安排對應任務（通常放在最後）；未提及此類慣例時不強制新增
- 這份檔案會被執行 Agent 逐項勾選、被審查 Agent 讀取確認完成度，是任務清單的唯一事實來源；不要另外在聊天輸出一份分析／計畫摘要

（完成後系統會自動執行 `openspec validate --strict`；只有 error 等級會擋下並把訊息傳回來給你修正，
warning 可視情況保留、不必為了消除 warning 硬湊內容，你不需要自己執行 validate。）

---

## 新建檔案時的骨架範本（格式規則見上方「OpenSpec 產出規則」）

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

| 輸入值 / 情境                                      | 預期結果 | 斷言 Target / Reject Key |
| -------------------------------------------------- | -------- | ------------------------ |
| <案例；須涵蓋主路徑的逐步範例，適用時加邊界／錯誤> | ...      | ...                      |

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

（見上方「MODIFIED 的正確做法」）

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
```
