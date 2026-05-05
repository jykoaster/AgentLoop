import os
import glob as _glob
from langchain_core.tools import tool

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def _safe_path(path: str) -> str:
    """確保路徑在 repo 範圍內，防止路徑穿越。"""
    full = os.path.abspath(os.path.join(REPO_ROOT, path))
    if not full.startswith(REPO_ROOT):
        raise ValueError(f"禁止存取 repo 範圍外的路徑: {path}")
    return full


@tool
def read_file(path: str) -> str:
    """讀取 repo 內的檔案內容。path 為相對於 repo root 的路徑。"""
    full = _safe_path(path)
    if not os.path.isfile(full):
        return f"[錯誤] 檔案不存在: {path}"
    with open(full, "r", encoding="utf-8") as f:
        return f.read()


@tool
def write_file(path: str, content: str) -> str:
    """寫入（或覆蓋）repo 內的檔案。path 為相對於 repo root 的路徑。"""
    full = _safe_path(path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return f"[完成] 已寫入: {path}"


@tool
def list_directory(path: str = "") -> str:
    """列出 repo 內某目錄的內容。path 為相對路徑，預設為 repo root。"""
    full = _safe_path(path) if path else REPO_ROOT
    if not os.path.isdir(full):
        return f"[錯誤] 目錄不存在: {path}"
    entries = os.listdir(full)
    result = []
    for e in sorted(entries):
        kind = "📁" if os.path.isdir(os.path.join(full, e)) else "📄"
        result.append(f"{kind} {e}")
    return "\n".join(result)


@tool
def search_files(pattern: str, directory: str = "") -> str:
    """在 repo 內搜尋符合 glob pattern 的檔案。

    例：pattern="**/*.py", directory="tabletop-backend"
    """
    base = _safe_path(directory) if directory else REPO_ROOT
    matches = _glob.glob(os.path.join(base, pattern), recursive=True)
    rel = [os.path.relpath(m, REPO_ROOT) for m in matches]
    return "\n".join(rel) if rel else "[無符合結果]"
