# analyze-plan Specification

## Purpose
定義 analyze_node 內的功能

## Requirements

### Requirement: 重跑已規劃任務的 analyze_plan 時詢問調整內容

The system SHALL 在使用者對一個已完成規劃、未封存、且沒有尚未處理之審查退回的任務重跑 analyze_plan 時，於 analyze_plan 階段以必填文字的待回覆提問詢問「請輸入本次要調整的內容」；取得調整內容後，系統 MUST 沿用該任務原本的分支、change、domain 與是否撰寫 spec 的決定（不再詢問這些問題），依調整內容更新同一個 change 的規格文件，完成後照原工作流進入人工確認；本次調整的審查重試次數 MUST 從 0 起算。

#### Scenario: 對已通過審查的任務重跑 analyze_plan 並輸入調整內容後更新同一個 change

逐步邏輯：任務 `feat-login` 已完成規劃、execute 與 review（review 通過、未封存）→ 使用者在 analyze_plan 卡片按「重跑」並確認 → analyze_plan 變為執行中並出現驚嘆號 → 使用者點卡片，看到提問「請輸入本次要調整的內容」→ 輸入「登入失敗三次後鎖定帳號 5 分鐘」送出 → 系統不再詢問分支、是否撰寫 spec、domain → 依調整內容更新 `feat-login` 的規格文件 → analyze_plan 完成，human_confirm 出現人工確認提問，執行計畫顯示原本已完成的項目與新增的待辦項目。

- GIVEN 任務 `feat-login`（分支 `feat/login`、domain `auth`）已完成規劃、execute 與 review，review 通過且尚未封存，審查重試次數為 2
- WHEN 使用者重跑 analyze_plan，並在待回覆提問輸入「登入失敗三次後鎖定帳號 5 分鐘」
- THEN analyze_plan 的第一個待回覆提問為必填文字題「請輸入本次要調整的內容」，之後不再出現分支名稱、是否撰寫 spec、domain 歸屬的提問
- AND 規格文件更新在原本的 `openspec/changes/feat-login/`，沒有建立其他 change 資料夾，工作分支仍為 `feat/login`
- AND analyze_plan 完成後進入 human_confirm，人工確認提問中的分析摘要為更新後的提案內容
- AND 審查重試次數為 0

#### Scenario: 未提供調整內容時 analyze_plan 記為錯誤且任務紀錄不變

逐步邏輯：使用者在命令列重跑 `feat-login` 的 analyze_plan → 出現調整內容提問 → 使用者按 Ctrl-C（或在無法互動的環境執行）→ 系統取不到調整內容 → analyze_plan 記為錯誤並顯示原因 → 任務描述與規格文件維持原樣，工作流結束。

- GIVEN 任務 `feat-login` 已完成規劃且未封存
- WHEN 使用者重跑 analyze_plan，但在調整內容提問時中止輸入，或執行環境無法互動
- THEN analyze_plan 為錯誤，結果顯示「未提供調整內容，無法調整規劃」
- AND 任務描述與 `openspec/changes/feat-login/` 底下的規格文件與重跑前相同
- AND human_confirm、execute、review、archive 不會執行

### Requirement: 調整內容依序編號附加在任務描述之後

The system SHALL 在取得調整內容後，保留原任務描述全文，並在其後附加一個空行與一行「調整 N：<調整內容>」；N 為正整數，等於任務描述中既有「調整 k：」行數加 1。附加後的任務描述 MUST 立即寫入該任務的執行狀態紀錄，使網頁任務列標題列的任務描述與之後 review 取得的需求都包含全部調整。

#### Scenario: 第二次調整以下一個編號附加且保留先前的調整

逐步邏輯：任務 `feat-login` 的任務描述為「新增登入頁」，已調整過一次 → 描述變成「新增登入頁\n\n調整 1：登入失敗三次後鎖定帳號 5 分鐘」→ 使用者再次重跑 analyze_plan 並輸入「鎖定時間改為 10 分鐘」→ 系統數出既有 1 行「調整 k：」→ 以編號 2 附加 → 網頁任務列顯示三段內容。

- GIVEN 任務 `feat-login` 的任務描述為「新增登入頁」＋空行＋「調整 1：登入失敗三次後鎖定帳號 5 分鐘」
- WHEN 使用者重跑 analyze_plan 並輸入調整內容「鎖定時間改為 10 分鐘」
- THEN 任務描述依序為「新增登入頁」、空行、「調整 1：登入失敗三次後鎖定帳號 5 分鐘」、空行、「調整 2：鎖定時間改為 10 分鐘」
- AND 網頁任務列顯示的任務描述與上述內容相同

### Requirement: 調整後保留已完成的待辦項目

The system SHALL 在調整模式更新 tasks.md 時，保留所有已勾選完成的待辦項目（文字與勾選狀態皆不變），本次調整所需的工作 MUST 以新增或改寫尚未完成的待辦項目呈現，讓 execute 只處理尚未完成的項目。

#### Scenario: 已執行過的任務調整後執行計畫同時列出已完成項目與新增的待辦項目

逐步邏輯：`feat-login` 的 tasks.md 有「1.1 新增登入表單」「1.2 撰寫登入表單測試」兩個已勾選項目 → 使用者重跑 analyze_plan 並輸入調整內容「登入失敗三次後鎖定帳號 5 分鐘」→ 系統更新規格，tasks.md 保留 1.1、1.2 的勾選與文字，另新增鎖定帳號相關的未勾選項目 → 人工確認的執行計畫依原階層編號列出全部項目。

- GIVEN `feat-login` 的 tasks.md 只有「1.1 新增登入表單」「1.2 撰寫登入表單測試」兩個已勾選項目
- WHEN 使用者重跑 analyze_plan 並以「登入失敗三次後鎖定帳號 5 分鐘」完成調整
- THEN tasks.md 中「1.1 新增登入表單」「1.2 撰寫登入表單測試」仍為已勾選，文字與調整前相同
- AND tasks.md 至少新增一個描述帳號鎖定工作的未勾選項目
- AND 人工確認提問的執行計畫列出上述所有項目，沿用 tasks.md 自帶的階層編號

### Requirement: 有尚未處理的審查退回時讓使用者選擇規劃方式

The system SHALL 在使用者重跑 analyze_plan、且該任務有尚未處理的審查退回時，先以選擇題詢問「依審查結果重新規劃」或「輸入調整內容」；選擇前者時 MUST 依審查結果修正規格（與 review 退回時自動重新規劃相同），選擇後者時 MUST 改為詢問調整內容並進入調整。review 退回後由工作流自動進入的重新規劃 MUST 直接依審查結果進行，不出現此選擇題。

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

### Requirement: 已封存任務不能調整

The system SHALL 在使用者對已封存的任務重跑 analyze_plan 時，直接把 analyze_plan 記為錯誤，結果顯示「此 change 已封存，請以新任務進行後續修改」，且 MUST 在任何提問之前結束。

#### Scenario: 對已封存任務重跑 analyze_plan 時記為錯誤並提示改用新任務

逐步邏輯：`feat-login` 已封存（規格已併入既有 Spec）→ 使用者在命令列執行 `--node analyze_plan` 並從選單選擇 `feat-login` → 系統發現該 change 已封存 → analyze_plan 記為錯誤，顯示提示 → 不出現任何提問，工作流結束。

- GIVEN `feat-login` 已封存，其執行狀態紀錄仍存在
- WHEN 使用者以命令列重跑 `feat-login` 的 analyze_plan
- THEN analyze_plan 為錯誤，結果顯示「此 change 已封存，請以新任務進行後續修改」
- AND 過程中沒有任何待回覆提問，任務描述與既有 Spec 皆與重跑前相同

### Requirement: 調整中斷後重跑接回同一次調整

The system SHALL 在調整進行中被中斷（用量上限暫停後結束、使用者中止）且已取得 Claude session 時，讓使用者下次重跑 analyze_plan 接回同一個 session 繼續這次調整；此時 MUST 不再詢問模式選擇或調整內容，任務描述也不再附加新的調整行。

#### Scenario: 調整被中止後重跑 analyze_plan 接回原 session 且不重複附加調整

逐步邏輯：使用者重跑 `feat-login` 的 analyze_plan 並輸入「鎖定時間改為 10 分鐘」→ 任務描述附加「調整 2：鎖定時間改為 10 分鐘」並寫入紀錄 → Claude 規劃中取得 session `s-1` → 使用者按「中止」→ analyze_plan 記為錯誤並保存 session → 使用者再次重跑 analyze_plan → 系統接回 `s-1` 續作，不出現調整內容提問。

- GIVEN `feat-login` 的調整在 Claude 規劃時被中止，任務描述已含「調整 2：鎖定時間改為 10 分鐘」，已保存 analyze_plan 的 session `s-1`
- WHEN 使用者再次重跑 analyze_plan
- THEN 工作流接回 session `s-1` 繼續規劃，沒有任何調整內容或模式選擇的提問
- AND 任務描述只含「調整 1」「調整 2」兩行調整，沒有「調整 3」

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
