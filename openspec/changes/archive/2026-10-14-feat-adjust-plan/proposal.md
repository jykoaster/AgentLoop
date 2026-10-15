# Proposal: 對同一個任務進行調整（重跑 analyze_plan 時輸入調整內容）

## Intent

讓使用者在任務完成規劃（甚至已執行、已通過審查）之後，不必手動修改 `state.json` 的任務描述，只要對同一個任務重跑 analyze_plan（網頁「重跑」按鈕或命令列 `--node analyze_plan`），系統就以待回覆提問詢問「本次要調整的內容」，再依調整內容更新同一個 change 的規格文件，接著照原工作流進入人工確認、execute、review。

核心目標：

- 調整以「增量」方式進行：已勾選完成的待辦項目保留不動，只新增（或改寫尚未完成的）待辦項目，execute 只做新增的部分。
- 任務描述保留原文，每次調整以「調整 N：<內容>」附加在後面，網頁任務列與 review 都能看到完整的需求演進。
- 有尚未處理的審查退回時，先讓使用者選擇「依審查結果重新規劃」或「輸入調整內容」。
- 已封存的任務不能調整，analyze_plan 記為錯誤並提示改以新任務進行。

背景：目前對已完成規劃的任務重跑 analyze_plan 會被「此 change 已完成初始規劃」擋下；而 review 通過後 state 仍保留審查報告，重跑時反而誤進「依審查結果重新規劃」模式。使用者唯一的調整方式是手動改 `state.json` 的 task（並清掉規劃結果）再重跑。

## Scope

In scope:

- analyze_plan 新增「調整」模式：判定條件、調整內容提問（必填文字）、調整內容附加至任務描述、沿用既有 domain 與是否撰寫 spec 的決定
- 有尚未處理的審查退回時，以選擇題讓使用者決定走「依審查結果重新規劃」或「調整」
- 已封存任務重跑 analyze_plan 時報錯
- 調整中途中斷（用量上限、使用者中止）後重跑可接回同一個 session，不重複詢問、不重複附加
- 調整完成後審查重試次數重新起算
- 對應測試與文件同步（`ARCHITECTURE.md`、`CLAUDE.md`、`README.md`）

Out of scope:

- 網頁新增獨立的「調整」按鈕或命令列新增 `--adjust` 參數
- 對已封存任務重新開啟 change 資料夾進行調整
- 網頁前端畫面改動（調整提問沿用既有待回覆提問元件呈現）
- 修改 execute／review／archive 節點的行為

## Approach

- `nodes/analyze_plan.py`：以 `AgentState` 欄位判定模式，新增「調整」模式，重用既有「依人工意見調整」的 system prompt（把調整內容當作修改意見注入），不新增第四份 `_SYSTEM`；只把 human-revise 背景句改寫成同時適用兩種情境；「既有 `- [x]` 項目保留不動」併入三份 prompt 共用的禁止事項（與既有勾選限制合為一條），遵守 CLAUDE.md「Keep prompts from growing」。
- `main.py` 的 `run_node()`：以暫態欄位 `start_from` 標記「這是重跑入口」，讓 analyze_plan 只在重跑時詢問模式選擇／調整內容；工作流內部因 review 退回而自動重新規劃時不受影響。
- 封存判斷抽到 `lib/openspec_runner.py` 的共用函式，analyze_plan 與網頁執行中任務列表共用同一規則；analyze_plan 全部 7 個提問函式（是否撰寫 spec、新 domain 名稱、domain 歸屬、domain Purpose、調整內容、重跑模式、分支名稱）共用一個「非互動／中止時回傳預設值」的輔助函式，各提問的文案與回傳值不變。
- 提問一律經由 `lib/interaction.py` 的 `ask()`（`kind="text", required=True` 與 `kind="choice"`），網頁與命令列共用。
- 詳見 design.md。
