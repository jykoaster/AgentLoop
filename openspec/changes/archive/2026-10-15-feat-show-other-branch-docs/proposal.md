# Proposal: 檢視規格文件可讀取其他分支上的 change

## Intent

規範目的：讓網頁控制台「執行中任務」列的「檢視規格文件」，不論目標專案此刻 checkout 在哪個分支，都能列出並開啟該任務的規格文件（proposal、design、tasks、specs delta 等）。讀取過程不切換分支、不改動工作樹，畫面與在該分支上直接讀檔時完全相同。

規範背景：工作流每次執行都會把目標專案切到該次任務的工作分支。某任務的 change 資料夾若已在它自己的工作分支上 commit，使用者開始另一個任務、切到別的分支後，這個資料夾就不在目前的工作樹裡。網頁只讀工作樹，所以點「檢視規格文件」會得到「找不到 change」，看不到其他尚未封存任務的規格。尚未 commit 的 change 檔案屬於 untracked，會隨工作樹留在原地、本來就讀得到；因此只要「工作樹找不到時，改讀該任務工作分支最新 commit 的內容」，兩個來源合起來就能涵蓋所有情況。

## Scope

In scope:

- 「執行中任務」列的「檢視規格文件」（檔案清單與單檔全文）：目前工作樹找不到該任務的 change 資料夾時，以唯讀方式改讀該任務工作分支最新 commit 裡的 change 資料夾
- 檔案排序規則、全文顯示方式與讀工作樹時相同；畫面不另外標示讀取來源
- 工作樹與工作分支都讀不到時，維持「找不到 change」
- 讀取工作分支時 git 指令本身失敗，在找不到訊息後附上 git 錯誤訊息，方便除錯
- 補上對應的後端測試，並更新 `ARCHITECTURE.md` 的 HTTP API／`repo_view.py` 描述

Out of scope:

- analyze_plan 等工作流節點讀取其他 change 文件（Agent 規劃時的衝突比對）
- 「已封存任務」、「既有 Spec」分頁的讀取來源
- 「執行中任務」列表本身的判定（是否已封存等）
- 每階段結束時另存規格文件快照
- 前端畫面與元件

## Approach

在 `lib/git_ops.py` 新增兩個唯讀函式：以 `git ls-tree -r --name-only <branch> -- openspec/changes/<name>/` 列出分支上的檔案、以 `git show <branch>:<path>` 讀取單檔內容，皆不 checkout、不動工作樹與 index。`web/repo_view.py` 的 `list_change_files()`／`read_change_file()` 先照舊讀工作樹，資料夾不存在時才從 `.agentloop/changes/<name>/state.json` 取 `branch_name`，改走 git 讀取，最後套用同一套 Markdown 過濾與排序。兩個 git 函式比照 `create_branch_from` 回傳 `(結果或 None, git 錯誤訊息)`；「工作樹優先 → 工作分支 → 找不到」的判定抽成 `repo_view` 內單一 helper，讀單檔時以分支清單區分「檔案不存在」與「git 出錯」。HTTP API 路徑與回應格式不變，前端不需修改。
