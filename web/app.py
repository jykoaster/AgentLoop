"""網頁控制台的 HTTP API（FastAPI），前綴 `/api`；同時以 `StaticFiles` 提供前端靜態檔
（`WEB_DIST_DIR` 未設定或不存在時只提供 API，方便本機開發時前端另外用 Vite dev server）。
"""
import os

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import repo_view, search_api
from . import settings as web_settings
from .runner import QuestionGone, RequiredAnswerMissing, RERUNNABLE_STAGES, RunConflict, get_manager
from ..lib import REPO_ROOT

router = APIRouter(prefix="/api")


class NewTaskBody(BaseModel):
    task: str


class RerunBody(BaseModel):
    stage: str


class AnswerBody(BaseModel):
    question_id: str
    answer: str = ""


class SearchBody(BaseModel):
    query: str


class SettingsBody(BaseModel):
    target_project: str | None = None
    oauth_token: str | None = None
    api_key: str | None = None


def _project() -> str:
    return web_settings.effective_value("TARGET_PROJECT")


def _require_project() -> str:
    project = _project()
    if not project:
        raise HTTPException(404, "尚未設定目標專案")
    return project


# ── 執行中任務 ───────────────────────────────────────────────────────────────

@router.get("/changes")
def get_changes():
    project = _project()
    return repo_view.list_active_changes(project) if project else []


@router.get("/changes/{name}/stages/{stage}")
def get_stage(name: str, stage: str):
    project = _require_project()
    try:
        return repo_view.get_stage_detail(project, name, stage)
    except repo_view.NotFound as e:
        raise HTTPException(404, str(e)) from e


@router.get("/changes/{name}/files")
def get_change_files(name: str):
    project = _require_project()
    try:
        return repo_view.list_change_files(project, name)
    except repo_view.NotFound as e:
        raise HTTPException(404, str(e)) from e


@router.get("/changes/{name}/files/{path:path}")
def get_change_file(name: str, path: str):
    project = _require_project()
    try:
        content = repo_view.read_change_file(project, name, path)
    except repo_view.NotFound as e:
        raise HTTPException(404, str(e)) from e
    return {"path": path, "content": content}


# ── 執行管理 ─────────────────────────────────────────────────────────────────

@router.get("/run")
def get_run():
    return get_manager().status()


@router.post("/runs", status_code=201)
def post_run(body: NewTaskBody):
    task = body.task.strip()
    if not task:
        raise HTTPException(422, "任務描述不可為空白")
    try:
        return get_manager().start_new_task(task)
    except RunConflict as e:
        raise HTTPException(409, f"目前已有 {e.label} 執行中") from e


@router.post("/changes/{name}/rerun")
def post_rerun(name: str, body: RerunBody):
    if body.stage not in RERUNNABLE_STAGES:
        raise HTTPException(422, f"不可重跑的階段：{body.stage}")
    try:
        return get_manager().start_rerun(name, body.stage)
    except RunConflict as e:
        raise HTTPException(409, f"目前已有 {e.label} 執行中") from e


@router.post("/run/answer")
def post_answer(body: AnswerBody):
    try:
        get_manager().answer(body.question_id, body.answer)
    except QuestionGone as e:
        raise HTTPException(410, "此提問已結束，請重新整理") from e
    except RequiredAnswerMissing as e:
        raise HTTPException(422, "此欄位為必填") from e
    return {"ok": True}


@router.post("/run/abort")
def post_abort():
    get_manager().abort()
    return {"ok": True}


# ── 已封存任務 ───────────────────────────────────────────────────────────────

@router.get("/archive")
def get_archive():
    project = _project()
    return repo_view.list_archive(project) if project else []


@router.get("/archive/{dir_name}/files")
def get_archive_files(dir_name: str):
    project = _require_project()
    try:
        return repo_view.list_archive_files(project, dir_name)
    except repo_view.NotFound as e:
        raise HTTPException(404, str(e)) from e


@router.get("/archive/{dir_name}/files/{path:path}")
def get_archive_file(dir_name: str, path: str):
    project = _require_project()
    try:
        content = repo_view.read_archive_file(project, dir_name, path)
    except repo_view.NotFound as e:
        raise HTTPException(404, str(e)) from e
    return {"path": path, "content": content}


# ── 既有 Spec ────────────────────────────────────────────────────────────────

@router.get("/specs")
def get_specs():
    project = _project()
    return repo_view.list_specs(project) if project else []


@router.get("/specs/{domain}")
def get_spec(domain: str):
    project = _require_project()
    try:
        content = repo_view.read_spec(project, domain)
    except repo_view.NotFound as e:
        raise HTTPException(404, str(e)) from e
    return {"domain": domain, "content": content}


@router.post("/specs/search")
def post_search(body: SearchBody):
    project = _require_project()
    try:
        return search_api.search_specs(project, body.query)
    except search_api.SearchFailed as e:
        raise HTTPException(502, f"搜尋失敗：{e}") from e


# ── 設定 ─────────────────────────────────────────────────────────────────────

@router.get("/settings")
def get_settings():
    view = web_settings.get_settings_view(REPO_ROOT)
    view["run_active"] = get_manager().is_active()
    return view


@router.put("/settings")
def put_settings(body: SettingsBody):
    fields = body.model_dump(exclude_unset=True)
    if "target_project" in fields and get_manager().is_active():
        raise HTTPException(409, "執行進行中，無法變更目標專案")
    try:
        view = web_settings.update_settings(fields, REPO_ROOT)
    except web_settings.InvalidTargetProject as e:
        raise HTTPException(400, str(e)) from e
    view["run_active"] = get_manager().is_active()
    return view


@router.get("/fs")
def get_fs(path: str = ""):
    try:
        return web_settings.list_subfolders(REPO_ROOT, path)
    except web_settings.InvalidTargetProject as e:
        raise HTTPException(400, str(e)) from e


app = FastAPI()
app.include_router(router)

_dist_dir = os.environ.get("WEB_DIST_DIR", "")
if _dist_dir and os.path.isdir(_dist_dir):
    app.mount("/", StaticFiles(directory=_dist_dir, html=True), name="frontend")
