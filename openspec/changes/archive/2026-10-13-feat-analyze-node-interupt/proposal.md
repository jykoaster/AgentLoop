# Proposal: 新增任務的初始 analyze_plan 可從網頁中止

## Intent

讓使用者在網頁新增任務後，在初始 analyze_plan 執行期間（包括分支名稱、是否撰寫 spec、domain 等初始提問、grilling 提問，以及 Claude 正在規劃時）隨時都能從網頁中止，結束整個執行，並釋放「新增任務」與「重跑」按鈕。

背景：新增任務後，任務要等 analyze_plan 整段結束才會留下執行狀態紀錄，所以在這之前列表只有一個暫時列。暫時列的 analyze_plan 詳情載入不到階段狀態，因此「中止」按鈕不會出現。使用者唯一的停止方式是等規劃跑完，或是剛好碰到用量上限暫停時按「中止」。本次只補上暫時列的中止入口，不改變執行狀態紀錄寫出的時機。

## Scope

In scope:

- 暫時列 analyze_plan 詳情在執行中時顯示「中止」按鈕；位置、樣式、確認對話框都與正式任務列的 analyze_plan 詳情一致
- 確認中止後結束整個執行（含其下所有 Claude 程序），暫時列消失，「新增任務」按鈕恢復可用
- 對應的前端與後端測試

Out of scope:

- 提早寫出執行狀態紀錄（例如分支名稱一決定就寫），讓暫時列提早轉成正式任務列
- 中止暫時列時記錄「使用者中止」註記，或保存 Claude session 供之後接回
- 在暫時列標題列另外放一個中止按鈕
- 中止後清理已建立的 git 分支或 openspec change 資料夾

## Approach

前端：`ChangeRow` 把自己是否為暫時列的資訊傳給 `StageDetail`。暫時列沒有 change 名稱，無法向後端查詢階段詳情，所以 `StageDetail` 改用暫時列本身帶有的「analyze_plan 執行中」狀態來決定是否顯示「中止」按鈕。按鈕沿用既有的 `onAbort`（同一個 `window.confirm` 文案、同一個 `postAbort()` API）。

後端：`web/runner.py` 的 `abort()` 在沒有 change 名稱或沒有 `state.json` 時，原本就會略過狀態回寫，只結束 process group 並清理執行目錄，因此不需要修改。只要補一個測試，固定住這個行為。

詳見 design.md。
