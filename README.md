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

容器內的 Claude Code 登入狀態**刻意不與 host 共用**（存在獨立的 `agent_home` named volume），所以即使你 host 上已經登入過 `claude`，容器內第一次仍需要另外登入一次：

```bash
docker exec -it agent_loop claude login
```

登入狀態會保存在 `agent_home` volume 裡，容器重建（`docker compose up`/`down`）不會遺失，只有主動 `docker compose down -v` 才會清掉。也可以改用專屬的 `ANTHROPIC_API_KEY` 環境變數（寫進 `.env`）取代登入，兩種方式擇一即可。

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

---

## Agent 流程簡介

四個節點依序（含審查失敗的重試迴圈）串接，狀態透過同一個 `AgentState` 字典在節點間傳遞：

| 節點            | 角色       | 說明                                                                                                          |
| --------------- | ---------- | ------------------------------------------------------------------------------------------------------------- |
| `analyze_plan`  | 規劃 Agent | 讀取任務與目標專案程式碼，必要時互動式提問釐清需求，輸出結構化 TASK 清單與規格文件                            |
| `human_confirm` | 人工確認閘 | 顯示計畫摘要，等待使用者輸入 `y` 確認才放行；也可輸入修改意見打回重新規劃，或直接中止                         |
| `execute`       | 執行 Agent | 依序完成計畫中的每個 TASK：改程式碼、同步商業邏輯文件、跑測試並修復失敗                                       |
| `review`        | 審查 Agent | 唯讀方式比對 `git diff HEAD`，從 Standards（是否符合專案規範）與 Spec（是否符合規格）兩軸審查，判定是否可合併 |

審查沒通過時，依問題嚴重程度標記「重寫」或「修補」，回到 `analyze_plan` 針對審查意見重新規劃，再次經過人工確認後重跑 `execute` → `review`，最多重試 3 輪，超過即強制結束。

![image](https://hackmd.io/_uploads/BJrOA-xLGx.png)
![image](https://hackmd.io/_uploads/r1DKCZxLGl.png)
![image](https://hackmd.io/_uploads/ry3hRWg8fg.png)
![image](https://hackmd.io/_uploads/HJdT0ZgIGl.png)
![image](https://hackmd.io/_uploads/BJbC0bgIGe.png)
![image](https://hackmd.io/_uploads/rygkJze8fe.png)
![image](https://hackmd.io/_uploads/HJOkJfeLGl.png)
![image](https://hackmd.io/_uploads/HJee1fg8fe.png)
![image](https://hackmd.io/_uploads/Hk5eyMlUzl.png)

---

## 目標專案文件需求

`execute` 與 `review` 節點靠 `project_context.py` 動態偵測目標專案根目錄下的 `CLAUDE.md`（或 `AGENT.md` / `AGENTS.md`）來了解架構與慣例，不會把任何專案的目錄結構寫死在 prompt 裡。目標專案的說明檔**必須**涵蓋以下內容，Agent 才能正確規劃、實作與審查：

- **技術棧與架構**：使用的框架、語言版本、專案分層方式
- **指令**：測試、lint、type check、build 指令（`execute` 強制跑測試並自動修復失敗；找不到說明時才會退而求其次探索 `package.json` / `pyproject.toml` 等設定檔）
- **目錄慣例**：新檔案該放哪裡、命名規則
- **程式碼規範**：風格、i18n、型別、auto-generated 檔案等哪些可改、哪些不可改的規則（若另有 `CODING_STANDARDS.md` / `CONTRIBUTING.md`，`review` 節點也會一併讀取）

此外，目標專案根目錄下需要有 **`docs/` 目錄**存放商業邏輯說明文件（功能說明、資料流、模組/元件結構、業務規則）。`execute` 節點每次修改程式碼後都必須同步更新這些文件（若 `docs/` 不存在會自動建立），`review` 節點會驗證是否確實同步。

找不到任何說明檔時，Agent 會退回用 Read/Glob/Grep 自行探索程式碼風格，但規劃與審查的準確度會下降，建議每個目標專案都補上 `CLAUDE.md`。
