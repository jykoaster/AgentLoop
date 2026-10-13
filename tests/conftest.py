import pytest


@pytest.fixture(autouse=True)
def _clear_web_interaction_env(monkeypatch):
    """避免呼叫 pytest 的外部 shell（含 web 控制台啟動的子行程）殘留的網頁模式環境變數，
    讓需要網頁模式的測試之外都走命令列分支。"""
    monkeypatch.delenv("AGENTLOOP_INTERACTION", raising=False)
    monkeypatch.delenv("AGENTLOOP_RUN_DIR", raising=False)
