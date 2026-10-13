"""
web/app.py（FastAPI）的 HTTP API 測試：TestClient 打 `/api/*`，以 tmp_path 建立假的
工作區根目錄。執行子行程以假的 `python -m` 替身取代真正的 workflow；search 的
`_ask_claude`／`_search` 以 monkeypatch 取代（直接 monkeypatch `search_api.search_specs`）。

函式名用英文。Scenario 標題的原文寫在該測試的 docstring 裡；同一個標題若前端測試也有，
docstring 在標題後加註「（API）」。
"""
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from AgentLoop.web import app as app_module
from AgentLoop.web import repo_view as repo_view_module
from AgentLoop.web import runner as runner_module
from AgentLoop.web import search_api as search_api_module


def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for condition")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTLOOP_WEB_STATE_DIR", str(tmp_path / ".web"))
    monkeypatch.setenv("TARGET_PROJECT", "my-project")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for mod in (app_module, repo_view_module, runner_module):
        monkeypatch.setattr(mod, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(runner_module, "_manager", runner_module.RunManager())
    (tmp_path / "my-project").mkdir()
    return tmp_path


@pytest.fixture
def client(workspace):
    return TestClient(app_module.app)


def _write_state(workspace: Path, change_name: str, **fields) -> Path:
    d = workspace / "my-project" / ".agentloop" / "changes" / change_name
    d.mkdir(parents=True)
    state = {
        "task": "test", "change_name": change_name, "branch_name": "", "iteration": 0,
        "analysis": "", "plan": [], "execution_result": "", "review_result": "",
        "review_level": "", "human_feedback": "", "stages": {}, "stage_notes": {},
    }
    state.update(fields)
    (d / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return d


def _write_openspec_change(workspace: Path, change_name: str, files: dict) -> Path:
    root = workspace / "my-project" / "openspec" / "changes" / change_name
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


class TestActiveChangesListing:
    def test_lists_one_row_of_stage_cards_per_active_change(self, client, workspace):
        """執行中任務分頁為每個未封存的 change 顯示一列階段卡片（API）"""
        _write_state(
            workspace, "feat-login",
            branch_name="feat/login", task="新增登入頁", iteration=0,
            stages={"analyze_plan": "done", "human_confirm": "done", "execute": "running",
                    "review": "pending", "archive": "pending"},
        )
        _write_state(workspace, "fix-typo")
        archive_dir = workspace / "my-project" / "openspec" / "changes" / "archive" / "2026-01-01-fix-typo"
        archive_dir.mkdir(parents=True)

        resp = client.get("/api/changes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        row = data[0]
        assert row["change_name"] == "feat-login"
        assert row["branch_name"] == "feat/login"
        assert row["task"] == "新增登入頁"
        assert row["iteration"] == 0
        assert row["stages"] == {
            "analyze_plan": "done", "human_confirm": "done", "execute": "running",
            "review": "pending", "archive": "pending",
        }

    def test_legacy_change_without_stages_shows_all_pending(self, client, workspace):
        """沒有階段狀態紀錄的舊任務以尚未開始顯示所有階段（API）"""
        d = workspace / "my-project" / ".agentloop" / "changes" / "legacy-change"
        d.mkdir(parents=True)
        (d / "state.json").write_text(json.dumps({"task": "舊任務"}), encoding="utf-8")

        data = client.get("/api/changes").json()
        assert len(data) == 1
        assert data[0]["stages"] == {
            "analyze_plan": "pending", "human_confirm": "pending", "execute": "pending",
            "review": "pending", "archive": "pending",
        }


class TestStageDetail:
    def test_stage_detail_returns_result_and_log(self, client, workspace):
        """點擊卡片後顯示該階段的執行結果與執行日誌（API）"""
        change_dir = _write_state(
            workspace, "feat-login",
            stages={"analyze_plan": "done", "human_confirm": "done", "execute": "done",
                    "review": "done", "archive": "pending"},
            review_result="## Standards\n無問題", review_level="修補",
        )
        logs_dir = change_dir / "logs"
        logs_dir.mkdir()
        lines = [f"\x1b[1;32mline {i}\x1b[0m" for i in range(1, 801)]
        (logs_dir / "review.log").write_text("\n".join(lines), encoding="utf-8")

        resp = client.get("/api/changes/feat-login/stages/review")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fields"]["review_level"] == "修補"
        assert data["fields"]["review_result"].startswith("## Standards")
        log_lines = data["log"].splitlines()
        assert len(log_lines) == 500
        assert log_lines[0] == "line 301"
        assert log_lines[-1] == "line 800"
        assert "\x1b" not in data["log"]


class TestRerunStage:
    def test_rerun_starts_at_stage_and_continues(self, client, workspace, monkeypatch):
        """重跑某階段時從該階段開始並接續後續流程（API）"""
        _write_state(
            workspace, "feat-login",
            stages={"analyze_plan": "done", "human_confirm": "done", "execute": "error",
                    "review": "done", "archive": "pending"},
        )
        script = workspace / "fake_rerun.py"
        script.write_text(
            "import os, time\n"
            "print('@@AGENTLOOP_STAGE execute@@', flush=True)\n"
            "time.sleep(60)\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(runner_module, "MAIN_CMD", [sys.executable, str(script)])

        resp = client.post("/api/changes/feat-login/rerun", json={"stage": "execute"})
        assert resp.status_code == 200
        assert resp.json()["change_name"] == "feat-login"
        assert resp.json()["stage"] == "execute"

        run = client.get("/api/run").json()
        assert run["active"] is True
        assert run["change_name"] == "feat-login"

        client.post("/api/run/abort")

    def test_rejects_invalid_stage(self, client, workspace):
        resp = client.post("/api/changes/feat-login/rerun", json={"stage": "human_confirm"})
        assert resp.status_code == 422


FAKE_NEW_TASK_SCRIPT = """\
import json
import os
import sys
import time

workspace = os.environ["FAKE_WORKSPACE_ROOT"]
target = os.environ.get("TARGET_PROJECT", "my-project")
task = sys.argv[1]

print("@@AGENTLOOP_STAGE analyze_plan@@", flush=True)
time.sleep(0.2)

change_dir = os.path.join(workspace, target, ".agentloop", "changes", "feat-login")
os.makedirs(change_dir, exist_ok=True)
with open(os.path.join(change_dir, "state.json"), "w", encoding="utf-8") as f:
    json.dump({
        "task": task, "change_name": "feat-login", "branch_name": "feat/login",
        "stages": {"analyze_plan": "running"}, "stage_notes": {},
    }, f)

time.sleep(60)
"""


class TestNewTaskChangeDetection:
    def test_new_task_starts_analyze_plan_question(self, client, workspace, monkeypatch):
        """新增任務後以 analyze_plan 卡片引導初始提問（change 偵測部分）（API）"""
        monkeypatch.setenv("FAKE_WORKSPACE_ROOT", str(workspace))
        script = workspace / "fake_new_task.py"
        script.write_text(FAKE_NEW_TASK_SCRIPT, encoding="utf-8")
        monkeypatch.setattr(runner_module, "MAIN_CMD", [sys.executable, str(script)])

        resp = client.post("/api/runs", json={"task": "新增登入頁"})
        assert resp.status_code == 201

        run = client.get("/api/run").json()
        assert run["active"] is True
        assert run["task"] == "新增登入頁"
        assert run["label"] == "新增登入頁"
        assert run["change_name"] == ""

        _wait_until(lambda: client.get("/api/run").json().get("change_name") == "feat-login")
        run2 = client.get("/api/run").json()
        assert run2["label"] == "feat-login"

        client.post("/api/run/abort")

    def test_blank_task_is_rejected(self, client, workspace):
        """任務描述為空白時無法送出新增任務（API 422 部分）"""
        resp = client.post("/api/runs", json={"task": "   "})
        assert resp.status_code == 422


class TestArchiveListing:
    def test_archive_lists_each_change_and_its_files(self, client, workspace):
        """已封存任務分頁每個封存 change 一列並可瀏覽其文件（API）"""
        archive_root = workspace / "my-project" / "openspec" / "changes" / "archive"
        (archive_root / "2026-09-01-feat-a").mkdir(parents=True)
        feat_b = archive_root / "2026-10-01-feat-b"
        feat_b.mkdir(parents=True)
        (feat_b / "proposal.md").write_text("# proposal", encoding="utf-8")
        (feat_b / "tasks.md").write_text("# tasks", encoding="utf-8")

        rows = client.get("/api/archive").json()
        assert rows[0] == {"dir": "2026-10-01-feat-b", "date": "2026-10-01", "name": "feat-b"}
        assert rows[1] == {"dir": "2026-09-01-feat-a", "date": "2026-09-01", "name": "feat-a"}

        files = client.get("/api/archive/2026-10-01-feat-b/files").json()
        assert files == ["proposal.md", "tasks.md"]

        content = client.get("/api/archive/2026-10-01-feat-b/files/proposal.md").json()
        assert content["content"] == "# proposal"


class TestSpecsListing:
    def test_specs_lists_each_domain_and_its_content(self, client, workspace):
        """既有 Spec 分頁列出每個 domain 並可檢視其規格內容（API）"""
        specs = workspace / "my-project" / "openspec" / "specs"
        (specs / "billing").mkdir(parents=True)
        (specs / "billing" / "spec.md").write_text("billing spec", encoding="utf-8")
        (specs / "auth").mkdir(parents=True)
        (specs / "auth" / "spec.md").write_text("auth spec", encoding="utf-8")

        domains = client.get("/api/specs").json()
        assert domains == ["auth", "billing"]

        content = client.get("/api/specs/auth").json()
        assert content["content"] == "auth spec"


class TestChangeFilesSorting:
    def test_change_files_open_from_the_row(self, client, workspace):
        """從任務列開啟該 change 的規格文件（檔案排序）（API）"""
        _write_openspec_change(workspace, "feat-login", {
            "tasks.md": "# tasks",
            "proposal.md": "# proposal",
            "specs/auth/spec.md": "# auth spec",
        })

        files = client.get("/api/changes/feat-login/files").json()
        assert files == ["proposal.md", "tasks.md", "specs/auth/spec.md"]

        content = client.get("/api/changes/feat-login/files/specs/auth/spec.md").json()
        assert content["content"] == "# auth spec"


class TestSpecSearch:
    def test_search_returns_answer_and_references(self, client, monkeypatch):
        """輸入問題搜尋規格後顯示回答與參考檔案（API）"""
        monkeypatch.setattr(
            search_api_module, "search_specs",
            lambda project, query: {
                "answer": "登入失敗 5 次會鎖定 15 分鐘。",
                "references": [{"path": "openspec/specs/auth/spec.md", "doc_type": "spec"}],
            },
        )
        resp = client.post("/api/specs/search", json={"query": "登入失敗幾次會鎖定？"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "登入失敗 5 次會鎖定 15 分鐘。"
        assert data["references"] == [{"path": "openspec/specs/auth/spec.md", "doc_type": "spec"}]

    def test_search_with_no_match_returns_not_found(self, client, workspace):
        """規格中找不到相關內容時顯示查無結果訊息（API）"""
        resp = client.post("/api/specs/search", json={"query": "任何問題"})
        assert resp.status_code == 200
        assert resp.json() == {"answer": "規格文件中沒有找到相關內容。", "references": []}

    def test_search_failure_returns_error(self, client, monkeypatch):
        """搜尋失敗時顯示錯誤訊息並保留查詢文字（502 部分）（API）"""
        def _raise(project, query):
            raise search_api_module.SearchFailed("claude CLI error: not logged in")

        monkeypatch.setattr(search_api_module, "search_specs", _raise)
        resp = client.post("/api/specs/search", json={"query": "登入規則？"})
        assert resp.status_code == 502
        assert resp.json()["detail"] == "搜尋失敗：claude CLI error: not logged in"


class TestSettings:
    def test_settings_shows_current_values_and_saves(self, client, workspace):
        """設定分頁顯示目前設定並可儲存（API）"""
        initial = client.get("/api/settings").json()
        assert set(initial.keys()) == {
            "target_project", "oauth_token", "api_key", "workspace_root", "run_active",
        }

        resp = client.put("/api/settings", json={"api_key": "sk-ant-api03-...abcd"})
        assert resp.status_code == 200
        assert resp.json()["api_key"] == {"set": True, "last4": "abcd"}

        after = client.get("/api/settings").json()
        assert after["api_key"] == {"set": True, "last4": "abcd"}

    def test_rejects_target_project_change_while_run_active(self, client, workspace, monkeypatch):
        """有執行進行中時無法變更目標專案（409 部分）（API）"""
        script = workspace / "fake_sleep.py"
        script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        monkeypatch.setattr(runner_module, "MAIN_CMD", [sys.executable, str(script)])
        client.post("/api/runs", json={"task": "t"})

        resp = client.put("/api/settings", json={"target_project": "other"})
        assert resp.status_code == 409

        client.post("/api/run/abort")


class TestFolderPicker:
    def test_folder_picker_sets_target_project_when_unset(self, client, workspace):
        """尚未指定目標專案時開啟資料夾選擇器並以選定資料夾作為目標專案（/fs 部分）（API）"""
        (workspace / "AgentLoop").mkdir()
        (workspace / ".cache").mkdir()

        folders = client.get("/api/fs", params={"path": ""}).json()
        assert sorted(folders) == ["AgentLoop", "my-project"]

        resp = client.put("/api/settings", json={"target_project": "my-project"})
        assert resp.status_code == 200
        assert resp.json()["target_project"] == "my-project"
