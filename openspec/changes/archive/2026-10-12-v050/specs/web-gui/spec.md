## ADDED Requirements

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

## MODIFIED Requirements

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
