# Proposal: 階段詳情移入任務列並提供任務列收合

## Intent

規範目的：讓使用者在「執行中任務」分頁中，點擊某任務列的階段卡片後，階段詳情直接展開在**該任務列區塊內、階段卡片下方**，而不是統一出現在整個列表最底下；使用者不必捲到頁尾找詳情，也能一眼看出詳情屬於哪個任務。另外每個任務列標題列右側提供一個收合／展開按鈕，任務多時可把不關心的任務收成只剩標題列，畫面更精簡。

規範背景：目前全頁只有一個共用的詳情面板，固定渲染在所有任務列與新增任務按鈕之後；任務一多，點上方任務的卡片後詳情出現在很遠的頁尾，且同時只能看一個任務的詳情。

輸出要求（可觀察行為，本次 `skip_specs: true`，不寫 specs delta，於此與 design.md 記錄）：

- 階段詳情 MUST 出現在被點擊卡片所屬任務列區塊內、五張階段卡片列的下方（「檢視規格文件」按鈕位置見 design.md）；不再出現在列表之外。
- 每個任務列各自最多展開一個階段詳情；多個任務列可同時各自展開。點同列另一張卡片 → 該列詳情切換為新階段；點同一張已展開的卡片 → 不變。
- 詳情保留既有紅色純圖示「關閉」按鈕（提示與無障礙名稱「關閉」），點擊後只關閉該列詳情。
- 每個任務列（含新增任務後尚無 change 名稱的暫時列）標題列最右側有一個純圖示收合按鈕：展開狀態下無障礙名稱與提示為「收合」、圖示朝上箭頭；收合狀態下為「展開」、圖示朝下箭頭。
- 收合後該任務列只保留標題列（change 名稱、分支、任務描述、迭代次數與收合按鈕），隱藏五張階段卡片、「檢視規格文件」按鈕與已展開的階段詳情；再按一次展開，恢復卡片與按鈕，若收合前有展開的詳情則一併恢復同一階段。
- 預設為展開；收合狀態與已展開的詳情只存在目前頁面，2 秒輪詢更新資料時 MUST 保持不變，重新整理頁面後回到預設（全部展開、無詳情）。

範例及解釋：

1. 頁面有 `feat-login` 與 `fix-css` 兩列 → 使用者點 `feat-login` 的 review 卡片 → `feat-login` 列內卡片下方展開 review 詳情（審查等級、報告、日誌），`fix-css` 列不變。
2. 再點 `fix-css` 的 execute 卡片 → `fix-css` 列內展開 execute 詳情，`feat-login` 的 review 詳情仍在。
3. 點 `feat-login` 的 analyze_plan 卡片 → `feat-login` 列詳情切換為 analyze_plan；全頁仍只有兩個詳情。
4. 按 `feat-login` 標題列右側「收合」→ 該列只剩標題列，按鈕變為「展開」；2 秒後輪詢更新，仍維持收合。
5. 按「展開」→ 五張卡片、檢視規格文件按鈕與 analyze_plan 詳情恢復顯示。
6. 按 `fix-css` 詳情的紅色「關閉」→ 只有 `fix-css` 的詳情消失。

## Scope

In scope:

- 階段詳情由 `ActiveChanges` 底部的共用面板移到各 `ChangeRow` 內、卡片列下方，選中階段狀態改由各任務列自己持有
- 每個任務列標題列右側新增收合／展開純圖示按鈕與收合狀態
- 待回覆提問的判定（`questionFor`）隨詳情一起移入任務列
- 新增 chevron 圖示註冊、更新/新增前端元件測試
- 同步更新 `ARCHITECTURE.md` 前端段落與 `README.md` 網頁操作說明

Out of scope:

- 後端 API、`StageDetail` 元件內容與輪詢邏輯不變
- 已封存任務分頁、既有 Spec 分頁不變
- 收合狀態不持久化（不寫 localStorage、不寫後端）
- 「全部收合／全部展開」等批次操作
- `openspec/specs/web-gui/spec.md` 不寫 delta（`skip_specs: true`，使用者已決定）

## Approach

在 `ChangeRow.vue` 內新增 `selectedStage: ref<string | null>` 與 `collapsed: ref(false)`；`StageCard` 的 click 直接設定 `selectedStage`，不再往上 emit `open-stage`。卡片列之下以 `v-if="selectedStage"` 渲染原本 `ActiveChanges` 裡的 `.stage-detail-panel`（含紅色關閉按鈕與 `StageDetail`），`question` 由 `runStatus` 計算（沿用 `hasQuestion` 的比對規則回傳 `runStatus.question`）。標題列改為左右排列，右側放純圖示收合按鈕（`chevron-up`／`chevron-down`，`aria-label`/`title` 為「收合」／「展開」）；`collapsed` 為 true 時以 `v-if` 隱藏卡片列、檢視規格文件按鈕與詳情，但不清空 `selectedStage`，以便展開後恢復。`ActiveChanges.vue` 移除 `selected`、`onOpenStage`、`questionFor` 與底部面板。`ChangeRow` 以 `row.change_name` 為 key，輪詢替換 `rows` 時元件實例保留，狀態因而不受輪詢影響。詳見 design.md。
