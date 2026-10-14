## ADDED Requirements

### Requirement: 工作分支不存在時讓使用者選擇起點分支

The system SHALL 在初始規劃取得工作分支名稱後，若該分支在目標專案本地不存在，於 analyze_plan 階段以待回覆提問「要從哪個分支建立 <工作分支>？」列出目標專案全部本地分支：每個選項 MUST 以「編號. 分支名稱」顯示，編號從 1 開始連續遞增，依分支名稱字母順序排列；目前所在分支的選項 MUST 在名稱後加註「（目前分支）」。使用者輸入編號即以該分支為起點分支；直接送出空白回答時 MUST 以目前分支為起點分支；輸入非清單內的編號時 MUST 提示後重新詢問同一題。工作分支已存在於本地時，系統 MUST 直接切換到該分支繼續規劃。

#### Scenario: 工作分支不存在時列出本地分支並以使用者選的分支為起點

逐步邏輯：使用者新增任務 → 輸入工作分支名稱「feat/login」→ 系統發現本地沒有 feat/login → analyze_plan 提問「要從哪個分支建立 feat/login？」並列出「1. develop（目前分支）」「2. main」→ 使用者輸入「2」→ 系統以 main 為起點分支建立 feat/login → 目標專案切換到 feat/login，analyze_plan 接著詢問是否撰寫 spec 等後續問題。

- GIVEN 目標專案本地有 develop、main 兩個分支，目前在 develop，且沒有 feat/login
- WHEN 使用者新增任務並輸入工作分支名稱「feat/login」，在起點分支提問輸入「2」
- THEN 起點分支提問的選項依序為「1. develop（目前分支）」「2. main」
- AND 目標專案建立 feat/login 並切換過去，feat/login 指向 main 的最新版本
- AND analyze_plan 繼續後續規劃提問

#### Scenario: 起點分支提問直接送出空白時以目前分支為起點

逐步邏輯：起點分支提問出現 → 使用者不輸入任何編號直接送出 → 系統採用目前分支 develop 為起點建立工作分支。

- GIVEN 目標專案目前在 develop，工作分支 feat/login 本地不存在，起點分支提問已出現
- WHEN 使用者直接送出空白回答
- THEN feat/login 以 develop 為起點建立並切換過去

#### Scenario: 起點分支提問輸入無效編號時重新詢問

逐步邏輯：起點分支提問列出 2 個選項 → 使用者輸入「9」→ 系統提示編號無效 → 再次出現同一題 → 使用者輸入「1」→ 以第 1 個分支為起點。

- GIVEN 起點分支提問列出 2 個選項
- WHEN 使用者輸入「9」
- THEN 系統提示編號無效並再次出現同一題起點分支提問
- AND 使用者接著輸入「1」後以第 1 個選項的分支為起點建立工作分支

#### Scenario: 工作分支已存在時直接切換不詢問起點分支

逐步邏輯：使用者新增任務並輸入已存在的分支「feat/login」→ 系統直接切到 feat/login → 接著詢問後續規劃問題。

- GIVEN 目標專案本地已有 feat/login
- WHEN 使用者新增任務並輸入工作分支名稱「feat/login」
- THEN 目標專案切換到既有的 feat/login，analyze_plan 接著出現的提問是後續規劃問題

#### Scenario: 非互動式環境以目前分支為起點建立工作分支

- GIVEN analyze_plan 在非互動式環境執行，工作分支本地不存在，目前在 develop
- WHEN 初始規劃需要建立工作分支
- THEN 系統不提問，直接以 develop 為起點建立並切換到工作分支

#### Scenario: 使用者中止起點分支提問時記為錯誤

- GIVEN 起點分支提問已出現
- WHEN 使用者中止提問
- THEN analyze_plan 記為錯誤並說明未選擇起點分支，工作分支未建立，系統不進入規格撰寫

### Requirement: 建立工作分支前同步起點分支到遠端最新版本

The system SHALL 在從起點分支建立工作分支之前，先切換到起點分支並以只快轉的方式向其追蹤的遠端分支同步；同步成功後才建立工作分支。起點分支未設定追蹤的遠端分支時，系統 MUST 在執行日誌印出「起點分支 <名稱> 未設定 upstream，略過 git pull」並直接以本地版本建立工作分支。

#### Scenario: 起點分支落後遠端時先同步再建立工作分支

逐步邏輯：使用者選 main 為起點 → 系統切到 main → 遠端 main 比本地多 1 個 commit → 系統快轉本地 main 到遠端最新 → 從最新的 main 建立 feat/login 並切換過去 → 執行日誌顯示已從 main 建立並切換到 feat/login。

- GIVEN 本地 main 追蹤遠端 main，遠端 main 比本地多 1 個 commit，工作分支 feat/login 不存在
- WHEN 使用者選擇 main 為起點分支
- THEN 本地 main 前進到遠端 main 的最新 commit
- AND feat/login 指向該最新 commit 並成為目前分支
- AND 執行日誌顯示已從 main 建立並切換到 feat/login

#### Scenario: 起點分支未設定 upstream 時略過同步並從本地版本建立

- GIVEN 起點分支 local-only 沒有追蹤任何遠端分支
- WHEN 使用者選擇 local-only 為起點分支
- THEN 執行日誌顯示「起點分支 local-only 未設定 upstream，略過 git pull」
- AND 工作分支從 local-only 的本地版本建立並成為目前分支

### Requirement: 起點分支同步失敗時 analyze_plan 記為錯誤

The system MUST 在起點分支切換失敗或同步失敗（網路或認證錯誤、本地與遠端分岔無法快轉、逾時等）時，將 analyze_plan 記為錯誤，錯誤說明 MUST 包含工作分支名稱與 git 回報的失敗原因；此時工作分支 MUST 尚未建立，系統不進入規格撰寫。

#### Scenario: 起點分支無法快轉時記為錯誤且不建立工作分支

逐步邏輯：使用者選 main 為起點 → 系統切到 main 並同步 → 本地 main 與遠端 main 各有不同 commit、無法快轉 → 系統停止 → analyze_plan 卡片顯示錯誤「無法建立分支 feat/login：git pull 失敗：…」→ 本地沒有 feat/login。

- GIVEN 本地 main 與其遠端 main 已分岔，工作分支 feat/login 不存在
- WHEN 使用者選擇 main 為起點分支
- THEN analyze_plan 記為錯誤，錯誤說明包含「feat/login」與 git pull 的失敗原因
- AND 本地仍不存在 feat/login，系統不進入規格撰寫
