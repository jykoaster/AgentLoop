# Design: 階段詳情移入任務列並提供任務列收合

## Technical Approach

- `web/frontend/src/components/active-changes/ChangeRow.vue`
  - 新增 `const selectedStage = ref<string | null>(null)`、`const collapsed = ref(false)`。
  - `openStage(stage)` 改為 `selectedStage.value = stage`；移除 `open-stage` emit 宣告。
  - 新增 `const question = computed(() => selectedStage.value && hasQuestion(selectedStage.value) ? props.runStatus.question : null)`（比對規則與現行 `ActiveChanges.questionFor` 相同：run active、question.stage 相符、`change_name || ''` 相符）。
  - 模板：標題列外層改 `flex items-start justify-between`，左側沿用現有 change 名稱／分支／任務／迭代，右側新增
    `<button type="button" class="collapse-toggle btn-secondary px-2 py-1.5 text-sm" :title :aria-label :aria-expanded="!collapsed" @click="collapsed = !collapsed">`，圖示 `chevron-up`（展開時，標籤「收合」）／`chevron-down`（收合時，標籤「展開」）。暫時列也顯示此按鈕。
  - `<template v-if="!collapsed">` 包住卡片 grid、`.stage-detail-panel`、檢視規格文件按鈕。順序：卡片 grid → 詳情面板 → 檢視規格文件按鈕（詳情緊接在卡片下方）。
  - `.stage-detail-panel` 沿用 `ActiveChanges` 現有樣式與紅色關閉按鈕（`aria-label="關閉"`、`title="關閉"`、`text-danger`），點擊設 `selectedStage = null`；內含 `<StageDetail :change-name="row.change_name" :stage="selectedStage" :question="question" />`。面板在任務列卡片內，外框可改輕量（如 `border border-line rounded-lg p-4`，去除 `shadow-lg`），保留 `stage-detail-panel` class 供測試定位。
- `ActiveChanges.vue`：移除 `selected`、`questionFor`、`onOpenStage`、底部 `.stage-detail-panel`、`StageDetail` import，以及兩個 `<ChangeRow>` 上的 `@open-stage`。
- `src/icons.ts`：新增 `faChevronUp`、`faChevronDown`（`setup.ts` 共用同一份清單，測試可斷言 `svg[data-icon="chevron-up"]`）。
- 狀態保留：`ChangeRow` 以 `:key="row.change_name"` 渲染，輪詢只替換 `rows` 陣列內容，Vue 依 key 重用元件實例，`selectedStage`／`collapsed` 不會重設。暫時列（`tempRow`）在 analyze_plan 寫出 change 名稱後會被正式列取代，其本地狀態隨之消失，可接受。

## Architecture Decisions

### Decision: 詳情與收合狀態由各任務列自行持有

由 `ChangeRow` 內部 `ref` 持有，而非在 `ActiveChanges` 維護 `Map<changeName, stage>`。每列各自最多一個詳情、彼此獨立，正好對應元件邊界；也省去 emit/props 往返。代價是狀態無法跨頁面重新整理保留，與需求一致（不持久化）。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫**：`mount(ActiveChanges)`（`vi.mock('../api')`），以使用者操作（點 `.stage-card`、點 `[aria-label="收合"]`／`[aria-label="展開"]`／`[aria-label="關閉"]`）並在 `[data-change-name="..."]` 範圍內斷言 `.stage-detail-panel`、`.stage-card`、檢視規格文件按鈕是否存在，以及 `getStageDetail` 被呼叫的 change/stage 參數。
- **次要接縫**：無（`StageDetail.spec.ts` 既有測試不受影響）。

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| 兩列 `feat-login`、`fix-css`，點 `feat-login` 的 review 卡片 | 詳情出現在 `feat-login` 列內，`fix-css` 列無詳情；全頁 1 個詳情 | `[data-change-name="feat-login"] .stage-detail-panel` 存在；`[data-change-name="fix-css"] .stage-detail-panel` 不存在；`getStageDetail('feat-login','review')` |
| 接著點 `fix-css` 的 execute 卡片 | 兩列各有一個詳情 | 全頁 `.stage-detail-panel` 數量 2 |
| 接著點 `feat-login` 的 analyze_plan 卡片 | `feat-login` 詳情切換為 analyze_plan，全頁仍 2 個 | `getStageDetail('feat-login','analyze_plan')`；數量 2 |
| 點 `fix-css` 詳情內「關閉」 | 只 `fix-css` 詳情消失 | `fix-css` 列無 `.stage-detail-panel`、`feat-login` 仍有 |
| 點 `feat-login` 標題列「收合」 | 該列只剩標題列；按鈕變「展開」 | 列內 `.stage-card`、`.stage-detail-panel`、`[aria-label="檢視規格文件"]` 不存在；`.change-name` 仍在；`[aria-label="展開"]` 有 `chevron-down` 圖示 |
| 收合後經過一次輪詢（`getChanges` 再 resolve） | 仍為收合 | 同上 |
| 點「展開」 | 卡片、檢視規格文件按鈕、原 analyze_plan 詳情恢復 | `.stage-card` 數量 5；`.stage-detail-panel` 存在 |
| analyze_plan 有待回覆提問，點該列 analyze_plan 卡片 | 列內詳情顯示提問 | 詳情內出現問題全文（沿用既有「驚嘆號並可在詳情中回覆」測試，改在列內範圍斷言） |

## Technical Debt & Follow-up Notes

`openspec/specs/web-gui/spec.md` 的「階段詳情」「純圖示按鈕」Requirement 未描述詳情位置與收合按鈕（本次依使用者決定 `skip_specs: true`）；若日後要把位置與收合納入規格契約，需另開 change 補 MODIFIED delta（純圖示按鈕清單加入「收合／展開」）。
