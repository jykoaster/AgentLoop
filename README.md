# AgentLoop

以 **LangGraph** 編排、由 **Claude Code CLI** 驅動的多 Agent 工作流程系統。輸入一句任務描述，系統會自動規劃、等待人工確認、實作、程式碼審查，審查沒過就自動重新規劃再跑一輪，直到通過或達重試上限。系統不假設固定的目標技術棧，透過偵測目標專案的 `CLAUDE.md` / `AGENT.md` 動態判斷架構與慣例。詳細節點設計見 [ARCHITECTURE.md](./ARCHITECTURE.md)。

---

## 安裝與使用

### 前置需求

- Docker / Docker Compose
- 目標專案的資料夾需與 `AgentLoop` 放在**同一個上層目錄**下（sibling 目錄），例如：

  ```
  ~/workspace/
  ├── AgentLoop/
  └── my-project/     ← 目標專案
  ```

  這是因為容器內是透過掛載進來的 host `docker.sock` 直接操控宿主的 Docker engine（Docker outside of Docker），宿主 daemon 建立 bind mount 時用的是掛載路徑字串本身，該路徑必須在 host 上真實存在。

### 設定

1. 在 `AgentLoop/` 下建立 `.env`：

   ```bash
   # AgentLoop 與目標專案的共同上層目錄（host 上的真實絕對路徑）
   HOST_WORKSPACE_ROOT=/Users/<you>/workspace

   # 目標專案的資料夾名稱（相對於 HOST_WORKSPACE_ROOT）
   TARGET_PROJECT=my-project
   ```

   `docker-compose.yml` 會依 `TARGET_PROJECT` 掛載 `${HOST_WORKSPACE_ROOT}/${TARGET_PROJECT}`，不需要再手動改 `docker-compose.yml`。

   **需要同時掛載多個目標專案時**：目前只內建一個 `TARGET_PROJECT` 環境變數，若要擴充，在 `.env` 依樣新增 `TARGET_PROJECT_2`、`TARGET_PROJECT_3`……，並在 `docker-compose.yml` 的 `volumes` 底下依樣加一行：

   ```yaml
   - ${HOST_WORKSPACE_ROOT}/${TARGET_PROJECT_2}:${HOST_WORKSPACE_ROOT}/${TARGET_PROJECT_2}
   ```

   （`docker-compose.yml` 內已有對應註解提示這一點。）

2. 確認目標專案內已放好 [`CLAUDE.md` / `AGENT.md`](#目標專案文件需求)——這是系統判斷架構與慣例的主要依據。

### 建置與啟動容器

```bash
docker compose build
docker compose up -d
```

容器啟動後會保持存活（`tail -f /dev/null`），透過 `docker exec` 進入下指令：

```bash
docker exec -it agent_loop bash
```

### 首次使用：容器內登入 Claude Code

容器內的 Claude Code 登入狀態**刻意不與 host 共用**（存在獨立的 `agent_home` named volume），所以即使你 host 上已經登入過 `claude`，容器內第一次仍需要另外設定一次認證。

**建議做法：用 `claude setup-token` 產生長效 token**，而不是在容器內跑互動式 `claude login`——`docker exec -it` 是嵌套 TTY，貼上瀏覽器給的授權碼時常因終端機的 paste 處理（多帶換行符、截斷）或碼過期而顯示 `Invalid code`。改用 token 可以完全避開這段互動貼碼流程：

1. 在 **host**（瀏覽器登入沒問題的地方）執行：

   ```bash
   claude setup-token
   ```

   走一次瀏覽器授權後，會印出一個長效 token。

2. 把這個 token 寫進 `AgentLoop/.env`：

   ```bash
   CLAUDE_CODE_OAUTH_TOKEN=<setup-token 產生的 token>
   ```

   `docker-compose.yml` 的 `env_file: .env` 會自動把它帶進容器，之後容器內的 `claude` 不需要再另外登入。

3. 若之前已經跑過互動式 `claude login` 而積了一份登入狀態在 `agent_home` volume 裡也沒關係，兩者可以並存；`.env` 裡的 `CLAUDE_CODE_OAUTH_TOKEN` 會被讀取使用。

**替代做法**：也可以改用專屬的 `ANTHROPIC_API_KEY` 環境變數（同樣寫進 `.env`）取代登入——差別是這條路走 API 用量計費，而非 Claude 訂閱額度。

**若仍想用互動式登入**（例如沒有 Claude 訂閱、只能走 OAuth 免費額度），可以跑：

```bash
docker exec -it agent_loop claude login
```

登入狀態會保存在 `agent_home` volume 裡，容器重建（`docker compose up`/`down`）不會遺失，只有主動 `docker compose down -v` 才會清掉。但如上述，這條路在 `docker exec -it` 底下貼授權碼容易失敗，優先用 `setup-token` 或 `ANTHROPIC_API_KEY`。

> 為什麼不能跟 host 共用登入狀態：如果容器直接掛載 host 的 `~/.claude`，host 與容器內的 `claude` process 會共用同一份 OAuth 憑證檔。兩邊同時使用 `claude` 時，token refresh 會互相搶寫，可能導致容器執行到一半認證失效報錯，或剛啟動時讀到寫入中的檔案而顯示未登入。獨立登入後這兩個問題都不會再發生，代價是多佔用一個 session／可能產生額外的 API 用量。

### 執行 Agent 工作流

在容器內、工作目錄 `${HOST_WORKSPACE_ROOT}` 下執行：

```bash
# 完整工作流（規劃 → 人工確認 → 執行 → 審查，含重試迴圈）
python -m AgentLoop.main "幫我在後端新增一個 GET /tables/featured 端點"

# 只單獨執行某一個 node，方便除錯（human_confirm 不支援單獨執行）
python -m AgentLoop.main --node analyze_plan "任務描述"
python -m AgentLoop.main --node execute --state-file /tmp/state.json "任務描述"
python -m AgentLoop.main --node review "任務描述"
```

完整工作流跑到 `human_confirm` 時會暫停，在終端機顯示規劃摘要與 TASK 清單，輸入 `y` 才會繼續往下執行。

執行過程中，`analyze_plan` 第一次進行初始規劃時會先在終端機詢問 OpenSpec change 名稱（kebab-case）：直接輸入想要的名稱即可，Claude 會據此在目標專案下建立 `openspec/changes/<名稱>/`；若直接按 Enter 留空，則改用當時目標專案的 git branch 名稱作為 change 名稱。此值會沿用到同一個任務後續的重新規劃／依人工意見調整計畫，不會重複問、也不會重新命名既有 change。

規格文件遵照 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 的 change/spec-delta 規則，寫在**目標專案**（不是 AgentLoop 這個 repo）下的 `openspec/changes/<change 名稱>/`（`proposal.md`/`design.md`/`tasks.md`/`specs/<domain>/spec.md`）。目標專案第一次被處理時，若尚未有 `openspec/` 目錄，`analyze_plan` 會自動執行一次 `openspec init` bootstrap，不需要手動介入；`openspec` CLI 已由 Dockerfile 自動安裝在容器內。審查通過後，最後一個節點會呼叫 `openspec archive` 把這次的規格差異併入目標專案持久的 `openspec/specs/`，跨任務累積成完整的行為規格。

---

## Agent 流程簡介

五個節點依序（含審查失敗的重試迴圈）串接，狀態透過同一個 `AgentState` 字典在節點間傳遞：

| 節點             | 角色              | 說明                                                                                                                      |
| ---------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `analyze_plan`   | 規劃 Agent        | 讀取任務與目標專案程式碼，必要時互動式提問釐清需求，輸出結構化 TASK 清單與 OpenSpec change 規格文件                       |
| `human_confirm`  | 人工確認閘        | 顯示計畫摘要，等待使用者輸入 `y` 確認才放行；也可輸入修改意見打回重新規劃，或直接中止                                     |
| `execute`        | 執行 Agent        | 依序完成計畫中的每個 TASK：改程式碼、同步商業邏輯文件、跑測試並修復失敗、勾選 tasks.md 對應項目                           |
| `review`         | 審查 Agent        | 唯讀方式比對 `git diff HEAD`，從 Standards（是否符合專案規範）與 Spec（是否符合規格）兩軸審查，判定是否可合併             |
| `archive_change` | 收尾（純 Python） | review 通過後，呼叫 `openspec archive` 把這次的規格差異併入目標專案持久的 `openspec/specs/`；失敗只印警告，不影響流程結束 |

審查只有在發現**嚴重影響功能**的問題時（核心邏輯錯誤、功能無法正常運作、架構根本偏差等）才自動標記「重寫」或「修補」、直接回到 `analyze_plan` 重新規劃；其餘不影響功能的修改建議會逐條列出，在終端機讓使用者選擇要修哪幾條（或全部不修，直接放行），只有選中至少一條才會回到 `analyze_plan` 針對選中的建議重新規劃。重新規劃後再次經過人工確認才重跑 `execute` → `review`，最多重試 3 輪，超過即強制結束（且不會 archive）。

---

## 使用的 Skills

各節點透過 `skill_loader.py` 從 host 掛載進來的 `~/.claude/skills/` 讀取下列 skill 並注入 prompt。「完整內容」欄為是的 skill，因流程細節（提問方式、文件存放規則、平行 sub-agent 呼叫方式等）必須完整注入才能正確遵循；其餘只列出名稱供 Claude 自行判斷是否採用（節省 token）。

| Skill                                                                                                     | 使用節點                  | 完整內容 | 用途                                                                      |
| ----------------------------------------------------------------------------------------------------------- | ------------------------- | -------- | ------------------------------------------------------------------------- |
| [`grill-with-docs`](https://github.com/mattpocock/skills/blob/main/skills/engineering/grill-with-docs/SKILL.md) | `analyze_plan`            | 是       | 初始規劃／依人工意見重新規劃時，互動式逐一提問釐清需求                     |
| [`grilling`](https://github.com/mattpocock/skills/blob/main/skills/productivity/grilling/SKILL.md)             | `analyze_plan`            | 是       | 提供 `grill-with-docs` 的提問流程本體                                     |
| [`domain-modeling`](https://github.com/mattpocock/skills/blob/main/skills/engineering/domain-modeling/SKILL.md) | `analyze_plan`            | 是       | 提問過程中即時記錄詞彙與 ADR                                              |
| [`to-spec`](https://github.com/mattpocock/skills/blob/main/skills/engineering/to-spec/SKILL.md)                 | `analyze_plan`            | 是       | 規格文件撰寫依據（實際輸出格式由 `_SPEC_TEMPLATE` 固定覆蓋）              |
| [`tdd`](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/SKILL.md)                         | `analyze_plan`、`execute` | 否       | 規劃「撰寫／更新測試」TASK、執行測試 TASK 時採紅-綠循環                    |
| [`implement`](https://github.com/mattpocock/skills/blob/main/skills/engineering/implement/SKILL.md)             | `execute`                 | 是       | 執行階段主流程依據（commit 與 `/code-review` 步驟由 `_SYSTEM` 覆蓋關閉）  |
| [`code-review`](https://github.com/mattpocock/skills/blob/main/skills/engineering/code-review/SKILL.md)         | `review`                  | 是       | Standards／Spec 兩軸審查，各自透過平行 sub-agent 產出報告                 |

以上 skill 皆來自 [`mattpocock/skills`](https://github.com/mattpocock/skills)，透過 `~/.agents/.skill-lock.json` 安裝到 `~/.agents/skills/`，再由 `~/.claude/skills/` 下的 symlink 指向、以唯讀方式掛載進容器。`_FULL_CONTENT_SKILLS`（`skill_loader.py`）白名單決定完整內容注入名單；node 各自的 `_SKILLS` 常數（`nodes/analyze_plan.py`、`nodes/execute.py`）決定該節點會用到哪些 skill。`review` 節點的 `code-review` 是直接呼叫 `build_skills_block(["code-review"])`，不透過 `_SKILLS` 常數。

（OpenSpec 的規格產出流程不透過此 skill 機制載入，而是寫死在 `analyze_plan.py` 的 prompt 常數中，並由 `openspec_runner.py` 直接呼叫 `openspec` CLI，詳見上方「執行 Agent 工作流」一節。）

---

## 目標專案文件需求

`execute` 與 `review` 節點靠 `project_context.py` 動態偵測目標專案根目錄下的 `CLAUDE.md`（或 `AGENT.md` / `AGENTS.md`）來了解架構與慣例，不會把任何專案的目錄結構寫死在 prompt 裡。目標專案的說明檔**必須**涵蓋以下內容，Agent 才能正確規劃、實作與審查：

- **技術棧與架構**：使用的框架、語言版本、專案分層方式
- **指令**：測試、lint、type check、build 指令（`execute` 強制跑測試並自動修復失敗；找不到說明時才會退而求其次探索 `package.json` / `pyproject.toml` 等設定檔）
- **目錄慣例**：新檔案該放哪裡、命名規則
- **程式碼規範**：風格、i18n、型別、auto-generated 檔案等哪些可改、哪些不可改的規則（若另有 `CODING_STANDARDS.md` / `CONTRIBUTING.md`，`review` 節點也會一併讀取）

是否需要在 `docs/` 目錄維護商業邏輯說明文件（功能說明、資料流、模組/元件結構、業務規則），由目標專案自己的說明檔決定：說明檔裡若有要求同步維護，`analyze_plan` 會排入對應的文件更新 TASK、`execute` 照做、`review` 驗證是否確實同步；說明檔未提及此類慣例時，AgentLoop 不會強制新增或更新文件。

找不到任何說明檔時，Agent 會退回用 Read/Glob/Grep 自行探索程式碼風格，但規劃與審查的準確度會下降，建議每個目標專案都補上 `CLAUDE.md`。

### 目標專案是否需要 Docker

視情況而定，不是所有目標專案都一定要有 Docker：

- **規劃／審查中的讀取類操作**（讀 `CLAUDE.md`、產出計畫、`git diff HEAD` 比對）不需要目標專案有 Docker，任何技術棧都能處理。
- 但 `execute` 與 `review` 節點**強制要執行目標專案的測試指令**，而 AgentLoop 容器本身只原生安裝了 **Python 3.11** 與 **Node.js 20**（見 `Dockerfile`）。因此：
  - 若目標專案是 Python／Node 專案，且測試不依賴額外服務（資料庫、cache 等），可以在 AgentLoop 容器內直接跑測試，**不需要**目標專案有 Docker。
  - 若目標專案使用其他語言、或測試需要額外服務，則**需要**目標專案本身能透過 `docker compose up` / `exec` 之類的指令啟動與跑測試——AgentLoop 容器內建 Docker CLI 並掛載 host 的 `docker.sock`（DooD，見上方「首次使用」前的 Docker outside of Docker 說明），正是為了讓 Agent 能在容器內對目標專案下這類指令；容器本身沒有其他語言 runtime，也不會另外起一顆 Docker daemon。
  - 這件事應該寫進目標專案的 `CLAUDE.md`／`AGENT.md`：測試指令若需要透過 `docker compose exec ...` 執行，直接寫清楚，Agent 才會照著跑，而不是誤用容器內不存在的原生指令。
