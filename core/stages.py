"""各工作階段（analyze_plan／human_confirm／execute／review／archive）的狀態追蹤。

`AgentState["stages"]` 只有四種值：`pending`／`running`／`done`／`error`。`start()`／
`finish()` 由 `workflow.py` 的 `_tracked()` 包裝函式、以及 `main.py` 直呼 node 的路徑
（`run_node()`）呼叫；兩者都不碰節點回傳的其他欄位。

`current_stage()` 給 `claude_runner.py` 的用量上限暫停提問用，標記提問屬於哪個階段；
由 `start()` 在每個階段開始時更新，模組層單一變數即可——同一時間只會有一個階段在跑。
"""
from typing import Callable

STAGES = ("analyze_plan", "human_confirm", "execute", "review", "archive")

_current_stage: str = ""
_listener: Callable[[dict], None] | None = None


def set_listener(cb: Callable[[dict], None] | None) -> None:
    global _listener
    _listener = cb


def current_stage() -> str:
    return _current_stage


def start(state: dict, stage: str) -> dict:
    """該階段開始：記為 running，其後各階段重設為 pending、清掉該階段的 note。

    回傳要併入 state 的更新；同時（若有註冊 listener）立即把合併後的狀態回報出去，
    讓 main.py 在節點真正開始執行前就能把「執行中」寫進 state.json——節點本身可能跑
    好幾分鐘，不能等它回傳才讓使用者看到階段已經開始。
    """
    global _current_stage
    _current_stage = stage

    idx = STAGES.index(stage)
    stages_map = dict(state.get("stages") or {})
    notes_map = dict(state.get("stage_notes") or {})

    stages_map[stage] = "running"
    for later in STAGES[idx + 1:]:
        stages_map[later] = "pending"
    notes_map.pop(stage, None)

    update = {"stages": stages_map, "stage_notes": notes_map}

    print(f"@@AGENTLOOP_STAGE {stage}@@", flush=True)

    if _listener:
        merged = dict(state)
        merged.update(update)
        _listener(merged)

    return update


def finish(state: dict, stage: str, status: str | None, note: str | None = None) -> dict:
    """該階段結束：結果為 error 就記為 error，否則記為 done。

    `note` 有值時一併寫入 `stage_notes[stage]`、回傳也含 `stage_notes`；
    不傳 `note`（例如正常結束）時只回傳 `stages`，呼叫端行為不變。
    """
    stages_map = dict(state.get("stages") or {})
    stages_map[stage] = "error" if status == "error" else "done"
    update = {"stages": stages_map}
    if note is not None:
        notes_map = dict(state.get("stage_notes") or {})
        notes_map[stage] = note
        update["stage_notes"] = notes_map
    return update
