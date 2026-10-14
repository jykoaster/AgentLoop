# web-gui Specification

## Purpose
網頁控制台讓使用者在不改變任何工作流節點規則的前提下，以圖形化介面掌握每個任務各工作階段的進度、回覆工作流提問、中止與重跑階段、
瀏覽已封存任務與既有 Spec、搜尋規格，並設定目標專案與認證。

## Requirements

### Requirement: 主分頁組成

The system SHALL 在網頁最外層提供四個主分頁，依序為「執行中任務」、「已封存任務」、「既有 Spec」、「設定」，開啟網頁時預設選中「執行中任務」；點擊任一主分頁即切換到該分頁內容。

#### Scenario: 開啟網頁後顯示四個主分頁且預設選中執行中任務

逐步邏輯：使用者在瀏覽器開啟控制台 → 系統載入頁面 → 依序顯示四個主分頁並把「執行中任務」設為選中 → 內容區顯示執行中任務列表；使用者再點「設定」→ 選中狀態移到「設定」並顯示設定內容。

- GIVEN 已設定目標專案
- WHEN 使用者開啟控制台網址
- THEN 頁面最上方依序顯示「執行中任務」、「已封存任務」、「既有 Spec」、「設定」四個分頁標籤
- AND 「執行中任務」為選中狀態，內容區顯示執行中任務列表
- AND 使用者點擊「設定」後，選中狀態移到「設定」，內容區改為設定表單

### Requirement: 執行中任務列表

The system SHALL 在「執行中任務」分頁為目標專案中每個有執行狀態紀錄、且尚未封存的任務顯示一列；每列標題 MUST 顯示 change 名稱、分支名稱、任務描述（超過 80 字截斷並以「…」結尾）與目前迭代次數；列內 MUST 依 analyze_plan、human_confirm、execute、review、archive 的順序各顯示一張階段卡片，以及一個「檢視規格文件」入口。每張卡片 MUST 以比頁面背景更亮的深色卡片面呈現，顯示階段名稱與一個階段狀態徽章；卡片左側的粗色條與狀態徽章 MUST 以同一個狀態色區分四種階段狀態：尚未開始（灰）、執行中（藍）、完成（綠）、錯誤（紅），徽章內文字為該狀態的中文名稱（尚未開始、執行中、完成、錯誤）。狀態為執行中的卡片 MUST 另外持續顯示藍色呼吸光暈，其他狀態的卡片不帶光暈。列表依 change 名稱字母順序排列，每 2 秒自動更新一次。

#### Scenario: 執行中任務分頁為每個未封存的 change 顯示一列階段卡片

逐步邏輯：系統讀取目標專案所有任務的執行狀態 → 排除已封存的任務 → 每個剩下的任務組出一列 → 每張卡片依階段狀態決定左側色條與狀態徽章的顏色與文字 → 只有執行中的卡片加上呼吸光暈。

- GIVEN 目標專案有兩個任務：`feat-login`（分支 `feat/login`、任務描述「新增登入頁」、第 0 次迭代；analyze_plan 完成、human_confirm 完成、execute 執行中、review 與 archive 尚未開始）與 `fix-typo`（已封存）
- WHEN 使用者開啟「執行中任務」分頁
- THEN 列表只有一列，標題顯示「feat-login」、「feat/login」、「新增登入頁」、「第 0 次迭代」
- AND 該列依序顯示五張卡片，左側色條與狀態徽章分別為：analyze_plan（綠、「完成」）、human_confirm（綠、「完成」）、execute（藍、「執行中」）、review（灰、「尚未開始」）、archive（灰、「尚未開始」）
- AND 五張卡片中只有 execute 帶有呼吸光暈
- AND 該列有「檢視規格文件」入口

#### Scenario: 沒有任何執行中任務時顯示空狀態與新增任務入口

逐步邏輯：系統找不到任何未封存且有執行狀態紀錄的任務 → 內容區不顯示任何列 → 改顯示提示文字與新增任務入口。

- GIVEN 目標專案沒有任何未封存且有執行狀態紀錄的任務
- WHEN 使用者開啟「執行中任務」分頁
- THEN 內容區顯示「目前沒有執行中的任務」
- AND 仍顯示「新增任務」按鈕

### Requirement: 工作階段狀態紀錄

The system SHALL 在工作流執行時（不論由命令列或網頁啟動）把每個工作階段的狀態記錄在該任務的執行狀態中，狀態值只有尚未開始、執行中、完成、錯誤四種：階段開始時記為執行中，且其後所有階段重設為尚未開始；階段結束且整體結果為錯誤時記為錯誤，否則記為完成。

#### Scenario: 工作流推進時各階段狀態依序由尚未開始轉為執行中再轉為完成

逐步邏輯：新任務的五個階段都是尚未開始 → analyze_plan 開始，記為執行中 → analyze_plan 結束且沒有錯誤，記為完成 → human_confirm 開始，記為執行中 → 依此類推。

- GIVEN 一個新任務，五個階段皆為尚未開始
- WHEN 工作流執行 analyze_plan 並順利結束，接著進入 human_confirm
- THEN analyze_plan 開始執行時狀態為執行中，結束後為完成
- AND human_confirm 開始時狀態為執行中，execute、review、archive 仍為尚未開始
- AND 上述狀態都已寫入該任務的執行狀態，重新整理網頁後看到相同結果

#### Scenario: 階段結束且結果為錯誤時該階段記為錯誤且後續階段維持尚未開始

逐步邏輯：execute 執行中 → execute 結束並回報錯誤 → execute 記為錯誤 → 工作流依原路由結束，review 與 archive 不會開始。

- GIVEN 任務的 analyze_plan、human_confirm 為完成，execute 執行中
- WHEN execute 結束且整體結果為錯誤
- THEN execute 狀態為錯誤（紅）
- AND review、archive 狀態為尚未開始

#### Scenario: review 退回重新規劃時 analyze_plan 之後的階段重設為尚未開始

逐步邏輯：review 完成且判定需要重新規劃 → 迭代次數加一 → analyze_plan 再次開始 → analyze_plan 記為執行中，其後四個階段全部重設為尚未開始。

- GIVEN 任務五個階段中 analyze_plan、human_confirm、execute、review 為完成，archive 為尚未開始
- WHEN review 判定需要重新規劃，工作流再次進入 analyze_plan
- THEN analyze_plan 為執行中，human_confirm、execute、review、archive 皆為尚未開始
- AND 列標題的迭代次數加一

#### Scenario: 沒有階段狀態紀錄的舊任務以尚未開始顯示所有階段

逐步邏輯：系統讀到一個在本功能上線前建立、沒有階段狀態紀錄的任務 → 五個階段一律視為尚未開始 → 仍可在卡片上重跑。

- GIVEN 某任務的執行狀態中沒有任何階段狀態紀錄
- WHEN 使用者開啟「執行中任務」分頁
- THEN 該任務列的五張卡片皆顯示尚未開始（灰）
- AND analyze_plan、execute、review、archive 卡片仍提供重跑按鈕

### Requirement: 階段詳情

The system SHALL 在使用者點擊階段卡片後開啟該階段詳情，顯示該階段的執行結果與最近一次執行的日誌：analyze_plan 顯示分析摘要（proposal 全文）與計畫清單；human_confirm 顯示人工確認結果與修改意見；execute 顯示執行摘要；review 顯示審查報告與審查等級；archive 只顯示日誌。日誌 MUST 去除終端色碼、只顯示最後 500 行，且在該階段執行中時每 2 秒更新；尚無結果的欄位顯示「（尚無資料）」。若該階段因使用者中止而記為錯誤，詳情最上方 MUST 顯示「使用者中止」。

#### Scenario: 點擊卡片後顯示該階段的執行結果與執行日誌

逐步邏輯：使用者點擊 review 卡片 → 系統讀取該任務的執行狀態取出審查報告與審查等級 → 讀取 review 最近一次執行的日誌最後 500 行 → 在詳情中依序顯示。

- GIVEN 任務 `feat-login` 的 review 已完成，審查等級為「修補」，審查報告以「## Standards」開頭，review 日誌共 800 行且含終端色碼
- WHEN 使用者點擊 `feat-login` 的 review 卡片
- THEN 詳情顯示審查等級「修補」與完整審查報告
- AND 日誌區只顯示第 301 到 800 行，且不含任何終端色碼字元

#### Scenario: 被使用者中止的階段在詳情顯示使用者中止

逐步邏輯：execute 先前被使用者中止並記為錯誤 → 使用者點擊 execute 卡片 → 詳情最上方顯示中止註記，下方照常顯示執行摘要與日誌。

- GIVEN 任務 `feat-login` 的 execute 因使用者中止而記為錯誤
- WHEN 使用者點擊 execute 卡片
- THEN 詳情最上方顯示「使用者中止」
- AND 執行摘要欄位沒有內容時顯示「（尚無資料）」

### Requirement: 檢視任務規格文件

The system SHALL 在每個執行中任務列提供「檢視規格文件」入口，開啟後以唯讀方式列出該任務 OpenSpec change 資料夾內的所有 Markdown 檔案（相對路徑，proposal.md、design.md、tasks.md 依此順序排在最前，其餘依路徑字母順序），點擊檔名即顯示該檔全文。

#### Scenario: 從任務列開啟該 change 的規格文件

逐步邏輯：使用者點「檢視規格文件」→ 系統列出 change 資料夾內的 Markdown 檔 → 使用者點 `specs/auth/spec.md` → 顯示該檔全文。

- GIVEN 任務 `feat-login` 的 change 資料夾有 `tasks.md`、`proposal.md`、`specs/auth/spec.md`
- WHEN 使用者在 `feat-login` 列點「檢視規格文件」，再點 `specs/auth/spec.md`
- THEN 檔案清單依序為 `proposal.md`、`tasks.md`、`specs/auth/spec.md`
- AND 內容區以唯讀方式顯示 `specs/auth/spec.md` 的全文

### Requirement: 網頁回覆待回覆提問

The system SHALL 在執行中的工作流提出待回覆提問時，於提問所屬階段的卡片顯示驚嘆號；使用者點擊卡片後，詳情 MUST 顯示提問全文以及與提問種類相符的回覆控制項：選項題顯示每個選項的按鈕並另提供自訂文字輸入；是非題顯示「是」「否」兩個按鈕；文字題顯示輸入框與送出按鈕；用量上限暫停顯示「繼續」「中止」兩個按鈕。送出回覆後，工作流以該回覆繼續，與在終端輸入同一內容的結果相同，驚嘆號隨即消失。以命令列執行工作流時，提問仍在終端回覆，行為與本功能上線前相同。

#### Scenario: 階段等待人工回覆時卡片顯示驚嘆號並可在詳情中回覆

逐步邏輯：analyze_plan 的 grilling 輸出一個附三個選項的 QUESTION → 系統把它登記為 analyze_plan 的待回覆提問 → analyze_plan 卡片出現驚嘆號 → 使用者點卡片，看到問題與三個選項按鈕 → 點選項 1 → 系統把「1」交給工作流 → 工作流以同一 session 帶著回答繼續 → 驚嘆號消失，卡片維持執行中。

- GIVEN analyze_plan 執行中，Agent 提問「網頁服務要用什麼技術棧？」並附選項「1. FastAPI（建議）」「2. Flask」「3. Django」
- WHEN 使用者點擊 analyze_plan 卡片並按下選項 1 的按鈕
- THEN 點擊前 analyze_plan 卡片顯示驚嘆號，詳情顯示問題全文、三個選項按鈕與一個自訂文字輸入框
- AND 工作流收到的回答為「1」，與在終端輸入「1」的效果相同
- AND 回覆送出後驚嘆號消失，analyze_plan 卡片維持執行中

#### Scenario: 人工確認關卡可在網頁確認執行或送出修改意見

逐步邏輯：human_confirm 開始 → 卡片出現驚嘆號，詳情顯示分析摘要、計畫清單與是非題「繼續執行？」→ 使用者按「否」→ 接著出現文字題「請輸入修改意見（留空則中止）」→ 使用者輸入意見送出 → 工作流以修改意見回到 analyze_plan 重新規劃。

- GIVEN human_confirm 正在等待確認
- WHEN 使用者按「否」，再於修改意見輸入框輸入「改用 Flask」並送出
- THEN 工作流收到修改意見「改用 Flask」，human_confirm 記為完成，analyze_plan 重新變成執行中
- AND 若使用者改按「是」，human_confirm 記為完成且 execute 變成執行中

#### Scenario: 用量上限暫停時可在網頁選擇繼續或中止

逐步邏輯：execute 呼叫 Claude 撞到用量上限 → 系統登記用量上限暫停提問並顯示錯誤訊息 → 使用者等重置後按「繼續」→ 工作流接回同一個 Claude session 繼續。

- GIVEN execute 執行中撞到用量上限，錯誤訊息為「You've hit your session limit · resets 3:45pm」
- WHEN 使用者點擊 execute 卡片並按「繼續」
- THEN 詳情顯示上述錯誤訊息與「繼續」「中止」兩個按鈕
- AND 按下「繼續」後工作流接回中斷前的 Claude session，驚嘆號消失

#### Scenario: 以命令列執行工作流時提問仍在終端回覆

逐步邏輯：使用者在終端執行完整工作流 → analyze_plan 問分支名稱 → 提示照舊印在終端 → 使用者在終端輸入 → 流程照舊繼續。

- GIVEN 未以網頁模式啟動的工作流
- WHEN analyze_plan 詢問分支名稱，使用者在終端輸入「feat/login」
- THEN 終端顯示與本功能上線前相同的提示文字
- AND 工作流使用分支「feat/login」繼續

### Requirement: 待回覆提問的回覆驗證

The system MUST 拒絕不合規則的回覆並保留輸入內容：必填的文字題（分支名稱）不可送出空白；選項題的自訂文字可為空白，空白代表採用 Agent 建議的選項；沒有待回覆提問時送出的回覆一律被拒絕。被拒絕時畫面 MUST 顯示原因且工作流不會收到該回覆。

#### Scenario: 必填文字題送出空白時不送出並提示必填

逐步邏輯：analyze_plan 問分支名稱 → 使用者沒輸入就按送出 → 系統不把回覆交給工作流 → 顯示「此欄位為必填」→ 驚嘆號仍在。

- GIVEN analyze_plan 正在等待分支名稱
- WHEN 使用者在輸入框留空並按送出
- THEN 畫面顯示「此欄位為必填」
- AND 工作流仍在等待回覆，analyze_plan 卡片仍顯示驚嘆號

#### Scenario: 提問已被回覆後再送出回覆時顯示提問已結束

逐步邏輯：使用者在兩個瀏覽器分頁開著同一提問 → 在第一個分頁回覆 → 在第二個分頁再送出 → 系統發現已沒有待回覆提問 → 拒絕並提示。

- GIVEN 某待回覆提問已被回覆
- WHEN 使用者從另一個瀏覽器分頁對同一提問送出回覆
- THEN 畫面顯示「此提問已結束，請重新整理」
- AND 工作流不會收到第二個回覆

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

### Requirement: 重跑工作階段

The system SHALL 只在 analyze_plan、execute、review、archive 四張卡片提供「重跑」按鈕；按下並確認後，系統從該階段開始執行，並依原工作流路由接續後面的流程（與命令列 `--node` 相同），任務描述與其餘狀態沿用該任務既有的紀錄。重跑開始時該階段變為執行中，其後各階段重設為尚未開始。

#### Scenario: 重跑某階段時從該階段開始並接續後續流程

逐步邏輯：使用者在 execute 卡片按「重跑」並確認 → 系統以該任務既有紀錄從 execute 開始執行 → execute 變為執行中、review 與 archive 重設為尚未開始 → execute 結束後依路由進入 review。

- GIVEN 任務 `feat-login` 的 analyze_plan、human_confirm 為完成，execute 為錯誤，review 為完成，archive 為尚未開始
- WHEN 使用者在 execute 卡片按「重跑」並確認
- THEN execute 為執行中，review、archive 為尚未開始，analyze_plan、human_confirm 維持完成
- AND execute 順利結束後 review 自動變為執行中
- AND 重跑按鈕出現在 analyze_plan、execute、review、archive 四張卡片上

### Requirement: 同時只允許一個執行

The system SHALL 讓同一目標專案同時最多只有一個執行（含等待回覆中的執行）；有執行進行中時，所有任務的「重跑」按鈕與「新增任務」按鈕 MUST 停用，並在滑鼠移到按鈕上時顯示「目前已有 <change 名稱或任務描述> 執行中」；若仍有其他來源送出啟動要求，系統 MUST 拒絕並顯示同一原因。執行結束後按鈕自動恢復可用。

#### Scenario: 已有執行進行中時其他啟動動作停用並顯示原因

逐步邏輯：`feat-login` 的 execute 執行中 → 系統標記目前有執行 → 所有重跑與新增任務按鈕停用 → 使用者把滑鼠移到 `fix-css` 的重跑按鈕 → 顯示原因。

- GIVEN `feat-login` 正在執行，另有任務 `fix-css`
- WHEN 使用者把滑鼠移到 `fix-css` 的 review 重跑按鈕
- THEN 所有重跑按鈕與「新增任務」按鈕皆為停用
- AND 顯示「目前已有 feat-login 執行中」

#### Scenario: 執行進行中再送出啟動要求時系統拒絕

逐步邏輯：`feat-login` 正在執行 → 另一個瀏覽器分頁（畫面尚未更新）送出新增任務 → 系統發現已有執行 → 拒絕，不啟動新的執行 → 畫面顯示原因。

- GIVEN `feat-login` 正在執行
- WHEN 使用者從尚未更新的瀏覽器分頁送出新增任務「修正樣式」
- THEN 系統不啟動新的執行，`feat-login` 的執行不受干擾
- AND 畫面顯示「目前已有 feat-login 執行中」

### Requirement: 新增任務

The system SHALL 在「執行中任務」分頁提供「新增任務」按鈕，使用者輸入任務描述並送出後，系統以該描述啟動完整工作流（與命令列 `python -m AgentLoop.main "<任務描述>"` 相同）；在分支名稱決定之前，列表 MUST 以任務描述作為該列標題顯示一個暫時列，其 analyze_plan 卡片依序以待回覆提問詢問分支名稱、是否撰寫 spec、domain 等初始問題（順序與命令列相同）；分支名稱決定後，該列標題改為 change 名稱。任務描述不可為空白。

#### Scenario: 新增任務後以 analyze_plan 卡片引導初始提問

逐步邏輯：使用者按「新增任務」→ 輸入「新增登入頁」送出 → 系統啟動工作流 → 列表出現標題為「新增登入頁」的暫時列，analyze_plan 卡片執行中並顯示驚嘆號 → 使用者點卡片看到分支名稱提問 → 輸入「feat/login」送出 → 接著出現是否撰寫 spec 的是非題 → 回覆後出現 domain 選擇題 → 分支名稱決定後列標題變為「feat-login」。

- GIVEN 目前沒有執行進行中
- WHEN 使用者按「新增任務」、輸入任務描述「新增登入頁」並送出，再於 analyze_plan 詳情回覆分支名稱「feat/login」
- THEN 送出任務後列表出現標題為「新增登入頁」的列，analyze_plan 為執行中且有驚嘆號，其餘四階段為尚未開始
- AND 回覆分支名稱後，下一個待回覆提問為是否撰寫 spec 的是非題
- AND 該列標題改為「feat-login」，分支顯示「feat/login」

#### Scenario: 任務描述為空白時無法送出新增任務

逐步邏輯：使用者開啟新增任務對話框 → 不輸入或只輸入空白 → 送出按鈕停用。

- GIVEN 新增任務對話框已開啟
- WHEN 使用者只在任務描述輸入空白字元
- THEN 送出按鈕為停用

### Requirement: 已封存任務列表

The system SHALL 在「已封存任務」分頁為目標專案 `openspec/changes/archive/` 底下的每個封存 change 顯示一列，每列顯示封存日期（YYYY-MM-DD）與 change 名稱，依封存資料夾名稱由新到舊排序；點擊一列後以唯讀方式列出該封存 change 內的 Markdown 檔案（排序規則與「檢視任務規格文件」相同），點擊檔名顯示全文。

#### Scenario: 已封存任務分頁每個封存 change 一列並可瀏覽其文件

逐步邏輯：系統列出封存資料夾 `2026-09-01-feat-a`、`2026-10-01-feat-b` → 拆出日期與名稱 → 由新到舊排列 → 使用者點 `feat-b` 列 → 列出其檔案 → 點 `proposal.md` 顯示全文。

- GIVEN 封存資料夾有 `2026-09-01-feat-a` 與 `2026-10-01-feat-b`，後者內有 `proposal.md` 與 `tasks.md`
- WHEN 使用者開啟「已封存任務」分頁並點擊 `feat-b` 列，再點 `proposal.md`
- THEN 列表第一列為「2026-10-01 feat-b」，第二列為「2026-09-01 feat-a」
- AND 檔案清單依序為 `proposal.md`、`tasks.md`，內容區顯示 `proposal.md` 全文

#### Scenario: 沒有任何封存任務時顯示空狀態

逐步邏輯：封存資料夾不存在或沒有子資料夾 → 不顯示任何列 → 顯示提示文字。

- GIVEN 目標專案沒有任何封存 change
- WHEN 使用者開啟「已封存任務」分頁
- THEN 內容區顯示「目前沒有已封存的任務」

### Requirement: 既有 Spec 瀏覽

The system SHALL 在「既有 Spec」分頁由上而下依序呈現：規格搜尋區、domain 清單、所選 domain 的規格全文。domain 清單列出目標專案 `openspec/specs/` 底下每個 domain（依名稱字母順序），點擊 domain 後以唯讀方式在清單下方顯示該 domain 規格全文；沒有任何 domain 時在清單位置顯示「目前沒有既有 Spec」，搜尋區仍顯示在其上方。

#### Scenario: 既有 Spec 分頁列出每個 domain 並可檢視其規格內容

逐步邏輯：使用者開啟「既有 Spec」分頁 → 最上方先看到搜尋框 → 系統讀取 `openspec/specs/` 下的 domain 資料夾 `billing`、`auth` → 排序為 `auth`、`billing` 顯示在搜尋區下方 → 使用者點 `auth` → 清單下方顯示其規格全文。

- GIVEN 目標專案既有 Spec 有 `billing` 與 `auth` 兩個 domain
- WHEN 使用者開啟「既有 Spec」分頁並點擊 `auth`
- THEN 搜尋框位於 domain 清單上方
- AND domain 清單依序為 `auth`、`billing`
- AND 清單下方顯示 `auth` 規格全文

### Requirement: 規格語意搜尋

The system SHALL 在「既有 Spec」分頁的搜尋區提供搜尋框，使用者輸入問題送出後，系統以與命令列 `python -m AgentLoop.search` 相同的方式（索引過期時先重建、取最相關的最多 5 份文件、一律以 haiku 模型依文件回答）產生結果，並顯示：回答全文，以及參考檔案清單（每項為相對路徑與文件類型，依相關度排序）。搜尋進行中 MUST 顯示「搜尋中…」並停用送出按鈕；問題為空白時送出按鈕停用。

#### Scenario: 輸入問題搜尋規格後顯示回答與參考檔案

逐步邏輯：使用者輸入「登入失敗幾次會鎖定？」送出 → 畫面顯示搜尋中 → 系統檢索出 3 份相關文件 → 以 haiku 模型依文件回答 → 畫面顯示回答與 3 個參考檔案。

- GIVEN 既有 Spec 有 `auth` domain，其中規定登入失敗 5 次鎖定 15 分鐘
- WHEN 使用者在搜尋框輸入「登入失敗幾次會鎖定？」並送出
- THEN 等待期間顯示「搜尋中…」且送出按鈕停用
- AND 回答由 haiku 模型產生
- AND 完成後顯示回答全文，以及依相關度排序的參考檔案清單，每項為相對路徑與文件類型（例如 `openspec/specs/auth/spec.md（spec）`），最多 5 項

#### Scenario: 規格中找不到相關內容時顯示查無結果訊息

逐步邏輯：檢索不到任何文件 → 系統不呼叫 Claude → 顯示查無結果訊息。

- GIVEN 目標專案的 openspec 中沒有任何可檢索的文件
- WHEN 使用者送出任一問題
- THEN 畫面顯示「規格文件中沒有找到相關內容。」

#### Scenario: 搜尋失敗時顯示錯誤訊息並保留查詢文字

逐步邏輯：搜尋過程中 Claude 回答失敗 → 系統回報錯誤 → 畫面顯示錯誤原因 → 搜尋框保留原本的問題，使用者可直接再送出。

- GIVEN 搜尋時 Claude 呼叫失敗，錯誤訊息為「claude CLI error: not logged in」
- WHEN 使用者送出問題「登入規則？」
- THEN 畫面顯示「搜尋失敗：claude CLI error: not logged in」
- AND 搜尋框仍保留「登入規則？」，送出按鈕恢復可用

### Requirement: 設定管理

The system SHALL 在「設定」分頁依序提供目標專案、Claude OAuth token、Anthropic API key 三個欄位；token 與 API key 只顯示「已設定（末四碼 xxxx）」或「未設定」，不回傳完整值，輸入框留空儲存時保留原值。儲存成功顯示「已儲存」，之後啟動的執行與搜尋一律使用新值；網頁設定的值優先於 `.env` 中的同名設定，網頁未設定的欄位沿用 `.env`。有執行進行中時目標專案欄位 MUST 停用。

#### Scenario: 設定分頁顯示目前設定並可儲存

逐步邏輯：系統讀取網頁設定與 `.env` → 依優先序組出目前值 → 顯示三個欄位的表單（認證只顯示末四碼）→ 使用者在 API key 輸入框輸入以 `abcd` 結尾的金鑰並儲存 → 顯示已儲存 → API key 改顯示末四碼 → 之後的搜尋使用這把金鑰。

- GIVEN `.env` 設定目標專案 `my-project`、OAuth token 以 `…9xYz` 結尾，API key 未設定
- WHEN 使用者開啟「設定」分頁，在 API key 輸入框輸入 `sk-ant-api03-…abcd` 後按「儲存」
- THEN 表單依序只有目標專案、Claude OAuth token、Anthropic API key 三個欄位，顯示目標專案 `my-project`、OAuth token「已設定（末四碼 9xYz）」、API key「未設定」
- AND 儲存後顯示「已儲存」，API key 改顯示「已設定（末四碼 abcd）」，輸入框清空
- AND 重新整理後 API key 仍顯示「已設定（末四碼 abcd）」

#### Scenario: 認證欄位留空儲存時保留原本的值

逐步邏輯：OAuth token 已設定 → 使用者只改目標專案、token 輸入框留空 → 儲存 → token 仍是原值。

- GIVEN OAuth token 已設定且末四碼為 `9xYz`
- WHEN 使用者在 token 輸入框留空，只修改其他欄位後儲存
- THEN 重新整理後 token 仍顯示「已設定（末四碼 9xYz）」

#### Scenario: 有執行進行中時無法變更目標專案

逐步邏輯：`feat-login` 正在執行 → 使用者開啟設定 → 目標專案欄位與其「選擇資料夾」按鈕停用並說明原因。

- GIVEN `feat-login` 正在執行
- WHEN 使用者開啟「設定」分頁
- THEN 目標專案欄位與「選擇資料夾」按鈕為停用，旁邊顯示「執行進行中，無法變更目標專案」
- AND 認證欄位仍可編輯並儲存

### Requirement: 目標專案資料夾選擇

The system SHALL 在尚未指定目標專案（網頁設定與 `.env` 皆無）時，開啟網頁即自動開啟資料夾選擇器，且其他分頁顯示「請先在設定選擇目標專案」；設定分頁也提供「選擇資料夾」按鈕開啟同一選擇器。選擇器 MUST 只列出工作區根目錄底下的資料夾（不含以「.」開頭的隱藏資料夾，依名稱字母順序），可進入子資料夾與返回上一層，但不能離開工作區根目錄；選定後目標專案以相對工作區根目錄的路徑儲存並立即套用。

#### Scenario: 尚未指定目標專案時開啟資料夾選擇器並以選定資料夾作為目標專案

逐步邏輯：網頁設定與 `.env` 都沒有目標專案 → 使用者開啟控制台 → 系統自動開啟資料夾選擇器，列出工作區根目錄下的 `AgentLoop`、`my-project`（隱藏的 `.cache` 不列出）→ 使用者選 `my-project` 並確認 → 目標專案存為 `my-project` → 「執行中任務」改顯示 `my-project` 的任務。

- GIVEN 未設定目標專案，工作區根目錄下有 `AgentLoop`、`my-project`、`.cache`
- WHEN 使用者開啟控制台，在自動開啟的資料夾選擇器中點選 `my-project` 並按「確定」
- THEN 選擇器開啟時只列出 `AgentLoop`、`my-project`，且在選定前「執行中任務」分頁顯示「請先在設定選擇目標專案」
- AND 確定後設定的目標專案為 `my-project`，「執行中任務」分頁改顯示 `my-project` 的任務列表

#### Scenario: 選擇工作區根目錄以外的路徑時拒絕並提示

逐步邏輯：有人直接送出指向工作區根目錄以外（例如 `../etc`）的目標專案 → 系統解析後發現不在根目錄內 → 拒絕儲存 → 顯示原因。

- GIVEN 目前目標專案為 `my-project`
- WHEN 送出目標專案路徑 `../etc`
- THEN 畫面顯示「只能選擇工作區根目錄底下的資料夾」
- AND 目標專案仍為 `my-project`

### Requirement: 可點擊元素的游標提示

The system SHALL 讓控制台中所有可點擊的元素——主分頁標籤、各種按鈕（含純圖示按鈕與問答選項按鈕）、階段卡片、封存任務列、domain 清單項目、檔案清單項目、資料夾清單項目——在滑鼠移上時顯示手指游標；處於停用狀態的按鈕 MUST 改顯示禁止游標，且點擊不產生任何動作。

#### Scenario: 滑鼠移到可點擊元素時顯示手指游標且停用按鈕顯示禁止游標

逐步邏輯：使用者開啟「既有 Spec」分頁 → 把滑鼠移到 domain `auth` → 游標變成手指，表示可點 → 切到「執行中任務」，`feat-login` 正在執行 → 滑鼠移到 `fix-css` 列已停用的重跑按鈕 → 游標變成禁止符號，點了也不會重跑。

- GIVEN 既有 Spec 有 domain `auth`；任務 `feat-login` 正在執行，另有任務 `fix-css`
- WHEN 使用者依序把滑鼠移到 domain 清單的 `auth`、`fix-css` 的 analyze_plan 卡片、`fix-css` 的 review 重跑按鈕
- THEN `auth` 清單項目與 analyze_plan 卡片顯示手指游標
- AND 已停用的重跑按鈕顯示禁止游標，點擊後不出現重跑確認對話框

### Requirement: 純圖示按鈕

The system SHALL 將「關閉」「重跑」「檢視規格文件」「上一層」四種按鈕以純圖示呈現，按鈕上不顯示文字；每個純圖示按鈕 MUST 以原本的文字作為無障礙名稱，並在滑鼠停留時顯示原本的文字作為提示。「重跑」MUST 以警示黃呈現、「關閉」MUST 以紅色呈現，使兩者顏色明顯不同。「重跑」按鈕停用時，滑鼠停留提示 MUST 改為停用原因，無障礙名稱仍為「重跑」。

#### Scenario: 純圖示按鈕以滑鼠停留提示與無障礙名稱呈現原本文字

逐步邏輯：目前沒有執行進行中 → 使用者看 `feat-login` 列 → execute 卡片上的重跑按鈕只有一個黃色的循環箭頭圖示，沒有文字 → 滑鼠停在上面出現提示「重跑」→ 列底的規格文件按鈕只有文件圖示，停留提示「檢視規格文件」→ 使用者點 review 卡片開啟詳情 → 詳情面板的關閉按鈕只有紅色叉叉圖示，停留提示「關閉」→ 點它詳情面板關閉。

- GIVEN 任務 `feat-login` 存在且目前沒有執行進行中
- WHEN 使用者把滑鼠停在 execute 卡片的重跑按鈕、任務列的規格文件按鈕上，再點 review 卡片並把滑鼠停在詳情的關閉按鈕上後點擊它
- THEN 重跑按鈕只顯示圖示、不顯示文字，呈警示黃，提示與無障礙名稱皆為「重跑」
- AND 規格文件按鈕只顯示圖示，提示與無障礙名稱皆為「檢視規格文件」
- AND 關閉按鈕只顯示圖示，呈紅色，提示與無障礙名稱皆為「關閉」；點擊後詳情面板關閉
- AND 資料夾選擇器中的上一層按鈕同樣只顯示圖示，提示與無障礙名稱皆為「上一層」

#### Scenario: 重跑按鈕停用時滑鼠停留提示顯示停用原因

逐步邏輯：`feat-login` 正在執行 → 所有重跑按鈕停用 → 使用者把滑鼠停在 `fix-css` 的重跑按鈕 → 提示改為停用原因，但輔助科技讀到的名稱仍是「重跑」。

- GIVEN `feat-login` 正在執行，另有任務 `fix-css`
- WHEN 使用者把滑鼠停在 `fix-css` 的 review 重跑按鈕上
- THEN 提示顯示「目前已有 feat-login 執行中」
- AND 該按鈕的無障礙名稱仍為「重跑」，按鈕上仍只顯示圖示

### Requirement: 操作與狀態附圖示

The system SHALL 在下列位置的文字旁顯示對應圖示，文字本身維持原內容：四個主分頁標籤、「新增任務」、「搜尋」、「儲存」、「選擇資料夾」、「中止」、對話框的「確定」「取消」、問答回覆的「送出」「是」「否」「繼續」、封存任務列、domain 清單項目、檔案清單項目、資料夾清單項目。階段狀態徽章 MUST 在狀態中文名稱旁顯示圖示，四種狀態（尚未開始、執行中、完成、錯誤）各自使用不同圖示；階段卡片的待回覆標示 MUST 以驚嘆號圖示呈現。

#### Scenario: 主要操作與階段狀態徽章在文字旁顯示對應圖示

逐步邏輯：使用者開啟控制台 → 四個主分頁標籤各自在文字前顯示一個圖示，文字仍為「執行中任務」「已封存任務」「既有 Spec」「設定」→ `feat-login` 列的五張卡片中，徽章依狀態顯示不同圖示加上中文狀態名稱 → analyze_plan 有待回覆提問，卡片右上角顯示驚嘆號圖示。

- GIVEN 任務 `feat-login` 的 analyze_plan 執行中且有待回覆提問、human_confirm 尚未開始、execute 錯誤、review 完成
- WHEN 使用者開啟控制台
- THEN 四個主分頁標籤各有一個圖示，標籤文字依序仍為「執行中任務」「已封存任務」「既有 Spec」「設定」
- AND 「新增任務」按鈕文字旁有圖示
- AND 狀態徽章分別顯示「執行中」「尚未開始」「錯誤」「完成」，且這四個徽章的圖示彼此不同
- AND analyze_plan 卡片顯示驚嘆號圖示
