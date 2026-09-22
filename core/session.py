"""中斷中的 Claude session 在 AgentState 裡的存取。

**每個 change 同時只會有一個中斷中的 session**，所以狀態是「單一插槽」而非清單：
節點撞到用量上限就讓整個工作流停下（`review` 看到上游 `status: "error"` 直接跳過、
`route_after_review` 也在 error 時 END），不可能有第二個節點接著跑到一半又被中斷；
節點正常產出結論時則會把插槽清掉。存新的 session 一律整份取代舊的，不累積。

插槽仍然記著 owner node，因為 `--node` 可以從任一節點切入：`execute` 絕對不能去
`--resume` 一個 `analyze_plan` 留下的 session——工具權限（`plan` vs `full`）與當時
交辦的工作都不同，接錯會讓 Claude 在錯誤的脈絡下動手。

兩個欄位只透過這裡的函式讀寫，不在節點裡各自拼裝，避免 owner 與 id 走偏。
"""
from .state import AgentState


def take_session(state: AgentState, node: str) -> str:
    """取出屬於 `node` 的中斷 session id。

    插槽是空的、或裡面是別的節點留下的 session（例如 `analyze_plan` 中斷後直接
    `--node execute`）時回傳空字串，讓呼叫端走全新 session。
    """
    if state.get("session_node", "") != node:
        return ""
    return state.get("session_id", "") or ""


def store_session(node: str, session_id: str) -> dict:
    """組出要併進 state 的更新。

    `session_id` 非空 → 插槽換成這個節點的 session（中斷，待下次接回）；
    空字串 → 清空插槽（本節點已產出結論，之後接回只會帶進過期脈絡）。
    """
    if session_id:
        return {"session_node": node, "session_id": session_id}
    return {"session_node": "", "session_id": ""}
