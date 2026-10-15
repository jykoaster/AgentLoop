"""唯讀瀏覽目標專案狀態：`.agentloop/changes/*/state.json`、
`openspec/changes(/archive)/`、`openspec/specs/`。不呼叫 Claude，純粹讀檔案。
"""
import json
import os
import re
from dataclasses import dataclass

from .runner import get_manager
from ..core.stages import STAGES
from ..lib import REPO_ROOT, branch_exists, list_branch_files, read_branch_file
from ..lib.openspec_runner import is_change_archived

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_LOG_TAIL_LINES = 500
_PRIORITY_FILES = ("proposal.md", "design.md", "tasks.md")
_ARCHIVE_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")


class NotFound(Exception):
    pass


def _safe_name(name: str) -> bool:
    return bool(name) and name not in (".", "..") and "/" not in name and os.sep not in name


def _require_safe_name(name: str, what: str) -> None:
    if not _safe_name(name):
        raise NotFound(f"找不到{what}：{name}")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _tail_lines(text: str, n: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:])


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _changes_root(project: str) -> str:
    return os.path.join(REPO_ROOT, project, ".agentloop", "changes")


def _change_dir(project: str, change_name: str) -> str:
    return os.path.join(_changes_root(project), change_name)


def _openspec_change_dir(project: str, change_name: str) -> str:
    return os.path.join(REPO_ROOT, project, "openspec", "changes", change_name)


def _archive_root(project: str) -> str:
    return os.path.join(REPO_ROOT, project, "openspec", "changes", "archive")


def _is_archived(project: str, change_name: str) -> bool:
    return is_change_archived(os.path.join(REPO_ROOT, project), change_name)


def list_active_changes(project: str) -> list[dict]:
    root = _changes_root(project)
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        state_path = os.path.join(root, name, "state.json")
        if not os.path.isfile(state_path) or _is_archived(project, name):
            continue
        state = _read_json(state_path) or {}
        stored_stages = state.get("stages") or {}
        stages = {s: stored_stages.get(s, "pending") for s in STAGES}
        out.append({
            "change_name": name,
            "branch_name": state.get("branch_name", ""),
            "task": state.get("task", ""),
            "iteration": state.get("iteration", 0),
            "stages": stages,
            "stage_notes": state.get("stage_notes") or {},
        })
    return out


def _persisted_log(project: str, change_name: str, stage: str) -> str:
    path = os.path.join(_change_dir(project, change_name), "logs", f"{stage}.log")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def get_stage_detail(project: str, change_name: str, stage: str) -> dict:
    _require_safe_name(change_name, "change")
    state_path = os.path.join(_change_dir(project, change_name), "state.json")
    state = _read_json(state_path)
    if state is None:
        raise NotFound(f"找不到 change：{change_name}")

    fields: dict = {}
    if stage == "analyze_plan":
        fields = {"analysis": state.get("analysis", ""), "plan": state.get("plan", [])}
    elif stage == "human_confirm":
        fields = {"status": state.get("status", ""), "human_feedback": state.get("human_feedback", "")}
    elif stage == "execute":
        fields = {"execution_result": state.get("execution_result", "")}
    elif stage == "review":
        fields = {"review_result": state.get("review_result", ""), "review_level": state.get("review_level", "")}

    live = get_manager().live_stage_log(change_name, stage)
    raw_log = live if live is not None else _persisted_log(project, change_name, stage)

    return {
        "status": (state.get("stages") or {}).get(stage, "pending"),
        "note": (state.get("stage_notes") or {}).get(stage, ""),
        "fields": fields,
        "log": _tail_lines(_strip_ansi(raw_log), _LOG_TAIL_LINES),
    }


def _markdown_sort_key(rel: str):
    if rel in _PRIORITY_FILES:
        return (0, _PRIORITY_FILES.index(rel))
    return (1, rel)


def _sort_markdown_paths(paths: list[str]) -> list[str]:
    return sorted((p for p in paths if p.endswith(".md")), key=_markdown_sort_key)


def _sorted_markdown_files(root: str) -> list[str]:
    found: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
            found.append(rel)
    return _sort_markdown_paths(found)


def _safe_join(root: str, rel_path: str) -> str:
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root, rel_path))
    if candidate != root_real and not candidate.startswith(root_real + os.sep):
        raise NotFound("路徑超出範圍")
    return candidate


def _list_markdown(root: str, missing_msg: str) -> list[str]:
    if not os.path.isdir(root):
        raise NotFound(missing_msg)
    return _sorted_markdown_files(root)


def _read_markdown(root: str, rel_path: str) -> str:
    path = _safe_join(root, rel_path)
    if not path.endswith(".md") or not os.path.isfile(path):
        raise NotFound(f"找不到檔案：{rel_path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _work_branch_name(project: str, change_name: str) -> str:
    state = _read_json(os.path.join(_change_dir(project, change_name), "state.json"))
    return (state or {}).get("branch_name", "")


@dataclass
class _WorktreeSource:
    root: str


@dataclass
class _BranchSource:
    branch: str
    files: list[str]


def _resolve_change_source(project: str, change_name: str) -> "_WorktreeSource | _BranchSource":
    root = _openspec_change_dir(project, change_name)
    if os.path.isdir(root):
        return _WorktreeSource(root)

    branch = _work_branch_name(project, change_name)
    if branch and branch_exists(project, branch):
        files, err = list_branch_files(project, branch, f"openspec/changes/{change_name}")
        if files is None:
            raise NotFound(f"找不到 change：{change_name}（git：{err}）")
        if files:
            return _BranchSource(branch, _sort_markdown_paths(files))

    raise NotFound(f"找不到 change：{change_name}")


def list_change_files(project: str, change_name: str) -> list[str]:
    _require_safe_name(change_name, "change")
    source = _resolve_change_source(project, change_name)
    if isinstance(source, _WorktreeSource):
        return _sorted_markdown_files(source.root)
    return source.files


def read_change_file(project: str, change_name: str, rel_path: str) -> str:
    _require_safe_name(change_name, "change")
    source = _resolve_change_source(project, change_name)
    if isinstance(source, _WorktreeSource):
        return _read_markdown(source.root, rel_path)

    if rel_path not in source.files:
        raise NotFound(f"找不到檔案：{rel_path}")
    content, err = read_branch_file(project, source.branch, f"openspec/changes/{change_name}/{rel_path}")
    if content is None:
        raise NotFound(f"找不到檔案：{rel_path}（git：{err}）")
    return content


def list_archive(project: str) -> list[dict]:
    root = _archive_root(project)
    if not os.path.isdir(root):
        return []
    out = []
    for name in os.listdir(root):
        if not os.path.isdir(os.path.join(root, name)):
            continue
        m = _ARCHIVE_DIR_RE.match(name)
        date, change_name = (m.group(1), m.group(2)) if m else ("", name)
        out.append({"dir": name, "date": date, "name": change_name})
    out.sort(key=lambda d: d["dir"], reverse=True)
    return out


def list_archive_files(project: str, dir_name: str) -> list[str]:
    _require_safe_name(dir_name, "封存")
    root = os.path.join(_archive_root(project), dir_name)
    return _list_markdown(root, f"找不到封存：{dir_name}")


def read_archive_file(project: str, dir_name: str, rel_path: str) -> str:
    _require_safe_name(dir_name, "封存")
    root = os.path.join(_archive_root(project), dir_name)
    return _read_markdown(root, rel_path)


def list_specs(project: str) -> list[str]:
    root = os.path.join(REPO_ROOT, project, "openspec", "specs")
    if not os.path.isdir(root):
        return []
    return sorted(
        d for d in os.listdir(root)
        if not d.startswith(".") and os.path.isdir(os.path.join(root, d))
    )


def read_spec(project: str, domain: str) -> str:
    _require_safe_name(domain, "domain")
    path = os.path.join(REPO_ROOT, project, "openspec", "specs", domain, "spec.md")
    if not os.path.isfile(path):
        raise NotFound(f"找不到 domain：{domain}")
    with open(path, encoding="utf-8") as f:
        return f.read()
