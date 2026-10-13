# Design: 網頁控制台改為深色主題並強化元件樣式

## Technical Approach

### 色彩 token（`web/frontend/src/style.css` 的 `@theme`）

沿用既有 token 名稱並翻轉為深色值，新增少數缺少的 token；元件仍只引用 token，不寫任意色碼、不寫 `<style>` 區塊。建議色值（以 Tailwind slate 色階為基準，實作時可微調，但須維持三層底色由暗到亮遞增、彼此肉眼可辨）：

| token | 用途 | 建議值 |
| --- | --- | --- |
| `--color-bg` | 頁面背景（最暗層） | `#0b1120` |
| `--color-surface` | 卡片、面板、對話框（中間層） | `#1e293b` |
| `--color-surface-muted` | 卡片內嵌區塊：日誌、規格內文、`<pre>`、hover 底色（最亮層） | `#334155` |
| `--color-header`（新增） | 頂部主分頁導覽列 | `#020617` |
| `--color-line` | 邊框 | `#475569` |
| `--color-fg` | 主要文字 | `#f1f5f9` |
| `--color-fg-muted` | 次要文字 | `#94a3b8` |
| `--color-on-accent`（新增） | 主要／危險按鈕、狀態徽章上的文字 | `#ffffff` |
| `--color-overlay`（新增） | 對話框遮罩 | `rgb(2 6 23 / 0.7)` |
| `--color-primary` / `--color-primary-hover` | 主要按鈕、選中分頁、focus ring | `#3b82f6` / `#2563eb` |
| `--color-danger` / `--color-warning` / `--color-success` | 錯誤／警示／成功訊息 | `#f87171` / `#fbbf24` / `#4ade80` |
| `--color-stage-pending` / `-running` / `-done` / `-error` | 階段狀態色（灰／藍／綠／紅不變） | `#64748b` / `#3b82f6` / `#22c55e` / `#ef4444` |

元件中現有的 `text-white` 一律改用 `text-on-accent`，`bg-black/40` 改用 `bg-overlay`，讓色值只存在於 `style.css`。

### 呼吸光暈動畫

在 `@theme` 內定義 `--animate-breathe: breathe 2s ease-in-out infinite;`，並於 `@theme` 內（Tailwind v4 寫法）宣告 `@keyframes breathe`，在 0%/100% 與 50% 之間切換以 `--color-stage-running` 為色的 `box-shadow` 擴散範圍（例如 0 → 12px）。元件以 `animate-breathe` utility 套用。另加 `motion-reduce:animate-none`，尊重使用者「減少動態效果」偏好。

### 階段卡片（`StageCard.vue`）

- 卡片本體固定 `bg-surface`、`border border-line`、`rounded-lg`、`shadow`、hover 時邊框提亮；左側粗色條以 `border-l-4` + 狀態對照表的 `border-l-stage-*` 實作。
- 狀態文字改為徽章：`.stage-status` 元素套 `rounded-full px-2 text-xs font-medium text-on-accent` + 狀態對照表的 `bg-stage-*`。
- 狀態對照表由單一字串改為每個狀態對應 `{ bar, badge }`（例：`running → { bar: 'border-l-stage-running', badge: 'bg-stage-running' }`），未知狀態退回 pending；`running` 額外套 `animate-breathe`。
- 驚嘆號標記改為 `bg-warning` 圓形小徽章，重跑按鈕改為次要按鈕樣式。
- 卡片仍保留 `data-status` 屬性。

### 各元件一致樣式

- 主要按鈕：`rounded-md bg-primary text-on-accent hover:bg-primary-hover focus-visible:ring-2 focus-visible:ring-primary shadow-sm transition-colors`；次要按鈕：使用共用 utility `btn-secondary`（見下節）；危險按鈕：`bg-danger`。disabled 一律 `disabled:cursor-not-allowed disabled:opacity-50`。
- 輸入框／select／textarea：`rounded-md border border-line bg-bg text-fg placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/40`。
- `App.vue`：導覽列改 `bg-header` + 底部邊框 + 左側顯示「AgentLoop 控制台」標題；選中分頁維持 `border-primary text-primary`，未選中 hover 時文字變 `text-fg`；`main` 加最大寬度與置中。
- 任務列（`ChangeRow`）、階段詳情面板、提問表單、設定面板：`bg-surface rounded-xl border border-line shadow-lg p-4/p-5`；區塊標題用 `text-fg` 半粗體，次要資訊用 `text-fg-muted`。
- 內嵌區塊（日誌、規格內文、檔案內容、分析摘要等 `<pre>`）：`bg-surface-muted rounded-md p-3 font-mono text-sm`，日誌加 `max-h-96 overflow-auto`。
- 對話框（`FolderPicker`、`NewTaskDialog`、`FileBrowser`）：遮罩 `bg-overlay backdrop-blur-sm`，內框 `bg-surface rounded-xl border border-line shadow-2xl`。
- 清單型按鈕（既有 Spec domain、已封存任務、資料夾項目、檔案項目）：整列可點、`hover:bg-surface-muted`、圓角，與背景間有分隔。
- 次要按鈕共用外觀：在 `style.css` 以 Tailwind v4 `@utility btn-secondary { @apply rounded-md border border-line bg-surface-muted/0 text-fg transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50; }` 定義（disabled 樣式只在按鈕停用時生效，對原本未停用的呼叫點無影響）。現有 11 處次要按鈕——`FolderPicker.vue`（「上一層」、「取消」）、`NewTaskDialog.vue`（取消）、`StageCard.vue`（`.rerun-button`）、`ChangeRow.vue`（`.view-files-button`）、`SettingsPanel.vue`（選擇資料夾）、`QuestionForm.vue` ×3（選項、「否」、「中止」）、`FileBrowser.vue`（`.close-button`）、`ActiveChanges.vue`（階段詳情面板關閉）——把上述外觀 class 換成 `btn-secondary`；尺寸（`px-2 py-1 text-sm`／`px-3 py-1.5`／`px-3 py-2` 等）、版面 class（`self-start`、`mt-1`、`self-end`）與測試用語意 class（`rerun-button`、`view-files-button`、`close-button`）原樣留在呼叫點，模板結構不變、畫面不變。主要按鈕不在本次收斂範圍。
- `index.html` 的 `<html>` 加 `class="bg-bg"`（或於 `style.css` 對 `html, body` 設背景）並宣告 `color-scheme: dark`，避免捲動超出時露出白底、讓原生捲軸與表單控制項為深色。

### 測試在網頁模式環境下卡死的修正（審查修補）

成因：`web/runner.py` 啟動工作流子行程時設定 `AGENTLOOP_INTERACTION=web`／`AGENTLOOP_RUN_DIR`；`lib/claude_runner.py` 的 `_run_claude_once` 呼叫 `subprocess.Popen` 時沒有傳 `env=`，`claude -p` 因此繼承這兩個變數，它在 execute／review 中執行的 `pytest` 也一併繼承。`lib/interaction.is_interactive()` 先檢查環境變數，所以 `patch("sys.stdin.isatty", ...)` 失效，`ask()` 改走 `_ask_web()`，無限輪詢永遠不會出現的 `answer.json`。

修法分兩層，兩層各自都足以避免卡死：

1. **測試隔離**：新增 `tests/conftest.py`，用 autouse fixture 在每個測試開始前 `monkeypatch.delenv` 這兩個變數。需要網頁模式的測試（`tests/test_interaction.py` 的 `TestWebHumanConfirm` 等）已經在測試內自行 `monkeypatch.setenv`，而 fixture 先於測試本體執行，因此不受影響。這樣不論誰在什麼環境執行 `pytest`，測試套件都不會受外部環境影響。
2. **子行程隔離**：`_run_claude_once` 以 `{k: v for k, v in os.environ.items() if k not in ("AGENTLOOP_INTERACTION", "AGENTLOOP_RUN_DIR")}` 建立 env 並傳給 `Popen`。這兩個變數是「工作流行程與 web 控制台」之間的互動埠，`claude` 子行程及它執行的工具指令都不是提問方，不應該繼承。父行程自己讀取 `AGENTLOOP_RUN_DIR` 寫 session 檔的既有邏輯不變。

`is_interactive()` 的判斷順序不變：網頁模式下沒有 tty，若先看 `isatty()`，網頁提問會全部失效。

## Architecture Decisions

### Decision: 只提供深色主題，不做主題切換

使用者選擇整體翻轉為深色主題；不提供淺色／深色切換，也不跟隨系統偏好。所有色值仍集中於 `@theme`，未來若要加切換，只需改為在 `:root` / `.dark` 下覆寫同名 CSS 變數，元件不需更動。

### Decision: 對比度不列為規格驗收條件

依使用者決定，背景分層與文字對比只作為本設計的色值選擇依據（上表三層底色遞增、前景淺色），不寫入 spec，也不撰寫計算對比度的測試。

### Decision: 次要按鈕外觀以 `@utility` 收斂，不抽元件

審查指出次要按鈕 class 在 11 處重複。使用者選擇在 `style.css` 定義 `@utility btn-secondary`，而非新增 `BaseButton.vue` 或 TS class 常數：模板結構與既有測試 selector 不變、不需新增元件測試，且與「樣式集中於 `style.css`」的既有慣例一致。utility 只含外觀，尺寸留在呼叫點，因此畫面完全不變。

### Decision: 以測試隔離＋子行程 env 過濾修正卡死，不改互動埠判斷邏輯

使用者選擇兩層都修，而不是只修其中一層，也不是調整 `is_interactive()` 的優先序。conftest 讓測試套件在任何環境下都可以重現；子行程過濾從根源避免 agent 在任何目標專案執行的指令誤入網頁模式。互動埠本身的語意（設定環境變數即為網頁模式）維持不變。

## Testing Strategy

### Seam（測試接縫）

- **首選接縫**：`ActiveChanges` 元件掛載後的 DOM（既有 `src/__tests__/ActiveChanges.spec.ts`，`vi.mock('../api')`）。jsdom 不計算 Tailwind CSS，因此斷言狀態對應的 class 名稱（色條 `border-l-stage-*`、徽章 `bg-stage-*`、光暈 `animate-breathe`）與徽章文字，色碼本身以 `style.css` 為準。
- **後端接縫（審查修補）**：(1) 以 `subprocess.run` 在設定網頁模式環境變數的情況下執行子 `pytest`（加 timeout），驗證測試套件不會卡住，這是行為層級的回歸測試；(2) 攔截 `subprocess.Popen` 呼叫 `_run_claude_once`，斷言傳出的 `env` 不含這兩個變數。`Popen` 以 `unittest.mock.patch` 替換成回傳空 stdout 的假物件，不會真的啟動 `claude`。
- **次要接縫**：`npm run build`（`vue-tsc -b && vite build`）確認 Tailwind 能產生新 token 與 `animate-breathe` utility；其他元件純樣式變動（含 `btn-secondary` 收斂）以既有測試全數通過為準，不新增樣式斷言。

### 測試案例矩陣（Test Matrix）

| 輸入值 / 情境 | 預期結果 | 斷言 Target / Reject Key |
| --- | --- | --- |
| `feat-login`：analyze_plan 完成、human_confirm 完成、execute 執行中、review／archive 尚未開始（主路徑逐步範例） | 五張卡片 `data-status` 依序 done、done、running、pending、pending；色條依序綠綠藍灰灰；徽章文字依序「完成」「完成」「執行中」「尚未開始」「尚未開始」；只有 execute 帶光暈 | `.stage-card` 的 `border-l-stage-*` class；`.stage-status` 的 `bg-stage-*` class 與文字；`animate-breathe` 只出現在第 3 張 |
| 無任何執行中任務 | 顯示「目前沒有執行中的任務」與「新增任務」按鈕 | `.empty-state` 文字與按鈕 |
| 父行程設定 `AGENTLOOP_INTERACTION=web` 與不存在的 `AGENTLOOP_RUN_DIR`，執行子 `pytest tests/test_human_confirm.py`（逐步：子 pytest 繼承環境變數 → conftest 清除變數 → `isatty` patch 生效 → 走 CLI 分支 → 測試結束） | 在 timeout 內結束，returncode 0 | 未拋出 `subprocess.TimeoutExpired`；`returncode == 0` |
| 設定這兩個變數後呼叫 `_run_claude_once` | 傳給 `Popen` 的 env 不含這兩個變數，保留 `PATH` 等其他變數 | `Popen` 呼叫參數 `env` 的鍵 |
| 舊任務沒有階段狀態紀錄 | 五張卡片皆為尚未開始（灰）、無光暈 | 既有測試沿用 `data-status`，不需改 |

## Technical Debt & Follow-up Notes

- 色值以肉眼判斷層次，未以自動化測試驗證對比度；若日後需要，可新增讀取 `@theme` 色值並計算 WCAG 對比度的測試。
- 尚無淺色主題與切換開關。
- 主要按鈕 class 仍在 8+ 處重複，且部分呼叫點缺 `focus-visible:ring-2`；本次未處理，日後可比照 `btn-secondary` 收斂為 `btn-primary`。
