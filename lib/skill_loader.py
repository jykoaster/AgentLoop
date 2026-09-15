"""讀取 skill 內容並注入到 prompt 中。

優先讀取專案內建的 AgentLoop/.claude/skills/，讓專案自帶所需 skill、不依賴
使用者本機設定；找不到時 fallback 到使用者本機的 ~/.claude/skills/。
"""
import os
from .project_context import PACKAGE_ROOT

PROJECT_SKILLS_DIR = os.path.join(PACKAGE_ROOT, ".claude", "skills")
USER_SKILLS_DIR = os.path.expanduser("~/.claude/skills")
SKILLS_DIRS = [PROJECT_SKILLS_DIR, USER_SKILLS_DIR]

# 只注入完整內容的 skill 白名單；其餘只列名稱
# grilling / domain-modeling：提問方式與詞彙／ADR 寫入規則必須完整注入。
# code-review：平行 sub-agent 與 smell baseline 必須完整注入（fixed point / spec 來源由 review 節點參數覆蓋）。
# tdd：紅-綠循環規則必須完整注入——Claude Code 原生的 skill 探索只認 $HOME/.claude/skills/，
# 跟 claude_runner.py 呼叫 subprocess 時的 cwd 無關，AgentLoop/.claude/skills/tdd/ 這份隨版控帶著走
# 的內建副本永遠不會被原生機制發現；只列名稱的話，能不能用完全取決於執行者自己的 ~/.claude/skills/
# 剛好有沒有同名 skill，違反了本檔案開頭「讓專案自帶所需 skill、不依賴使用者本機設定」的設計目標。
_FULL_CONTENT_SKILLS: set[str] = {
    "grilling", "domain-modeling", "code-review", "tdd",
}


def _resolve(name: str, filename: str) -> str:
    """依序在專案內建與使用者本機目錄尋找檔案路徑，找不到回傳空字串。"""
    for skills_dir in SKILLS_DIRS:
        path = os.path.join(skills_dir, name, filename)
        if os.path.isfile(path):
            return path
    return ""


def load_skill(name: str) -> str:
    """讀取單一 skill 的 SKILL.md 內容。找不到時靜默略過。"""
    path = _resolve(name, "SKILL.md")
    if not path:
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_skill_file(name: str, filename: str) -> str:
    """讀取 skill 目錄中的任意檔案。找不到時靜默略過。"""
    path = _resolve(name, filename)
    if not path:
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_skills_block(skill_names: list[str]) -> str:
    """將 skill 合併成可注入 prompt 的區塊。

    白名單內的 skill 注入完整內容；其餘只列出名稱，節省 token。
    """
    full_parts: list[str] = []
    name_only: list[str] = []

    for name in skill_names:
        if name in _FULL_CONTENT_SKILLS:
            content = load_skill(name)
            if content:
                full_parts.append(f"## Skill: {name}\n\n{content}")
        else:
            name_only.append(f"- {name}")

    sections: list[str] = []
    if name_only:
        sections.append("# 參考技術規範（Skills）\n\n" + "\n".join(name_only))
    if full_parts:
        sections.append("\n\n---\n\n".join(full_parts))

    return "\n\n".join(sections)
