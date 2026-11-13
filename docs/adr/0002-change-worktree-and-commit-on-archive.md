# 每個任務一個 git worktree，封存時才自動 commit

原本所有節點在目標專案主工作目錄 `git checkout` 工作分支，兩個任務並行會互相切走分支，只能同時跑一個執行。改為每個任務在 `<工作區根目錄>/.agentloop-worktrees/<目標專案>/<change 名稱>/` 建立專屬 worktree，CLI 與網頁一律如此，主工作目錄永遠不切分支；執行狀態紀錄（`.agentloop/changes/`）仍留在主工作目錄，讓網頁從單一位置列出所有任務。

因為 execute 從不 commit，移除 worktree 等於丟掉成果，所以 execute 只擬好 commit 訊息存進 state，archive 成功後才以這則訊息 commit 全部變更到工作分支、再移除 worktree（分支保留、不 push）。缺訊息或 commit 失敗時不移除 worktree、archive 記為錯誤，重跑 archive 只補做 commit 與移除。

## Considered Options

- 可切換的「worktree 模式」開關：兩套 git 行為並存、測試面加倍，否決。
- worktree 放在目標專案內 `.agentloop/worktrees/`：要求每個目標專案都 gitignore `.agentloop/`，否決。
- worktree 不自動移除、或移除前不 commit：前者讓 worktree 無限堆積，後者會丟失未提交的實作。

## Consequences

- 工作分支合併回主工作目錄所在分支前，「既有 Spec」看不到該任務併入的內容；「已封存任務」以「未合併 · <工作分支>」標示列出，文件從工作分支唯讀讀取。任務是否已封存改以執行狀態紀錄的旗標判定。
- 任務工作目錄不含主工作目錄的未追蹤檔。執行遇到障礙時依目標專案自己的說明處理；本專案不規定相依如何準備。
- 目標專案若以固定容器名稱或埠啟動 `docker compose`，並行任務仍可能互相衝突；本決策不處理。
