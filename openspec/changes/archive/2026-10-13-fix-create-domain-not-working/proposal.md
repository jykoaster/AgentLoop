# Proposal: 修正網頁選擇 domain 時點擊「建立新 domain」無反應

## Intent

規範目的：讓使用者在網頁控制台回答「本次需求歸屬於哪一個既有 domain？」這題時，點任何一個選項按鈕（包含「以上皆非，建立新 domain」）都能讓工作流確實往下走。點既有 domain 就以該 domain 繼續規劃；點建立新 domain 就接著出現「新 domain 名稱」文字題。結果要和在終端輸入同一個編號完全一樣。

規範背景：網頁的選項按鈕只有在選項開頭是「N. 」時，才會把編號 N 交給工作流；沒有編號的選項會原樣送出整段文字。domain 歸屬題的選項目前是「web-gui」「以上皆非，建立新 domain」這類沒有編號的文字。工作流只接受編號或既有 domain 名稱，收到「以上皆非，建立新 domain」這段文字就判定無效，又重新問同一題。使用者看到的是同一題原地重現，像是按了沒反應。點既有 domain 剛好不受影響，因為送出的名稱本身就合法。

## Scope

In scope:

- domain 歸屬提問的選項改成帶編號的格式（「1. <domain>」…「N. 以上皆非，建立新 domain」），跟 grilling 選項題的格式一致
- 補上網頁模式下 domain 歸屬提問的測試，並在 ARCHITECTURE.md 同步說明
- 抽出共用的「編號. 文字」組字 helper，讓 domain 歸屬提問與 review 建議選擇題的終端清單和選項題選項都用同一份編號清單（純重構，可觀察行為不變）

Out of scope:

- 網頁選項按鈕的通用解析規則（前端不改）
- 命令列的提示文字與輸入規則（維持原樣，仍可用逗號輸入多個編號）
- 回覆無效時在網頁上的錯誤提示
- review 建議選擇題的行為（只抽共用編號組字，提示文字與選擇邏輯不變）
- 其他選項題

## Approach

修正點在後端 `nodes/analyze_plan.py` 的 `_ask_domain_selection()`：送給 `interaction.ask(kind="choice", options=...)` 的 `options` 改成 `f"{i}. {d}"`，最後一項是 `f"{new_idx}. 以上皆非，建立新 domain"`。網頁的 `QuestionForm.vue` 原本就會用 `^(\d+)\.\s*` 把「N. 」選項轉成 `"N"` 送出，後端現有的解析邏輯（數字編號、逗號複選、`new_idx` 判斷、接著 `_ask_new_domain_name()`）全部沿用，不需要修改。終端 `print()` 出的清單原本就帶編號，命令列行為不變。

編號組字統一由 `lib/interaction.py` 新增的公開函式 `numbered(items: list[str]) -> list[str]` 負責：回傳 `["1. a", "2. b", ...]`，編號從 1 開始連續遞增。`_ask_domain_selection()` 以 `numbered(domains + ["以上皆非，建立新 domain"])` 產生清單，`options=` 直接使用；終端 `print()` 迴圈改成走訪這份清單，再套用原本的顏色與縮排（`new_idx = len(domains) + 1` 仍用於解析答案）。`nodes/review.py` 的建議選擇題同樣以 `numbered(suggestions)` 產生清單，供終端 `print()` 與 `options=` 共用，印出的文字、縮排與選擇邏輯維持不變。
