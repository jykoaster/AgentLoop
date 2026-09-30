## Purpose
「日誌分析（new）」頁面讓使用者檢視訪問日誌。

## Requirements

### Requirement: 頁面於 header 之下呈現 tab 標籤列

「日誌分析（new）」頁面 SHALL 於 header 之下、查詢列之下、表格之上呈現 tab 標籤列；本版本的 tab 標籤列 SHALL 僅包含「訪問日誌」一個 tab 標籤，且該 tab 於頁面停留期間永遠處於選中狀態。tab 標籤文字 SHALL 顯示為當前語系的「訪問日誌」對應字串。

#### Scenario: 頁面顯示訪問日誌單一 tab 標籤

逐步邏輯：使用者開啟頁面 → 系統在 header 下方渲染 tab 標籤列 → 使用者看到一個「訪問日誌」tab 標籤，且該 tab 為選中狀態。
- GIVEN 使用者具備日誌分析權限並開啟「日誌分析（new）」頁面
- WHEN 頁面完成初始化
- THEN 頁面於 header 之下、查詢列之下、表格之上顯示 tab 標籤列，內含且僅含一個 tab 標籤
- AND 該 tab 標籤顯示當前語系的「訪問日誌」文字
- AND 該 tab 標籤為選中狀態，且使用者於頁面停留期間該狀態不改變

#### Scenario: 切換語系後 tab 標籤文字隨語系更新

逐步邏輯：使用者切換語系 → tab 標籤文字改以新語系呈現。
- GIVEN 使用者已在「日誌分析（new）」頁面，tab 標籤顯示當前語系的「訪問日誌」文字
- WHEN 使用者切換至另一語系
- THEN tab 標籤文字改為新語系的「訪問日誌」對應字串
