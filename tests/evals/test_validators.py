"""Unit tests for OpenSpec delta structural validators (no Claude CLI)."""
from .validators import check_no_split_same_trigger_scenarios


def test_same_given_when_under_one_requirement_must_merge():
    spec = """
## MODIFIED Requirements

### Requirement: 頁面於 header 之下呈現 tab 標籤列

#### Scenario: 頁面顯示訪問日誌單一 tab 標籤
- GIVEN 使用者具備日誌分析權限並開啟「日誌分析（new）」頁面
- WHEN 頁面完成初始化
- THEN 頁面顯示「訪問日誌」tab 且為選中狀態

#### Scenario: 頁面 tab 列同時包含 OWASP 日誌 tab
- GIVEN 使用者具備日誌分析權限並開啟「日誌分析（new）」頁面
- WHEN 頁面完成初始化
- THEN 頁面另外顯示「OWASP 日誌」tab
"""
    ok, msg = check_no_split_same_trigger_scenarios(spec)
    assert not ok
    assert "頁面顯示訪問日誌單一 tab 標籤" in msg
    assert "頁面 tab 列同時包含 OWASP 日誌 tab" in msg


def test_different_when_is_a_separate_branch():
    spec = """
### Requirement: 頁面於 header 之下呈現 tab 標籤列

#### Scenario: 頁面載入後 tab 列顯示本頁提供的日誌類型且預設選中訪問日誌
- GIVEN 使用者具備日誌分析權限並開啟「日誌分析（new）」頁面
- WHEN 頁面完成初始化
- THEN tab 列依序顯示「訪問日誌」與「OWASP 日誌」，且「訪問日誌」為選中狀態

#### Scenario: 使用者點擊 OWASP 日誌 tab 後被選中並顯示 OWASP 表格容器
- GIVEN 使用者位於「日誌分析（new）」頁面，「訪問日誌」tab 為選中狀態
- WHEN 使用者點擊「OWASP 日誌」tab
- THEN 「OWASP 日誌」tab 改為選中狀態
"""
    ok, msg = check_no_split_same_trigger_scenarios(spec)
    assert ok, msg
