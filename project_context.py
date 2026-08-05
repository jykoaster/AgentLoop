"""偵測工作區內各專案的 CLAUDE.md / AGENT.md，讓 Agent 依任務需求自行選擇並讀取，
而不是把單一專案的結構寫死在 prompt 裡。"""
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
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
