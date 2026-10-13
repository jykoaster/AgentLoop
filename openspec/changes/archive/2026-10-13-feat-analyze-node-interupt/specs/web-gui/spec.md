## MODIFIED Requirements

### Requirement: 中止執行中的階段

The system SHALL 在階段詳情中，於該階段執行中（含等待回覆）時提供「中止」按鈕；使用者確認中止後，系統 MUST 在 10 秒內結束整個執行（含其下所有 Claude 程序），把該階段記為錯誤並註明「使用者中止」；若該階段已取得 Claude session，系統 MUST 保存它，之後重跑該階段時接回同一個 session。新增任務後仍以暫時列呈現的執行，同樣 MUST 在暫時列的 analyze_plan 詳情提供「中止」按鈕，位置、樣式與確認對話框都與正式任務列相同；使用者確認中止後，系統 MUST 在 10 秒內結束整個執行，暫時列隨之從列表消失，「新增任務」按鈕恢復可用。

#### Scenario: 使用者中止執行中的階段後該階段標為錯誤並保留 session 供重跑接回

逐步邏輯：execute 執行中且已取得 Claude session → 使用者點 execute 卡片按「中止」並確認 → 系統結束整個執行 → execute 記為錯誤並註明使用者中止 → 保存 session → 「重跑」與「新增任務」重新可用 → 使用者重跑 execute → 工作流接回同一個 session 續作。

- GIVEN 任務 `feat-login` 的 execute 執行中，已取得 Claude session `abc123`
- WHEN 使用者在 execute 詳情按「中止」並在確認對話框按「確定」
- THEN 10 秒內執行結束，execute 為錯誤（紅），詳情顯示「使用者中止」
- AND analyze_plan、human_confirm 維持完成，review、archive 維持尚未開始
- AND 之後使用者重跑 execute 時，工作流接回 session `abc123` 而非重新開始

#### Scenario: 新增任務的暫時列在 analyze_plan 執行中可中止並結束執行

逐步邏輯：使用者新增任務「新增登入頁」→ 列表出現標題為「新增登入頁」的暫時列，analyze_plan 執行中 → 使用者展開暫時列、點 analyze_plan 卡片 → 詳情底部顯示「中止」按鈕（不論此刻是否有待回覆提問，例如分支名稱提問已回覆、Claude 正在規劃）→ 使用者按「中止」→ 跳出與正式任務列相同的確認對話框「確定要中止這個階段嗎？」→ 按「確定」→ 系統結束整個執行 → 下一次畫面更新時暫時列消失，「新增任務」按鈕恢復可用。

- GIVEN 使用者剛新增任務「新增登入頁」，列表只有該任務的暫時列，analyze_plan 為執行中，該任務尚未留下執行狀態紀錄
- WHEN 使用者在暫時列的 analyze_plan 詳情按「中止」，並在確認對話框按「確定」
- THEN 詳情底部顯示「中止」按鈕，按鈕旁的圖示與文字和正式任務列的「中止」按鈕相同
- AND 確認對話框文字為「確定要中止這個階段嗎？」
- AND 10 秒內執行結束，列表不再顯示標題為「新增登入頁」的暫時列
- AND 「新增任務」按鈕恢復可用
