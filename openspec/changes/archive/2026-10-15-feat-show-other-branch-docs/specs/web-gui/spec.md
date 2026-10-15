## MODIFIED Requirements

### Requirement: 檢視任務規格文件

The system SHALL 在每個執行中任務列提供「檢視規格文件」入口，開啟後以唯讀方式列出該任務 OpenSpec change 資料夾內的所有 Markdown 檔案（相對路徑，proposal.md、design.md、tasks.md 依此順序排在最前，其餘依路徑字母順序），點擊檔名即顯示該檔全文。目標專案目前的工作樹有該 change 資料夾時 MUST 顯示工作樹內容；工作樹沒有時，系統 MUST 不切換分支、不改動工作樹，改以該任務工作分支最新 commit 中的 change 資料夾作為內容來源，檔案清單的排序規則與全文顯示方式和讀取工作樹時相同，畫面不區分來源。工作樹與工作分支都找不到該 change 時，系統 MUST 顯示「找不到 change：<change 名稱>」。讀取工作分支時若 git 指令本身失敗（例如分支物件損毀），系統 MUST 在原本的找不到訊息（「找不到 change：<change 名稱>」或「找不到檔案：<檔案路徑>」）後以「（git：<git 錯誤訊息>）」附上 git 回報的錯誤內容；分支上本來就沒有該 change 或該檔案時，訊息維持原樣、不附 git 錯誤。

#### Scenario: 從任務列開啟該 change 的規格文件

逐步邏輯：使用者點「檢視規格文件」→ 系統列出 change 資料夾內的 Markdown 檔 → 使用者點 `specs/auth/spec.md` → 顯示該檔全文。

- GIVEN 任務 `feat-login` 的 change 資料夾有 `tasks.md`、`proposal.md`、`specs/auth/spec.md`
- WHEN 使用者在 `feat-login` 列點「檢視規格文件」，再點 `specs/auth/spec.md`
- THEN 檔案清單依序為 `proposal.md`、`tasks.md`、`specs/auth/spec.md`
- AND 內容區以唯讀方式顯示 `specs/auth/spec.md` 的全文

#### Scenario: 目前分支沒有該 change 資料夾時從任務的工作分支讀取規格文件

逐步邏輯：任務 `feat-login` 的規格文件已 commit 在工作分支 `feat/login` → 使用者之後新增任務 `feat-cart`，工作流把目標專案切到 `feat/cart`，工作樹裡不再有 `feat-login` 的 change 資料夾 → 使用者在 `feat-login` 列點「檢視規格文件」→ 系統在工作樹找不到資料夾，改讀 `feat/login` 最新 commit 裡的 change 資料夾 → 依同一排序規則列出檔案 → 使用者點 `specs/auth/spec.md` → 系統從 `feat/login` 讀出該檔全文顯示 → 目標專案仍停在 `feat/cart`，工作樹沒有任何變動。

- GIVEN 任務 `feat-login` 的工作分支為 `feat/login`，該分支最新 commit 中的 change 資料夾有 `tasks.md`、`proposal.md`、`specs/auth/spec.md`（`specs/auth/spec.md` 內容為「# auth spec」）
- AND 目標專案目前 checkout 在分支 `feat/cart`，工作樹中沒有 `feat-login` 的 change 資料夾
- WHEN 使用者在 `feat-login` 列點「檢視規格文件」，再點 `specs/auth/spec.md`
- THEN 檔案清單依序為 `proposal.md`、`tasks.md`、`specs/auth/spec.md`，畫面與讀取工作樹時相同
- AND 內容區以唯讀方式顯示「# auth spec」
- AND 目標專案仍在分支 `feat/cart`，工作樹沒有新增、修改或刪除任何檔案

#### Scenario: 工作樹與工作分支都沒有該 change 時顯示找不到 change

逐步邏輯：使用者點「檢視規格文件」→ 工作樹沒有 `feat-login` 的 change 資料夾 → 該任務記錄的工作分支已不存在於本地 → 系統沒有可讀的來源 → 顯示找不到 change。

- GIVEN 任務 `feat-login` 記錄的工作分支 `feat/login` 已不存在於本地，工作樹中也沒有 `feat-login` 的 change 資料夾
- WHEN 使用者在 `feat-login` 列點「檢視規格文件」
- THEN 系統回應「找不到 change：feat-login」，不列出任何檔案

#### Scenario: 讀取工作分支時 git 指令失敗會在找不到訊息後附上 git 錯誤訊息

逐步邏輯：工作樹沒有 `feat-login` 的 change 資料夾 → 系統改讀工作分支 `feat/login`，分支上的檔案清單有 `proposal.md` → 使用者點 `proposal.md` → 系統從分支讀該檔時 git 回報錯誤（該檔內容的 git 物件已遺失）→ 因為檔案確實在分支清單內，系統判定是 git 出錯而不是檔案不存在 → 回應找不到檔案，並在後面附上 git 的錯誤訊息，讓使用者知道實際原因。

- GIVEN 任務 `feat-login` 的工作分支 `feat/login` 最新 commit 中的 change 資料夾有 `proposal.md`，但 `proposal.md` 內容對應的 git 物件已從目標專案的 git 資料中遺失
- AND 目標專案目前 checkout 在其他分支，工作樹中沒有 `feat-login` 的 change 資料夾
- WHEN 使用者在 `feat-login` 列點「檢視規格文件」，再點 `proposal.md`
- THEN 檔案清單仍列出 `proposal.md`
- AND 系統回應以「找不到檔案：proposal.md（git：」開頭、後接 git 回報的非空錯誤訊息並以「）」結尾的文字，不顯示檔案內容
