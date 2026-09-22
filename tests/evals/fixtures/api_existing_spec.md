## Purpose
管理平台文章的 CRUD 操作，對外提供 REST API 供前端及第三方整合使用。

## Requirements

### Requirement: 文章列表查詢
The system SHALL provide a cursor-based paginated list of articles via GET /api/articles, accepting `cursor` (opaque string) and `pageSize` (integer, 1–100) query parameters, and returning an array of article summaries along with a `nextCursor` field (null when no more pages exist).

#### Scenario: 首次查詢文章列表
逐步邏輯：呼叫端不帶 cursor 發送請求；伺服器從最新一篇開始取最多 pageSize 篇；回傳文章陣列及 nextCursor
- GIVEN 呼叫端帶入合法的 pageSize 參數（1–100），不帶 cursor
- WHEN 發送 GET /api/articles?pageSize=20
- THEN 回傳 HTTP 200，body 含 `articles` 陣列（每項含 id、title、authorId、publishedAt）及 `nextCursor` 字串；若文章總數 ≤ pageSize，則 nextCursor 為 null

#### Scenario: 游標分頁翻頁
- GIVEN 呼叫端帶入上一頁回傳的 nextCursor 值及相同的 pageSize
- WHEN 發送 GET /api/articles?cursor=<nextCursor>&pageSize=20
- THEN 回傳下一批文章陣列，不含上一頁已回傳的文章；達最後一頁時 nextCursor 為 null

### Requirement: 文章批次刪除
The system SHALL allow deleting multiple articles in a single request via DELETE /api/articles/batch, accepting an `ids` array (1–50 UUIDs) in the request body, and returning the count of successfully deleted articles as `deletedCount`.

#### Scenario: 批次刪除指定文章
逐步邏輯：呼叫端提供文章 ID 清單；伺服器驗證呼叫端具備刪除權限後逐一刪除；回傳刪除筆數
- GIVEN 呼叫端具備管理員權限，request body 含 `ids` 陣列（1–50 個 UUID）
- WHEN 發送 DELETE /api/articles/batch
- THEN 回傳 HTTP 200，body 含 `deletedCount`（integer）等於成功刪除的文章數；不存在的 ID 不計入且不報錯
