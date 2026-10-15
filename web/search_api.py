"""重用 `search.py` 的索引／檢索／回答函式，供 `/api/specs/search` 呼叫。

`search.py` 的 `_ask_claude()` 直接讀 `os.environ`（`ANTHROPIC_API_KEY`），
所以呼叫前以 context manager 暫時覆寫成網頁設定的有效值；網頁服務是單一行程，
暫時覆寫 `os.environ` 不是執行緒安全的操作，因此額外用一把鎖把這段序列化。
"""
import contextlib
import os
from pathlib import Path
from threading import Lock

from . import settings as web_settings
from .. import search as search_module
from ..lib import REPO_ROOT

_NO_RESULTS_ANSWER = "規格文件中沒有找到相關內容。"

_lock = Lock()


class SearchFailed(Exception):
    pass


@contextlib.contextmanager
def _env_overrides(overrides: dict[str, str]):
    original = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for k, v in original.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def search_specs(project: str, query: str) -> dict:
    project_dir = Path(REPO_ROOT) / project
    openspec_dir = project_dir / "openspec"
    if not openspec_dir.is_dir():
        return {"answer": _NO_RESULTS_ANSWER, "references": []}

    with _lock, _env_overrides(web_settings.effective_env_overrides()):
        db = search_module._db_path(project_dir)
        if search_module._is_stale(db, openspec_dir):
            docs = search_module._collect_documents(project_dir)
            if not docs:
                return {"answer": _NO_RESULTS_ANSWER, "references": []}
            search_module._build_index(db, docs)

        results = search_module._search(db, query)
        if not results:
            return {"answer": _NO_RESULTS_ANSWER, "references": []}

        try:
            answer = search_module._ask_claude(query, results, project_dir.name)
        except Exception as e:
            raise SearchFailed(str(e)) from e

    return {
        "answer": answer,
        "references": [{"path": r["path"], "doc_type": r["doc_type"]} for r in results],
    }
