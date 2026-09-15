"""偵測工作區內各專案的 CLAUDE.md / AGENT.md，讓 Agent 依任務需求自行選擇並讀取，
而不是把單一專案的結構寫死在 prompt 裡。"""
import os

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_ROOT = os.path.dirname(_LIB_DIR)   # AgentLoop/ 本身（skill_loader 找內建 skill 用）
REPO_ROOT = os.path.dirname(PACKAGE_ROOT)  # workspace root（AgentLoop/ 的上層目錄）
_CANDIDATE_FILES = ("CLAUDE.md", "AGENT.md", "AGENTS.md")


def list_project_docs() -> list[str]:
    """回傳工作區下各專案目錄中，CLAUDE.md / AGENT.md / AGENTS.md 的相對路徑清單。"""
    docs: list[str] = []
    if not os.path.isdir(REPO_ROOT):
        return docs
    for entry in sorted(os.listdir(REPO_ROOT)):
        project_dir = os.path.join(REPO_ROOT, entry)
        if entry.startswith(".") or not os.path.isdir(project_dir):
            continue
        for filename in _CANDIDATE_FILES:
            if os.path.isfile(os.path.join(project_dir, filename)):
                docs.append(f"{entry}/{filename}")
                break
    return docs


def build_project_docs_hint() -> str:
    """組成提示區塊：列出偵測到的專案說明檔，讓 Agent 依任務內容自行判斷要讀哪一個。"""
    docs = list_project_docs()
    if not docs:
        return (
            "本工作區未偵測到任何專案的 CLAUDE.md / AGENT.md，"
            "請自行用 Read/Glob/Grep 探索程式碼以了解專案結構與慣例。"
        )
    listed = "\n".join(f"- {d}" for d in docs)
    return (
        "本工作區可能包含多個專案，偵測到以下專案說明檔：\n"
        f"{listed}\n\n"
        "請依任務內容判斷本次涉及哪個（或哪些）專案，用 Read 讀取對應的 CLAUDE.md / AGENT.md，"
        "以了解該專案的架構、指令（測試、lint、build 等）、目錄慣例與程式碼規範。"
        "若任務同時涉及多個專案（例如前後端），須分別讀取各自的說明檔。"
        "若說明檔未涵蓋的細節，比對該專案現有程式碼風格。"
    )


def build_project_doc_hint_for(project_dir: str) -> str:
    """組成提示區塊：目標專案已確定時直接指向它的說明檔，不必再掃描整個 workspace、
    也不需要 Agent 自己判斷這次任務屬於哪個專案——那是 build_project_docs_hint() 在還
    不知道 project_dir 時的做法。analyze_plan／execute／review 這三個節點呼叫這裡時，
    project_dir 都已經確定，直接指名可以省下列出其他無關專案的 token，也避免 Agent
    在多個同名系列的專案（例如同時存在好幾個 *-frontend-vue）之間選錯。

    project_dir 意外為空（例如手動塞的 state 檔缺欄位）時，退回原本的整個 workspace 掃描。
    """
    if not project_dir:
        return build_project_docs_hint()

    for filename in _CANDIDATE_FILES:
        if os.path.isfile(os.path.join(REPO_ROOT, project_dir, filename)):
            return (
                f"目標專案：{project_dir}。請用 Read 讀取 `{project_dir}/{filename}`，"
                "以了解該專案的架構、指令（測試、lint、build 等）、目錄慣例與程式碼規範。"
                "若說明檔未涵蓋的細節，比對該專案現有程式碼風格。"
            )

    return (
        f"目標專案：{project_dir}。該目錄未偵測到 CLAUDE.md / AGENT.md / AGENTS.md，"
        "請自行用 Read/Glob/Grep 探索程式碼以了解專案結構與慣例。"
    )
