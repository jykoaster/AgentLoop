"""Prompt eval tests for openspec-authoring skill.

Each test sends a natural-language task description to the Claude Code CLI
(using the openspec-authoring skill as --system-prompt) and validates that
the generated OpenSpec delta satisfies structural correctness rules.

Run inside the Docker container:
    pytest AgentLoop/tests/evals/ -v -m eval
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .validators import (
    check_has_intent,
    check_has_stepwise_scenario,
    check_no_diff_language,
    check_no_implementation_details_frontend,
    check_no_negative_scenarios,
    check_no_split_same_trigger_scenarios,
    check_tasks_delete_removed_scenarios,
    has_added,
    has_modified,
    has_removed,
)

pytestmark = pytest.mark.eval

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SKILL_PATH = (
    Path(__file__).parent.parent.parent
    / ".claude" / "skills" / "openspec-authoring" / "SKILL.md"
)
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def skill_content() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def api_existing_spec() -> str:
    return (FIXTURES_DIR / "api_existing_spec.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ui_existing_spec() -> str:
    return (FIXTURES_DIR / "ui_existing_spec.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ui_tab_existing_spec() -> str:
    return (FIXTURES_DIR / "ui_tab_existing_spec.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Claude CLI helper
# ---------------------------------------------------------------------------

_FILE_MARKER = re.compile(r"<!--\s*FILE:\s*(.+?)\s*-->")


def _call_claude(system_prompt: str, user_prompt: str, timeout: int = 180) -> str:
    """Call `claude -p` with a system prompt; return the result text."""
    if not shutil.which("claude"):
        pytest.skip("claude CLI not found")

    cmd = [
        "claude", "-p", user_prompt,
        "--system-prompt", system_prompt,
        "--allowedTools", "Read",
        "--output-format", "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    # Parse stream-json: find the last "result" event
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event.get("type") == "result":
                return event.get("result", "")
        except json.JSONDecodeError:
            continue

    # Fallback: return raw stdout (useful for debugging failures)
    return proc.stdout


_OUTPUTS_DIR = Path(__file__).parent / "outputs"


def generate_spec(
    skill_content: str,
    task: str,
    project_type: str,
    existing_spec: str = "",
    test_name: str = "",
) -> dict[str, str]:
    """Call Claude with the openspec-authoring skill; return parsed {file_path: content}.

    Raw output and each parsed file are written to tests/evals/outputs/<test_name>/
    for post-run inspection.
    """
    existing_block = (
        f"既有 spec（openspec/specs/<domain>/spec.md 目前內容）：\n\n{existing_spec}"
        if existing_spec
        else "（此 domain 尚不存在，全部使用 ADDED）"
    )

    user_prompt = f"""專案類型：{project_type}

{existing_block}

任務：{task}

請產生 OpenSpec delta 文件。每個檔案用 <!-- FILE: <path> --> 標記開頭，例如：
<!-- FILE: proposal.md -->
<!-- FILE: specs/articles/spec.md -->
<!-- FILE: tasks.md -->
至少輸出這三個檔案。"""

    raw = _call_claude(skill_content, user_prompt)

    # Save raw output for inspection
    if test_name:
        out_dir = _OUTPUTS_DIR / test_name
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "_raw.md").write_text(raw, encoding="utf-8")

    files: dict[str, str] = {}
    parts = _FILE_MARKER.split(raw)
    # parts[0] = preamble; then alternating: path, content, path, content...
    for i in range(1, len(parts), 2):
        path = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        # Strip outer ```markdown ... ``` fence that Claude sometimes adds
        content = _strip_outer_fence(content)
        files[path] = content
        if test_name:
            safe_name = path.replace("/", "_")
            (out_dir / safe_name).write_text(content, encoding="utf-8")

    return files


def _strip_outer_fence(text: str) -> str:
    """Remove a single wrapping ```[lang] ... ``` fence if present."""
    if not text.startswith("```"):
        return text
    first_nl = text.find("\n")
    if first_nl == -1:
        return text
    if text.rstrip().endswith("```"):
        inner = text[first_nl + 1 : text.rstrip().rfind("\n```")]
        return inner.strip()
    return text


def spec_file(files: dict[str, str]) -> str:
    """Return the first specs/<domain>/spec.md content found."""
    for path, content in files.items():
        if path.startswith("specs/") and path.endswith("spec.md"):
            return content
    # Fallback: any file with ADDED/MODIFIED/REMOVED markers
    for content in files.values():
        if any(kw in content for kw in ["## ADDED", "## MODIFIED", "## REMOVED"]):
            return content
    return ""


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


def test_api_spec_added(skill_content):
    """新增 API endpoint → ADDED Requirements，endpoint 合約可見（backend-api 例外）。"""
    task = (
        "新增 POST /api/articles endpoint，供使用者建立新文章。"
        "接受 title（string，最多 200 字）、content（string）、tags（string array）欄位；"
        "成功時回傳新建文章的 id（UUID）和 createdAt（ISO 8601 格式）。"
    )
    files = generate_spec(skill_content, task, project_type="backend-api", test_name="api_added")
    spec = spec_file(files)
    proposal = files.get("proposal.md", "")

    assert has_added(spec), "spec 應包含 ## ADDED Requirements"

    ok, msg = check_has_stepwise_scenario(spec)
    assert ok, f"spec 應有 GIVEN/WHEN/THEN 步驟：{msg}"

    ok, msg = check_has_intent(proposal)
    assert ok, f"proposal.md：{msg}"

    ok, msg = check_no_negative_scenarios(spec)
    assert ok, f"不應有負向 Scenario：{msg}"

    # backend-api：endpoint 與欄位名稱是可觀察合約，必須出現
    assert any(kw in spec for kw in ["POST /api/articles", "/api/articles", "POST"]), (
        "backend-api spec 應直接列出 endpoint path（這是可觀察合約，不是實作細節）"
    )


def test_api_spec_modified(skill_content, api_existing_spec):
    """修改 API 分頁方式 → MODIFIED Requirements，不用 diff 語言。"""
    task = (
        "將 GET /api/articles 文章列表查詢從 cursor-based 分頁改為 offset-based 分頁。"
        "移除 cursor 參數，新增 page（integer，1-based）和 pageSize（integer，預設 20，最大 100）參數；"
        "回傳結果新增 total 欄位（文章總筆數，integer）。"
    )
    files = generate_spec(skill_content, task, project_type="backend-api", existing_spec=api_existing_spec, test_name="api_modified")
    spec = spec_file(files)

    assert has_modified(spec), "spec 應包含有內容的 ## MODIFIED Requirements"

    ok, msg = check_no_diff_language(spec)
    assert ok, f"MODIFIED 不應用 diff 語言描述變化：{msg}"

    ok, msg = check_no_negative_scenarios(spec)
    assert ok, f"不應有負向 Scenario：{msg}"

    ok, msg = check_has_stepwise_scenario(spec)
    assert ok, f"spec 應有 GIVEN/WHEN/THEN 步驟：{msg}"


def test_api_spec_removed(skill_content, api_existing_spec):
    """移除 API endpoint → REMOVED Requirements，不加負向 Scenario 或 ADDED。"""
    task = (
        "移除 DELETE /api/articles/batch 批次刪除 endpoint。"
        "此功能使用率低且增加維護複雜度，使用者改以逐篇刪除方式操作。"
    )
    files = generate_spec(skill_content, task, project_type="backend-api", existing_spec=api_existing_spec, test_name="api_removed")
    spec = spec_file(files)

    assert has_removed(spec), "spec 應包含 ## REMOVED Requirements"

    ok, msg = check_no_negative_scenarios(spec)
    assert ok, f"不應以負向 Scenario 描述移除後狀態：{msg}"

    assert not has_added(spec), (
        "移除 endpoint 不應新增 ADDED Requirements（不需要宣告『無法批次刪除』）"
    )

    # Requirement 與其下 Scenario 都從 spec 消失，tasks 必須各別安排刪除測試任務
    tasks = files.get("tasks.md", "")
    ok, msg = check_tasks_delete_removed_scenarios(
        tasks, ["文章批次刪除", "批次刪除指定文章"]
    )
    assert ok, msg


# ---------------------------------------------------------------------------
# UI tests
# ---------------------------------------------------------------------------


def test_ui_spec_added(skill_content):
    """新增 UI 功能 → ADDED Requirements，業務語言，無實作細節。"""
    task = (
        "在文章列表頁新增關鍵字搜尋功能：使用者可在搜尋框輸入關鍵字，"
        "按下 Enter 或點擊搜尋按鈕後，列表即時過濾顯示標題或內文包含該關鍵字的文章；"
        "無結果時顯示「查無相符文章」提示訊息。"
    )
    files = generate_spec(skill_content, task, project_type="frontend", test_name="ui_added")
    spec = spec_file(files)
    proposal = files.get("proposal.md", "")

    assert has_added(spec), "spec 應包含 ## ADDED Requirements"

    ok, msg = check_no_implementation_details_frontend(spec)
    assert ok, f"frontend spec 不應含實作細節：{msg}"

    ok, msg = check_has_stepwise_scenario(spec)
    assert ok, f"spec 應有 GIVEN/WHEN/THEN 步驟：{msg}"

    ok, msg = check_has_intent(proposal)
    assert ok, f"proposal.md：{msg}"

    ok, msg = check_no_negative_scenarios(spec)
    assert ok, f"不應有負向 Scenario：{msg}"


def test_ui_spec_modified(skill_content, ui_existing_spec):
    """修改 UI 分頁方式 → MODIFIED Requirements，不含負向斷言，不含 diff 語言。"""
    task = (
        "將文章列表的分頁方式從數字按鈕分頁改為無限捲動載入："
        "使用者捲動到列表底部時自動載入下一批文章；"
        "當所有文章都已載入時，顯示「已顯示全部文章」提示；"
        "移除底部的頁碼按鈕。"
    )
    files = generate_spec(skill_content, task, project_type="frontend", existing_spec=ui_existing_spec, test_name="ui_modified")
    spec = spec_file(files)

    assert has_modified(spec), "spec 應包含有內容的 ## MODIFIED Requirements"

    ok, msg = check_no_implementation_details_frontend(spec)
    assert ok, f"frontend spec 不應含實作細節：{msg}"

    ok, msg = check_no_negative_scenarios(spec)
    assert ok, (
        f"不應用 MUST NOT 或負向 Scenario 宣告頁碼消失——應只描述無限捲動的正向行為：{msg}"
    )

    ok, msg = check_no_diff_language(spec)
    assert ok, f"MODIFIED 不應用 diff 語言：{msg}"

    # 切換頁碼 Scenario 從 MODIFIED requirement 消失，tasks 必須安排刪除測試任務
    tasks = files.get("tasks.md", "")
    ok, msg = check_tasks_delete_removed_scenarios(tasks, ["切換頁碼"])
    assert ok, msg


def test_ui_spec_sibling_tab_merges_init_scenario(skill_content, ui_tab_existing_spec):
    """同頁加 tab：改寫既有初始化 Scenario，不可並列「單一 tab」與「同時包含」。"""
    task = (
        "在「日誌分析（new）」頁面的 tab 列新增「OWASP 日誌」tab，"
        "與既有「訪問日誌」tab 並列；頁面載入時預設仍選中「訪問日誌」。"
        "使用者可點擊切換兩個 tab。"
        "不變更訪問日誌 tab 本身的查詢、續拉或欄位行為。"
    )
    files = generate_spec(
        skill_content,
        task,
        project_type="frontend",
        existing_spec=ui_tab_existing_spec,
        test_name="ui_sibling_tab",
    )
    spec = spec_file(files)

    assert has_modified(spec), "tab 列從一個變成兩個，應 MODIFIED 既有 tab 標籤列 Requirement"

    ok, msg = check_no_split_same_trigger_scenarios(spec)
    assert ok, f"同一觸發的初始化 Scenario 應合併成一條：{msg}"

    assert "單一 tab" not in spec, (
        "舊標題寫死「單一 tab」，MODIFIED 必須改寫該 Scenario 標題，"
        "不可留下舊條再並列一條「同時包含 OWASP」"
    )

    assert "訪問日誌" in spec and "OWASP" in spec, (
        "合併後的初始化 Scenario 應同時涵蓋訪問日誌與 OWASP 日誌"
    )

    tasks = files.get("tasks.md", "")
    ok, msg = check_tasks_delete_removed_scenarios(
        tasks, ["頁面顯示訪問日誌單一 tab 標籤"]
    )
    assert ok, msg


def test_ui_spec_removed(skill_content, ui_existing_spec):
    """移除 UI 功能 → REMOVED Requirements，不加負向 Scenario。"""
    task = (
        "移除文章列表頁的統計圖表區塊。"
        "此功能已整合至後台報表模組，前台列表頁不再顯示。"
    )
    files = generate_spec(skill_content, task, project_type="frontend", existing_spec=ui_existing_spec, test_name="ui_removed")
    spec = spec_file(files)

    assert has_removed(spec), "spec 應包含 ## REMOVED Requirements"

    ok, msg = check_no_negative_scenarios(spec)
    assert ok, (
        f"移除圖表不應寫成『MUST NOT 顯示圖表』的 Scenario，直接用 REMOVED 即可：{msg}"
    )

    assert not has_added(spec), "移除 UI 功能不應新增 ADDED Requirements"

    # Requirement 與其下 Scenario 都從 spec 消失，tasks 必須各別安排刪除測試任務
    tasks = files.get("tasks.md", "")
    ok, msg = check_tasks_delete_removed_scenarios(
        tasks, ["文章統計圖表", "顯示近六個月發文統計"]
    )
    assert ok, msg
