## Purpose
文章列表頁讓使用者瀏覽所有已發布文章，並透過分頁和統計資訊輔助決策。

## Requirements

### Requirement: 文章列表顯示
The system SHALL display a list of published articles showing each article's title, author name, and publication date, with numeric page buttons at the bottom for navigation.

#### Scenario: 進入文章列表頁
逐步邏輯：使用者進入頁面；系統載入第一頁文章；顯示列表與分頁控制
- GIVEN 使用者已登入並進入文章列表頁面
- WHEN 頁面完成載入
- THEN 顯示最多 20 筆文章，每筆含標題、作者姓名、發布日期（YYYY-MM-DD 格式）；頁面底部顯示數字頁碼按鈕，當前頁碼以高亮標示

#### Scenario: 切換頁碼
- GIVEN 文章總數超過 20 筆，使用者目前在第一頁
- WHEN 點擊第二頁按鈕
- THEN 列表更新為第 21–40 筆文章；頁碼高亮移至第 2 頁按鈕

### Requirement: 文章統計圖表
The system SHALL display a bar chart showing the number of articles published per month for the past 6 months, located above the article list.

#### Scenario: 顯示近六個月發文統計
逐步邏輯：系統計算過去 6 個月每月發布文章數；以長條圖呈現
- GIVEN 使用者進入文章列表頁
- WHEN 頁面完成載入
- THEN 圖表顯示最近 6 個月的月份標籤（MMM YYYY 格式）及對應的文章數量；無文章的月份顯示高度為零的長條
