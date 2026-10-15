# Tasks

## 1. 測試先行（紅）

- [x] 1.1 在 `web/frontend/src/__tests__/ActiveChanges.spec.ts` 新增測試「點擊階段卡片後詳情展開在該任務列卡片下方且各列可各自展開一個」：兩列 `feat-login`／`fix-css`，依 design.md 測試矩陣前四列驗證列內位置、跨列並存、同列切換、關閉只影響該列
- [x] 1.2 新增測試「任務列收合後只保留標題列且展開後恢復原詳情」：依 design.md 測試矩陣收合／輪詢後仍收合／展開恢復三列驗證，並斷言按鈕 `aria-label`/`title` 為「收合」「展開」與 `chevron-up`/`chevron-down` 圖示
- [x] 1.3 調整既有測試「純圖示按鈕以滑鼠停留提示與無障礙名稱呈現原本文字」與「階段等待人工回覆時卡片顯示驚嘆號並可在詳情中回覆」等以 `.stage-detail-panel` 定位詳情的斷言，改在對應 `[data-change-name]` 任務列範圍內查找；確認測試此時為紅燈的部分符合預期

## 2. 實作（綠）

- [x] 2.1 `src/icons.ts` 註冊 `faChevronUp`、`faChevronDown`
- [x] 2.2 `ChangeRow.vue` 新增 `selectedStage`、`collapsed` 狀態與 `question` computed，卡片點擊改為設定 `selectedStage`，移除 `open-stage` emit
- [x] 2.3 `ChangeRow.vue` 模板：標題列右側加收合純圖示按鈕（含暫時列）；`v-if="!collapsed"` 包住卡片 grid → `.stage-detail-panel`（紅色關閉按鈕 + `StageDetail`）→ 檢視規格文件按鈕
- [x] 2.4 `ActiveChanges.vue` 移除 `selected`、`questionFor`、`onOpenStage`、底部詳情面板、`StageDetail` import 與 `@open-stage` 綁定
- [x] 2.5 於 `web/frontend/` 執行 `npx vitest run` 與 `npm run build`，全部通過

## 3. 文件同步

- [x] 3.1 更新 `ARCHITECTURE.md` 前端段落：階段詳情由 `ChangeRow` 在列內渲染、各列持有選中階段與收合狀態；純圖示按鈕清單加入「收合／展開」
- [x] 3.2 更新 `README.md` 網頁操作說明（約第 65 行）：點卡片於該任務列下方展開詳情、標題列右側按鈕可收合任務列
