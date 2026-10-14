# Design: 對同一個任務進行調整（重跑 analyze_plan 時輸入調整內容）

## Technical Approach

### 1. 重跑入口標記（`main.py`）

`run_node()` 呼叫 node 前，若 `node_name == "analyze_plan"`，在 state 設 `start_from = "analyze_plan"`（暫態欄位，`_save_state()` 本來就不寫入 `state.json`）。之後 `_stream_and_save(state, start_from="human_confirm")` 會覆寫成 `human_confirm`，所以工作流內部因 review 退回經 `increment` 回到 analyze_plan 時，`start_from` 不會是 `analyze_plan`，不會觸發模式選擇。`analyze_plan_node` 以 `is_rerun = state.get("start_from") == "analyze_plan"` 判斷。

### 2. 模式判定（`nodes/analyze_plan.py` `analyze_plan_node`）

依序判定（`prior_session` 為 `take_session(state, "analyze_plan")`）：

| 順序 | 條件 | 動作 |
| ---- | ---- | ---- |
| 1 | `is_rerun` 且已封存（`_is_archived_change()` 委派給 `lib/openspec_runner.py` 新增的公開函式 `is_change_archived(project_dir_abs, change_name)`，見 §7；不可用 `archive_destination_name()`，它前置的是今天日期） | `_fail("此 change 已封存，請以新任務進行後續修改")`，不提問 |
| 2 | `human_feedback` 非空 | 既有「依人工意見調整」（含被中斷的調整，見 §4） |
| 3 | `review_result` 非空且 `review_blocking` 為 True，且 `is_rerun` 且沒有 `prior_session` | 詢問模式選擇題（§3）；選「依審查結果重新規劃」→ 既有 replan；選「輸入調整內容」→ 進入調整 |
| 4 | `review_result` 非空且 `review_blocking` 為 True（工作流內部、或有 `prior_session`） | 既有 replan，不提問 |
| 5 | `is_rerun` 且 `analysis` 非空（含 review 已通過但 `review_result` 仍留著報告的情況） | 進入調整（§3） |
| 6 | `analysis` 非空但不是重跑入口（`start_from` 不是 `analyze_plan`，且沒有 `human_feedback`、沒有 `review_blocking`；正常路由不會出現，只有舊 `state.json` 或直接呼叫 node 才會遇到） | `_fail("此 change 已完成規劃，請以重跑 analyze_plan 進行調整")`，不提問、不呼叫 Claude，避免掉進初始規劃後重問分支／spec／domain 並覆寫整份規格 |
| 7 | 其他 | 既有初始規劃 |

原本的 Guard「此 change 已完成初始規劃，不可重複執行初始規劃」由第 5、6 條取代：重跑入口進入調整，非重跑入口改以第 6 條的新錯誤文案擋下。實作上把 `elif not is_human_revise and analysis_state: is_adjust = True` 改為 `elif is_rerun and not is_human_revise and analysis_state`，其後再加一個 `elif not is_human_revise and analysis_state` 分支回傳第 6 條的 `_fail()`。既有的 `is_replan = bool(review_result)` 必須改為 `bool(review_result) and review_blocking`，否則 review 通過後重跑會誤入 replan。Guard「review_blocking=True 但 review_result 為空」維持。

### 3. 調整提問與狀態寫入

- 模式選擇題：`interaction.ask("此任務有尚未處理的審查退回，要如何重新規劃？", kind="choice", stage="analyze_plan", options=interaction.numbered(["依審查結果重新規劃", "輸入調整內容"]))`；接受 `1`/`2` 或選項原文。非互動式環境、中止 → 視為「依審查結果重新規劃」（保留既有行為）。
- 調整內容：先 `print` 提示再 `interaction.ask("請輸入本次要調整的內容", kind="text", stage="analyze_plan", required=True, multiline=True)`。命令列空字串重問；`EOFError`/`KeyboardInterrupt`/非互動式 → `_fail("未提供調整內容，無法調整規劃")`，此時 task 與規格皆不變。
- 取得內容後：
  - `task = _append_adjustment(state["task"], content)`：以 `re.findall(r"(?m)^調整 \d+：", task)` 數出既有行數 n，回傳 `f"{task.rstrip()}\n\n調整 {n+1}：{content}"`。
  - `human_feedback = content`，`review_result = ""`、`review_blocking = False`、`review_level = ""`。
  - 之後完全走既有 human-revise 路徑（`tools="revise"`、`_SKILLS`、`_SYSTEM_HUMAN_REVISE`），`<<HUMAN_FEEDBACK>>` 注入調整內容。
- 回傳：`_fail()` 與成功回傳都要帶出 `task`、`human_feedback`（失敗時保留，成功時清空，沿用既有行為）、`review_result`／`review_blocking`；成功時調整模式另外回傳 `iteration: 0`。`_fail()` 需改為帶入目前的 `task`／`human_feedback`／review 欄位，讓 `main._save_state()` 立即寫入。

### 4. 中斷接回

調整內容一旦取得就以 `human_feedback` 形式寫入 state（見 §3）。若 Claude 呼叫被中斷，`_fail()` 回傳的 `human_feedback` 與附加後的 `task` 會存進 `state.json`；下次重跑命中 §2 第 2 條（human-revise），不再詢問、不再附加，並由 `call_resuming()` 以保存的 session 接回。session 失效時 fallback 的完整 prompt 也帶著同一段調整內容。

### 5. Prompt 調整（遵守「Keep prompts from growing」）

不新增 `_SYSTEM` 變體。

- `_SYSTEM_HUMAN_REVISE` 背景句「你先前已提出一份規格與計畫，但使用者在審閱後提出了以下修改意見：」改為「使用者對先前的規格與計畫提出以下修改意見（可能在執行前或執行後）：」
- 「保留 `- [x]`」規則放進三個 `_SYSTEM` 共用的 `_ANALYZE_PROHIBITIONS`，與既有那條「不得將 `- [ ]` 改為 `- [x]`」併成同一條雙向限制，不另加條目：

  ```
  - **不得變更 `tasks.md` 任何勾選狀態**——完成標記由 execute node 在實作後即時更新；
    既有 `- [x]` 維持原文，所需工作以新增或改寫 `- [ ]` 呈現
  ```

  同時把 `_SYSTEM_HUMAN_REVISE` 步驟 4 句尾的「tasks.md 既有 `- [x]` 項目維持原文與勾選，意見所需工作以新增或改寫 `- [ ]` 呈現」刪掉，只留「強制三項若被意見改到就一併改寫」，避免同一份 prompt 講兩次。整體 prompt 字數不增加。
- 這條規則同時套用到 initial、replan（修補／重寫）、human-revise。replan「重寫」等級的勾選重設不靠 Claude：`_reset_task_checkboxes()` 在 Claude 呼叫與 validate 之後才由 Python 把 `- [x]` 改回 `- [ ]`，所以與「不得變更勾選狀態」不衝突。
- `openspec-authoring` skill 不改。

### 6. 網頁

前端不需修改：選擇題與必填文字題沿用既有 `QuestionForm`（`kind="choice"`／`kind="text", required`）。網頁任務列本來就顯示 `state.json` 的 `task`，調整後自動顯示附加內容。`web/runner.py` 的重跑已是 `--node analyze_plan --change <name>`，不需修改。

### 7. 共用封存判斷（`lib/openspec_runner.py`）

新增公開函式 `is_change_archived(project_dir_abs: str, change_name: str) -> bool`，規則沿用目前 `_is_archived_change()` 較嚴格的版本：

1. `change_name` 不安全（空字串、`.`、`..`、含路徑分隔字元；與 `nodes/analyze_plan.py` 的 `_safe_change_name()` 規則相同，lib 內自行檢查，不反向 import node）→ `False`
2. `<project_dir_abs>/openspec/changes/<change_name>/` 存在 → `False`（change 仍在使用中）
3. `<project_dir_abs>/openspec/changes/archive/` 不存在 → `False`
4. archive 下有名稱等於 `<change_name>` 或以 `-<change_name>` 結尾的目錄 → `True`

- `nodes/analyze_plan.py` 的 `_is_archived_change(project_dir, change_name)` 改為組出 `os.path.join(REPO_ROOT, project_dir)` 後委派給它（`project_dir` 為空時仍回 `False`）。
- `web/repo_view.py` 的 `_is_archived(project, change_name)` 改為委派給它，移除原本只比對字尾的實作。網頁任務列因此多一個修正：archive 下剛好有同字尾目錄、但 change 仍在使用中的任務，不會再被誤藏。
- 不讓 node 直接 import `web/repo_view.py`：那會連帶載入 `web.runner`（`get_manager`），變成 node 層反向依賴 web 層。

### 8. 共用提問樣板（`nodes/analyze_plan.py`）

新增 `_ask_or_default(question, default, *, interactive_msg, abort_msg, abort_default=<同 default>, **ask_kwargs)`：

- `interaction.is_interactive()` 為 False → 若 `interactive_msg` 不為 `None` 則印出，回傳 `default`
- 否則呼叫 `interaction.ask(question, stage="analyze_plan", **ask_kwargs)` 並 `.strip()`；拋 `EOFError`／`KeyboardInterrupt` → 印出 `abort_msg`（前置換行，與現行輸出相同），回傳 `abort_default`（未指定時等於 `default`）
- `interactive_msg`／`abort_msg` 由呼叫端傳入含顏色碼的完整字串，各函式維持現行的 `_RED`／`_YELLOW` 配色

提示的列印、選項列印、空值重問與答案解析迴圈留在呼叫端。呼叫端以「回傳值是否為 `str`」以外的預設值（`None`、`False`）判斷走了非互動或中止分支時，必須在進入解析前直接回傳。

這次套用到 `nodes/analyze_plan.py` 全部 7 個 `_ask_*` 函式，每個函式的列印文案、`ask()` 參數與回傳值都不變：

| 函式 | `ask()` 參數 | 非互動式回傳 | 中止回傳 | 備註 |
| ---- | ------------ | ------------ | -------- | ---- |
| `_ask_skip_specs()` | `kind="confirm"` | `False`（印「非互動式環境，預設為需要寫 spec」） | `None`（`abort_default=None`，紅字「已取消，請明確選擇是否需要撰寫 spec」） | 呼叫端對回傳字串再 `.lower()` 後比對 y／n，無效輸入重問 |
| `_ask_new_domain_name()` | `kind="text"` | `""`（`interactive_msg=None`，現行呼叫端已保證互動式） | `""`（黃字「已中止，由 Agent 依任務語意自行命名」） | 無重問迴圈 |
| `_ask_domain_selection(project_dir)` | `kind="choice", options=...` | `([], "")`（印「非互動式環境，預設建立新 domain」） | `([], "")`（黃字「已中止，預設建立新 domain」） | 以 `default=None` 呼叫，`None` 時回傳 `([], "")`；沒有既有 domain 時仍在提問前直接回傳 `([], "")`；空值重問與編號解析迴圈不變 |
| `_ask_domain_purpose()` | `kind="text", multiline=True` | `""`（`interactive_msg=None`，現行無訊息） | `""`（黃字「已略過，由 Agent 自行撰寫 Purpose」） | 無重問迴圈 |
| `_ask_adjustment()` | `kind="text", required=True, multiline=True` | `None`（紅字「非互動式環境，無法輸入調整內容」） | `None`（紅字「已取消，調整內容為必填」） | 空值重問 |
| `_ask_rerun_mode()` | `kind="choice", options=...` | `"replan"`（黃字「非互動式環境，預設依審查結果重新規劃」） | `"replan"`（黃字「已中止，預設依審查結果重新規劃」） | 以 `default=None` 呼叫，`None` 時回傳 `"replan"`，避免把 `"replan"` 字串誤當成使用者答案 |
| `_ask_branch_name()` | `kind="text", required=True` | `""`（紅字「非互動式環境，無法輸入分支名稱」） | `""`（紅字「已取消，分支名稱為必填」） | 空值與分支名稱合法性重問 |

## Architecture Decisions

### Decision: 調整模式重用 human-revise 路徑，以 `human_feedback` 承載調整內容

替代方案是新增第四份 `_SYSTEM_ADJUST` 與新 state 欄位。選擇重用的理由：(1) 兩者本質都是「依使用者意見更新同一個 change」，提示詞幾乎相同，新增變體違反 CLAUDE.md 的 prompt 成長限制；(2) 把調整內容放進 `human_feedback` 後，中斷接回、session fallback 都直接沿用既有路徑，不需新的分支判斷。代價：`human_feedback` 的語意從「人工確認退回意見」擴大為「使用者對規格的修改意見（含調整）」，需同步更新 `core/state.py` 註解與文件。

### Decision: 以暫態 `start_from` 區分「重跑入口」與「工作流內部回到 analyze_plan」

模式選擇題只在使用者主動重跑時出現。`start_from` 已是不寫入 `state.json` 的暫態欄位，`run_node()` 是唯一的重跑入口（網頁重跑也走它），因此不新增欄位。

### Decision: 封存判斷放在 lib 層，由 node 與 web 共用

`analyze_plan` 與網頁任務列各自維護一套封存規則，會讓「網頁看得到的任務」和「重跑會被判定已封存的任務」不一致。共用函式放在 `lib/openspec_runner.py`，它本來就負責 archive 目錄的命名與搬移，node 與 web 都已依賴 lib，不會產生新的依賴方向。規則採較嚴格的版本（要求 active change 資料夾不存在）。

### Decision: 「保留 `- [x]`」併入共用禁止事項，而不是只寫在 human-revise

CLAUDE.md「Keep prompts from growing」要求規則放在共用區塊，或哪裡都不加。併入 `_ANALYZE_PROHIBITIONS` 既有那條勾選限制，讓 replan「修補」時也受到保護，prompt 長度也不增加。「重寫」等級的重設由 Python 在 Claude 之後執行，與此規則不衝突。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫**：`analyze_plan_node(state)`，以 `tests/test_node_guards.py` 既有手法 patch `call_claude`／`ensure_on_branch`／`_run_with_validate`／`_read_change_artifacts`／`interaction.ask`／`interaction.is_interactive`，在 `tmp_path` 下建立 `REPO_ROOT` 與 `openspec/changes/<name>/` 目錄；斷言回傳的 `task`、`human_feedback`、`status`、`analysis`、`iteration`，`interaction.ask` 的呼叫參數（提問文字、kind、options、required），以及送進 `call_claude` 的 prompt 是否含調整內容。
- **lib 接縫**：`lib.openspec_runner.is_change_archived(project_dir_abs, change_name)`，在 `tmp_path` 建目錄後直接斷言布林值（放在 `tests/test_openspec_runner.py`）；`web/repo_view.py` 的列表行為以 `tests/test_web_app.py` 既有方式驗證。
- **次要接縫**：`main.run_node("analyze_plan", change_name=...)`，patch `analyze_plan_node` 與 `_stream_and_save`，斷言傳入 node 的 state `start_from == "analyze_plan"` 且 `state.json` 不含 `start_from`（放在 `tests/test_workflow_entrypoints.py`）。tasks.md 保留 `- [x]` 屬 prompt 行為，以 `tests/evals/` 的方式驗證或在 node 測試中以「prompt 含保留規則文字」斷言。

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| ------------- | -------- | ------------------------ |
| 主路徑：`analysis` 非空、review 通過（`review_result` 有報告、`review_blocking=False`）、`iteration=2`、`start_from="analyze_plan"`；`ask` 回「登入失敗三次後鎖定帳號 5 分鐘」 | 第一次 `ask` 為 `kind="text", required=True`、提問「請輸入本次要調整的內容」；沒有分支／spec／domain 提問；prompt 含調整內容；回傳 `status="pending"`、`iteration=0`、task 結尾為「\n\n調整 1：登入失敗三次後鎖定帳號 5 分鐘」 | Scenario「對已通過審查的任務重跑 analyze_plan 並輸入調整內容後更新同一個 change」 |
| `ask` 拋 `KeyboardInterrupt` 或 `is_interactive()=False` | `status="error"`、`analysis` 含「未提供調整內容，無法調整規劃」；未呼叫 `call_claude`；task 不變 | Scenario「未提供調整內容時 analyze_plan 記為錯誤且任務紀錄不變」 |
| task 已含「調整 1：…」，輸入「鎖定時間改為 10 分鐘」 | task 為原文＋「\n\n調整 1：…」＋「\n\n調整 2：鎖定時間改為 10 分鐘」 | Scenario「第二次調整以下一個編號附加且保留先前的調整」 |
| 調整模式與 replan（修補）模式的 system prompt | 皆含「既有 `- [x]` 維持原文」共用規則，且同一份 prompt 中只出現一次 | Scenario「已執行過的任務調整後執行計畫同時列出已完成項目與新增的待辦項目」 |
| `review_blocking=True`、`review_result` 非空、`start_from="analyze_plan"`，選「輸入調整內容」 | 第一次 `ask` 為 choice，options 依序「依審查結果重新規劃」「輸入調整內容」；第二次為調整內容題；task 最後一行「調整 1：改用簡訊驗證碼登入」；回傳 `review_result=""` | Scenario「審查退回後重跑 analyze_plan 選擇輸入調整內容」 |
| 同上，選「依審查結果重新規劃」 | 只有一次 `ask`；prompt 為 replan 版本（含審查結果）；task 不變 | Scenario「審查退回後重跑 analyze_plan 選擇依審查結果重新規劃」 |
| `review_blocking=True`、`start_from` 為空或 `human_confirm`（工作流內部） | 不呼叫 `ask`，直接 replan | 同上 Scenario 的邊界（不另開 Scenario） |
| `start_from="analyze_plan"`，archive 目錄下有 `2026-10-13-feat-login`、`openspec/changes/feat-login/` 不存在 | `status="error"`、`analysis` 為「此 change 已封存，請以新任務進行後續修改」；未呼叫 `ask` | Scenario「對已封存任務重跑 analyze_plan 時記為錯誤並提示改用新任務」 |
| 調整時 `call_claude` 回 is_error（中止）且有 session `s-1`；以回傳 state 再跑一次 | 第一次回傳含附加後 task 與 `human_feedback`、`session_id="s-1"`；第二次不呼叫 `ask`、以 resume=`s-1` 呼叫、task 無「調整 3」 | Scenario「調整被中止後重跑 analyze_plan 接回原 session 且不重複附加調整」 |
| `analysis` 非空、`start_from=""`、無 `human_feedback`、`review_blocking=False` | `status="error"`、`analysis` 為「此 change 已完成規劃，請以重跑 analyze_plan 進行調整」；未呼叫 `ask`／`call_claude`；task 不變 | design §2 第 6 條（內部 guard，不另開 Scenario） |
| `is_change_archived`：archive 下有 `2026-10-13-feat-login`、active `feat-login/` 不存在 | `True` | lib 接縫 |
| `is_change_archived`：archive 下有 `feat-login`（無日期前綴）、active 不存在 | `True` | lib 接縫 |
| `is_change_archived`：archive 下有 `2026-10-13-feat-login`、active `feat-login/` 仍存在 | `False` | lib 接縫 |
| `is_change_archived`：archive 目錄不存在，或 change 名稱不安全（如 `../x`） | `False` | lib 接縫 |
| 網頁執行中任務列表：`feat-login` 有 state.json、active change 資料夾存在、archive 下有 `2026-09-01-feat-login` | 列表仍顯示 `feat-login` | `tests/test_web_app.py` |
| `nodes/analyze_plan.py` 全部 7 個 `_ask_*` 改用 `_ask_or_default` 後 | 既有測試（`tests/test_interaction.py`、`tests/test_analyze_adjust.py`、`tests/test_node_guards.py`、`tests/test_state_persistence.py`）全數通過，不修改斷言 | 重構安全網 |
| `main.run_node("analyze_plan")` | 傳入 node 的 state `start_from=="analyze_plan"`；寫出的 `state.json` 無 `start_from` | 次要接縫 |

## Technical Debt & Follow-up Notes

- `human_feedback` 語意擴大為「人工確認退回意見或調整內容」，未來若需在網頁區分兩者，需要新增欄位。
- 已封存任務的後續修改仍需以新任務進行；若日後要支援重開封存 change，需處理 change 資料夾重建與既有 Spec 的 delta 基準。
