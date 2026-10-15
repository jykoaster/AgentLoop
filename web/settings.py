"""網頁設定：`.web/settings.json` 讀寫、與 `.env`（`os.environ`）合併、secret 遮罩，
以及資料夾選擇器共用的「工作區根目錄邊界」檢查。

設定檔有值者優先，網頁沒設定的欄位沿用環境變數（`.env` 已由 docker-compose 的
`env_file` 注入到 `os.environ`）。`HOST_WORKSPACE_ROOT` 不在這裡管理——它必須在
容器啟動前就已知，留在 `.env`。
"""
import json
import os

from ..lib.project_context import PACKAGE_ROOT

_KEYS = ("TARGET_PROJECT", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")
_SECRET_FIELD_TO_KEY = {"oauth_token": "CLAUDE_CODE_OAUTH_TOKEN", "api_key": "ANTHROPIC_API_KEY"}

OUTSIDE_WORKSPACE_ERROR = "只能選擇工作區根目錄底下的資料夾"


class InvalidTargetProject(Exception):
    """目標專案（或資料夾選擇器選到的路徑）超出工作區根目錄。"""


def web_state_dir() -> str:
    return os.environ.get("AGENTLOOP_WEB_STATE_DIR", os.path.join(PACKAGE_ROOT, ".web"))


def _settings_path() -> str:
    return os.path.join(web_state_dir(), "settings.json")


def _read_raw() -> dict:
    path = _settings_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k in _KEYS and isinstance(v, str)}


def _write_raw(data: dict) -> None:
    state_dir = web_state_dir()
    os.makedirs(state_dir, exist_ok=True)
    path = _settings_path()
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def effective_value(key: str) -> str:
    """設定檔有值者優先，否則沿用環境變數。"""
    value = _read_raw().get(key, "")
    if value:
        return value
    return os.environ.get(key, "")


def effective_env_overrides() -> dict[str, str]:
    """啟動子行程／呼叫 search 前要覆蓋進 env 的鍵值（只含有效值非空者）。"""
    return {k: v for k in _KEYS if (v := effective_value(k))}


def _last4(value: str) -> str:
    return value[-4:] if len(value) >= 4 else value


def resolve_within_root(workspace_root: str, rel_path: str) -> str:
    """解析 `rel_path`（相對 workspace_root）的絕對路徑；超出 workspace_root 範圍就拋例外。"""
    root = os.path.realpath(workspace_root)
    candidate = os.path.realpath(os.path.join(root, rel_path or ""))
    if candidate != root and not candidate.startswith(root + os.sep):
        raise InvalidTargetProject(OUTSIDE_WORKSPACE_ERROR)
    return candidate


def list_subfolders(workspace_root: str, rel_path: str) -> list[str]:
    """列出 `rel_path` 底下的子資料夾（不含以 `.` 開頭的隱藏資料夾），依名稱排序。"""
    abs_path = resolve_within_root(workspace_root, rel_path)
    if not os.path.isdir(abs_path):
        return []
    return sorted(
        d for d in os.listdir(abs_path)
        if not d.startswith(".") and os.path.isdir(os.path.join(abs_path, d))
    )


def get_settings_view(workspace_root: str) -> dict:
    oauth = effective_value("CLAUDE_CODE_OAUTH_TOKEN")
    api_key = effective_value("ANTHROPIC_API_KEY")
    return {
        "target_project": effective_value("TARGET_PROJECT"),
        "oauth_token": {"set": bool(oauth), "last4": _last4(oauth)},
        "api_key": {"set": bool(api_key), "last4": _last4(api_key)},
        "workspace_root": workspace_root,
    }


def update_settings(fields: dict, workspace_root: str) -> dict:
    """套用部分欄位更新：
    - `target_project`：提供即覆蓋（空字串清空，需在 workspace_root 底下，否則拋
      `InvalidTargetProject`）
    - `oauth_token`／`api_key`：空字串＝不變更（代表使用者留空儲存，保留原值）
    是否允許改 `target_project`（執行中禁止）由呼叫端（web/app.py）用 runner 狀態檢查，
    這裡只管資料本身的驗證與落檔。
    """
    raw = _read_raw()

    if "target_project" in fields and fields["target_project"] is not None:
        tp = fields["target_project"].strip()
        if tp:
            resolve_within_root(workspace_root, tp)
        raw["TARGET_PROJECT"] = tp

    for field_name, key in _SECRET_FIELD_TO_KEY.items():
        value = fields.get(field_name)
        if value:
            raw[key] = value

    _write_raw(raw)
    return get_settings_view(workspace_root)
