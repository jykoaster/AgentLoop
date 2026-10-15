"""
web/settings.py 測試：`.web/settings.json` 讀寫、合併 `.env`、secret 遮罩、
工作區根目錄邊界檢查。
"""
import os
import pytest

from AgentLoop.web import settings as web_settings


@pytest.fixture(autouse=True)
def _isolated_state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTLOOP_WEB_STATE_DIR", str(tmp_path / ".web"))
    monkeypatch.delenv("TARGET_PROJECT", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


class TestSecretFieldsBlankOnSaveKeepsOriginalValue:
    def test_blank_credentials_keep_existing_values(self, tmp_path):
        """認證欄位留空儲存時保留原本的值"""
        workspace_root = str(tmp_path)
        web_settings.update_settings({"oauth_token": "sk-ant-oat01-xxxx9xYz"}, workspace_root)

        view = web_settings.update_settings(
            {"target_project": "", "oauth_token": ""},
            workspace_root,
        )

        assert view["oauth_token"]["set"] is True
        assert view["oauth_token"]["last4"] == "9xYz"


class TestRejectsPathOutsideWorkspaceRoot:
    def test_path_outside_workspace_is_rejected(self, tmp_path):
        """選擇工作區根目錄以外的路徑時拒絕並提示"""
        workspace_root = str(tmp_path / "workspace")
        os.makedirs(workspace_root)
        web_settings.update_settings({"target_project": "my-project"}, workspace_root)

        with pytest.raises(web_settings.InvalidTargetProject) as exc:
            web_settings.update_settings({"target_project": "../etc"}, workspace_root)

        assert str(exc.value) == web_settings.OUTSIDE_WORKSPACE_ERROR
        view = web_settings.get_settings_view(workspace_root)
        assert view["target_project"] == "my-project"


class TestListSubfolders:
    def test_lists_only_visible_subfolders_sorted(self, tmp_path):
        (tmp_path / "AgentLoop").mkdir()
        (tmp_path / "my-project").mkdir()
        (tmp_path / ".cache").mkdir()
        (tmp_path / "a-file.txt").write_text("x")

        assert web_settings.list_subfolders(str(tmp_path), "") == ["AgentLoop", "my-project"]

    def test_rejects_path_outside_root(self, tmp_path):
        with pytest.raises(web_settings.InvalidTargetProject):
            web_settings.list_subfolders(str(tmp_path), "../outside")


class TestEffectiveValuePrecedence:
    def test_settings_file_overrides_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TARGET_PROJECT", "from-env")
        web_settings.update_settings({"target_project": "from-settings"}, str(tmp_path))
        assert web_settings.effective_value("TARGET_PROJECT") == "from-settings"

    def test_falls_back_to_env_when_unset(self, monkeypatch):
        monkeypatch.setenv("TARGET_PROJECT", "from-env")
        assert web_settings.effective_value("TARGET_PROJECT") == "from-env"
