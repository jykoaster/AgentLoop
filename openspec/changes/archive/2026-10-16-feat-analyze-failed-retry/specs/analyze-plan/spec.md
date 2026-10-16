## ADDED Requirements

### Requirement: 規劃失敗後重跑 analyze_plan 重新執行原本的規劃

The system SHALL 在 analyze_plan 失敗後使用者重跑 analyze_plan 時，重新執行失敗當下的那一種規劃。是否進入調整 MUST 以「該任務的 analyze_plan 是否至少成功完成過一次規劃」判定：從未成功完成規劃的任務（例如初始規劃途中失敗）重跑時，系統 MUST 重新執行初始規劃，不詢問調整內容；並 MUST 沿用使用者先前已回答的工作分支、是否撰寫 spec 與 domain 歸屬，不再詢問這些問題（尚未回答過的才詢問）；若上次因中斷留下尚未完成的規劃 session，MUST 接回該 session 續作。初始規劃成功後照原工作流進入人工確認，任務描述 MUST 維持原文，不附加任何「調整 N：」行。依人工意見調整或調整（已輸入調整內容）途中失敗後重跑時，系統 MUST 以同一份修改意見／調整內容重新執行，不詢問調整內容、不附加新的「調整 N：」行。已至少成功完成過一次規劃的任務，若最近一次 analyze_plan 是在詢問調整內容時失敗，重跑時仍依既有規則進入調整。

#### Scenario: 初始規劃失敗後重跑 analyze_plan 重新執行初始規劃且不詢問調整內容

逐步邏輯：使用者新增任務「新增登入頁」→ 回答分支 `feat/login`、要撰寫 spec、domain 選 `auth` → 初始規劃呼叫 Claude 時失敗，analyze_plan 卡片變為錯誤，階段詳情顯示失敗原因 → 使用者在 analyze_plan 卡片按「重跑」並確認 → analyze_plan 變為執行中 → 系統判定此任務從未成功完成規劃，直接以初始規劃重新執行，不出現「請輸入本次要調整的內容」，也不再出現分支名稱、是否撰寫 spec、domain 歸屬的提問 → 規格文件寫在原本的 `openspec/changes/feat-login/` → analyze_plan 完成，human_confirm 出現人工確認提問。

- GIVEN 任務 `feat-login`（分支 `feat/login`、要撰寫 spec、domain `auth`）的初始規劃失敗，analyze_plan 為錯誤，且從未成功完成過規劃
- WHEN 使用者重跑 analyze_plan，且這次規劃成功
- THEN analyze_plan 期間沒有出現「請輸入本次要調整的內容」、分支名稱、是否撰寫 spec、domain 歸屬的待回覆提問，以初始規劃執行
- AND 規格文件寫在原本的 `openspec/changes/feat-login/`，工作分支仍為 `feat/login`
- AND 任務描述仍為「新增登入頁」，沒有附加「調整 1：」
- AND analyze_plan 完成後進入 human_confirm，人工確認提問中的分析摘要為本次產出的提案內容

#### Scenario: 初始規劃因用量上限中斷後重跑接回原 session 續作

逐步邏輯：初始規劃撞到用量上限而中斷，analyze_plan 為錯誤並留下中斷的 session → 用量重置後使用者重跑 analyze_plan → 系統判定任務從未成功完成規劃，以初始規劃接回同一個 session 續作，不詢問調整內容、是否撰寫 spec、domain。

- GIVEN 任務 `feat-login` 的初始規劃因用量上限中斷，留下屬於 analyze_plan 的中斷 session，且從未成功完成過規劃
- WHEN 使用者重跑 analyze_plan
- THEN 系統接回該中斷 session 繼續初始規劃，期間沒有出現調整內容、是否撰寫 spec、domain 歸屬的待回覆提問
- AND 成功後進入 human_confirm，任務描述沒有附加「調整 N：」

#### Scenario: 已完成過規劃的任務調整失敗後重跑仍詢問調整內容

逐步邏輯：任務 `feat-login` 已成功完成規劃 → 使用者重跑 analyze_plan 進行調整，但在調整內容提問時中止，analyze_plan 記為錯誤 → 使用者再次重跑 analyze_plan → 系統判定任務已成功完成過規劃，依然以必填文字題詢問「請輸入本次要調整的內容」。

- GIVEN 任務 `feat-login` 已至少成功完成過一次規劃，最近一次 analyze_plan 因未提供調整內容而為錯誤
- WHEN 使用者重跑 analyze_plan
- THEN analyze_plan 的第一個待回覆提問為必填文字題「請輸入本次要調整的內容」

#### Scenario: 依人工意見調整失敗後重跑 analyze_plan 以同一份修改意見重新執行

逐步邏輯：`feat-login` 完成規劃後在人工確認輸入修改意見「密碼至少 12 碼」→ analyze_plan 依人工意見調整時 OpenSpec 驗證失敗，analyze_plan 記為錯誤 → 使用者重跑 analyze_plan → 系統以同一份修改意見「密碼至少 12 碼」重新執行依人工意見調整，不出現任何提問 → 成功後進入 human_confirm。

- GIVEN `feat-login` 已完成規劃，依人工意見調整（修改意見「密碼至少 12 碼」）途中失敗，analyze_plan 為錯誤
- WHEN 使用者重跑 analyze_plan，且這次調整成功
- THEN analyze_plan 期間沒有任何待回覆提問，送給規劃的修改意見為「密碼至少 12 碼」
- AND 任務描述與重跑前相同，沒有附加新的「調整 N：」行
- AND analyze_plan 完成後進入 human_confirm

## MODIFIED Requirements

### Requirement: 有尚未處理的審查退回時讓使用者選擇規劃方式

The system SHALL 在使用者重跑 analyze_plan、且該任務有尚未處理的審查退回、且最近一次 analyze_plan 不是在依審查結果重新規劃途中失敗時（例如審查退回後工作流因達重試上限而結束），先以選擇題詢問「依審查結果重新規劃」或「輸入調整內容」；選擇前者時 MUST 依審查結果修正規格（與 review 退回時自動重新規劃相同），選擇後者時 MUST 改為詢問調整內容並進入調整。review 退回後由工作流自動進入的重新規劃 MUST 直接依審查結果進行，不出現此選擇題。依審查結果重新規劃途中失敗後重跑 analyze_plan 時，系統 MUST 直接以同一份審查結果重新執行依審查結果重新規劃，不出現此選擇題、不詢問調整內容，任務描述維持不變。

#### Scenario: 審查退回後重跑 analyze_plan 選擇輸入調整內容

逐步邏輯：`feat-login` 的 review 判定需修正，且已達重試上限而結束 → 使用者重跑 analyze_plan → analyze_plan 先出現選擇題，選項為「依審查結果重新規劃」「輸入調整內容」→ 使用者選「輸入調整內容」→ 接著出現必填文字題「請輸入本次要調整的內容」→ 輸入後依調整內容更新規格，任務描述附加「調整 1：…」。

- GIVEN `feat-login` 有尚未處理的審查退回，工作流已結束
- WHEN 使用者重跑 analyze_plan，在選擇題選「輸入調整內容」，再輸入「改用簡訊驗證碼登入」
- THEN 第一個待回覆提問為選擇題，選項依序為「依審查結果重新規劃」「輸入調整內容」
- AND 第二個待回覆提問為必填文字題「請輸入本次要調整的內容」
- AND 任務描述最後一行為「調整 1：改用簡訊驗證碼登入」

#### Scenario: 審查退回後重跑 analyze_plan 選擇依審查結果重新規劃

逐步邏輯：`feat-login` 有尚未處理的審查退回 → 使用者重跑 analyze_plan → 在選擇題選「依審查結果重新規劃」→ 系統依審查結果修正規格，不詢問調整內容 → 任務描述不變。

- GIVEN `feat-login` 有尚未處理的審查退回
- WHEN 使用者重跑 analyze_plan，在選擇題選「依審查結果重新規劃」
- THEN 系統依該次審查結果修正 `openspec/changes/feat-login/` 的規格文件
- AND 選擇題之後沒有調整內容提問，任務描述與重跑前相同

#### Scenario: 依審查結果重新規劃失敗後重跑 analyze_plan 直接重新規劃且不出現選擇題

逐步邏輯：`feat-login` 的 review 判定需修正（等級「修補」）→ 工作流自動進入依審查結果重新規劃 → 重新規劃時 Claude 執行失敗且沒有留下可接回的 session，analyze_plan 記為錯誤，審查退回仍未處理 → 使用者重跑 analyze_plan → 系統判定上次是依審查結果重新規劃失敗，不出現「依審查結果重新規劃／輸入調整內容」選擇題，直接以同一份審查結果重新規劃 → 成功後進入 human_confirm。

- GIVEN `feat-login` 有尚未處理的審查退回，最近一次 analyze_plan 在依審查結果重新規劃途中失敗，且沒有可接回的 session
- WHEN 使用者重跑 analyze_plan，且這次重新規劃成功
- THEN analyze_plan 期間沒有任何待回覆提問（沒有規劃方式選擇題、沒有調整內容提問）
- AND 系統依同一份審查結果修正 `openspec/changes/feat-login/` 的規格文件，任務描述與重跑前相同
- AND analyze_plan 完成後進入 human_confirm
