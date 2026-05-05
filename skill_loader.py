"""從 ~/.claude/skills/ 讀取 skill 內容並注入到 prompt 中。"""
import os

SKILLS_DIR = os.path.expanduser("~/.claude/skills")

# 只注入完整內容的 skill 白名單；其餘只列名稱
# writing-plans 的存檔路徑 (docs/superpowers/plans/) 定義在 SKILL.md 內，需完整注入
_FULL_CONTENT_SKILLS: set[str] = {"writing-plans"}


def load_skill(name: str) -> str:
    """讀取單一 skill 的 SKILL.md 內容。找不到時靜默略過。"""
    path = os.path.join(SKILLS_DIR, name, "SKILL.md")
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_skill_file(name: str, filename: str) -> str:
    """讀取 skill 目錄中的任意檔案。找不到時靜默略過。"""
    path = os.path.join(SKILLS_DIR, name, filename)
    if not os.path.isfile(path):
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
