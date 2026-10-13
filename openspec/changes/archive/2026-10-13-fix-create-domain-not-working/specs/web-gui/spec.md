## ADDED Requirements

### Requirement: 網頁回覆 domain 歸屬提問

The system SHALL 在新增任務的初始提問中，把 domain 歸屬提問以選項題呈現在 analyze_plan 卡片的待回覆提問裡：選項依序為目標專案每個既有 domain，最後一項是「以上皆非，建立新 domain」；每個選項 MUST 以「編號. 文字」的格式顯示，編號從 1 開始連續遞增。使用者按下任一選項按鈕後，工作流 MUST 收到該選項的編號，結果與在終端輸入同一編號相同：選既有 domain 就以該 domain 繼續規劃；選「以上皆非，建立新 domain」就接著出現「新 domain 名稱」文字題。使用者也可以在自訂文字輸入框輸入以逗號分隔的多個既有 domain 編號，一次選多個 domain。

#### Scenario: 點擊建立新 domain 選項後接著詢問新 domain 名稱

逐步邏輯：使用者新增任務 → 回覆分支名稱與是否撰寫 spec → analyze_plan 卡片出現 domain 歸屬選項題 → 詳情顯示「1. web-gui」「2. 以上皆非，建立新 domain」兩個按鈕 → 使用者按「2. 以上皆非，建立新 domain」→ 系統把「2」交給工作流 → 工作流認出 2 是建立新 domain 的編號 → analyze_plan 卡片的待回覆提問換成「新 domain 名稱為何？」文字題 → 使用者輸入「billing」送出 → 工作流把本次需求當成新 domain「billing」繼續規劃。

- GIVEN 目標專案只有一個既有 domain「web-gui」，analyze_plan 正在詢問本次需求歸屬於哪一個 domain
- WHEN 使用者點擊 analyze_plan 卡片並按下「2. 以上皆非，建立新 domain」按鈕
- THEN 按下前詳情顯示的選項按鈕依序為「1. web-gui」「2. 以上皆非，建立新 domain」
- AND 工作流收到的回答為「2」，與在終端輸入「2」的效果相同
- AND 待回覆提問接著換成「新 domain 名稱為何？」文字題，不再重新出現 domain 歸屬題

#### Scenario: 點擊既有 domain 選項後以該 domain 繼續規劃

逐步邏輯：analyze_plan 詢問 domain 歸屬 → 詳情顯示「1. auth」「2. billing」「3. 以上皆非，建立新 domain」→ 使用者按「2. billing」→ 系統把「2」交給工作流 → 工作流把本次需求歸到 billing → 不再詢問新 domain 名稱，analyze_plan 繼續規劃。

- GIVEN 目標專案的既有 domain 為「auth」「billing」，analyze_plan 正在詢問 domain 歸屬
- WHEN 使用者按下「2. billing」按鈕
- THEN 工作流收到的回答為「2」，本次需求歸屬於 billing
- AND 不出現新 domain 名稱提問

#### Scenario: 以自訂文字輸入多個編號同時選擇多個既有 domain

逐步邏輯：analyze_plan 詢問 domain 歸屬，選項為「1. auth」「2. billing」「3. 以上皆非，建立新 domain」→ 使用者在自訂文字輸入框輸入「1,2」送出 → 工作流收到「1,2」→ 本次需求同時歸屬於 auth 與 billing。

- GIVEN 目標專案的既有 domain 為「auth」「billing」，analyze_plan 正在詢問 domain 歸屬
- WHEN 使用者在自訂文字輸入框輸入「1,2」並送出
- THEN 本次需求同時歸屬於 auth 與 billing，analyze_plan 繼續規劃
