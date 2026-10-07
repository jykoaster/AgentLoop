"""Structural validators for OpenSpec delta output."""
import re
from typing import Optional


def has_added(spec_text: str) -> bool:
    return "## ADDED Requirements" in spec_text


def has_modified(spec_text: str) -> bool:
    if "## MODIFIED Requirements" not in spec_text:
        return False
    idx = spec_text.index("## MODIFIED Requirements")
    after = spec_text[idx + len("## MODIFIED Requirements"):].strip()
    return bool(re.search(r"### Requirement:", after))


def has_removed(spec_text: str) -> bool:
    if "## REMOVED Requirements" not in spec_text:
        return False
    idx = spec_text.index("## REMOVED Requirements")
    after = spec_text[idx + len("## REMOVED Requirements"):].strip()
    if not after:
        return False
    # Find content before the next h2 section (## but not ###)
    next_h2 = re.search(r"^## [^#]", after, re.MULTILINE)
    section_content = after[: next_h2.start()] if next_h2 else after
    return bool(section_content.strip())


def check_no_negative_scenarios(spec_text: str) -> tuple[bool, Optional[str]]:
    """Primary assertions must not be about absence of things.
    MUST NOT is only valid as a side-effect constraint (AND clause in a positive THEN)."""
    lines = spec_text.split("\n")
    for line in lines:
        # Negative scenario titles
        if re.match(r"\s*####\s+Scenario:", line):
            for kw in ["不顯示", "不存在", "沒有", "無法", "不出現", "移除後無"]:
                if kw in line:
                    return False, f"Negative scenario title: {line.strip()}"

        # Standalone MUST NOT in Requirement body (not inside a THEN/AND clause)
        if re.match(r"\s*The system MUST NOT", line):
            return False, f"Standalone MUST NOT requirement: {line.strip()}"

    return True, None


def check_no_implementation_details_frontend(spec_text: str) -> tuple[bool, Optional[str]]:
    """For frontend specs: detect implementation details that don't belong in spec."""
    violations = []

    if "```" in spec_text:
        violations.append("contains code block")
    if re.search(r"`\w+\.\w+`", spec_text):
        violations.append("contains property accessor notation like `obj.prop`")
    if re.search(r"===\s*(true|false|null|undefined)", spec_text):
        violations.append("contains JS conditional expression")
    for pattern, msg in [
        (r"\bDOM\b", "mentions DOM"),
        (r"\bmaxlength\b", "mentions DOM maxlength attribute"),
        (r"\bclassName\b", "mentions className"),
        (r"\bv-if\b|\bv-show\b|\b@click\b", "contains Vue template syntax"),
    ]:
        if re.search(pattern, spec_text):
            violations.append(msg)

    if violations:
        return False, "; ".join(violations)
    return True, None


def check_no_diff_language(spec_text: str) -> tuple[bool, Optional[str]]:
    """MODIFIED sections should state the new behavior, not describe what changed."""
    patterns = [
        (r"從.{1,20}改為", "diff language: 從X改為Y"),
        (r"原本是.{1,20}現在", "diff language: 原本是X現在Y"),
        (r"改動前|改動後", "diff language: 改動前/後"),
        (r"changed from\b", "diff language: changed from"),
        (r"previously\b", "diff language: previously"),
    ]
    for pattern, msg in patterns:
        if re.search(pattern, spec_text, re.IGNORECASE):
            return False, msg
    return True, None


def check_has_stepwise_scenario(spec_text: str) -> tuple[bool, Optional[str]]:
    """At least one Scenario must have GIVEN/WHEN/THEN structure."""
    has_g = "- GIVEN" in spec_text or "GIVEN " in spec_text
    has_w = "- WHEN" in spec_text or "WHEN " in spec_text
    has_t = "- THEN" in spec_text or "THEN " in spec_text
    if has_g and has_w and has_t:
        return True, None
    return False, "No GIVEN/WHEN/THEN stepwise scenario found"


def check_tasks_delete_removed_scenarios(
    tasks_text: str,
    disappeared: list[str],
) -> tuple[bool, Optional[str]]:
    """tasks.md must explicitly mention deleting tests for every Requirement or
    Scenario that disappeared (REMOVED requirement or MODIFIED with missing Scenarios).

    disappeared: list of Requirement titles and/or Scenario titles that were in
    the old spec but are absent from the new delta. Each entry is checked
    independently — tasks must mention it with delete-intent language.
    """
    missing = []
    for title in disappeared:
        delete_near_title = bool(
            re.search(
                rf"(?:移除|刪除|delete|remove).{{0,80}}{re.escape(title)}|"
                rf"{re.escape(title)}.{{0,80}}(?:移除|刪除|delete|remove)",
                tasks_text,
                re.IGNORECASE,
            )
        )
        if not delete_near_title:
            missing.append(title)
    if missing:
        return False, f"tasks.md 缺少以下消失 Requirement／Scenario 的刪除測試任務：{missing}"
    return True, None


def check_no_split_same_trigger_scenarios(
    spec_text: str,
) -> tuple[bool, Optional[str]]:
    """Two Scenarios in the same Requirement with the same first GIVEN+WHEN
    are one behavior branch and must be merged."""
    parts = re.split(r"^### Requirement:", spec_text, flags=re.MULTILINE)
    for part in parts[1:]:
        scenarios = re.split(r"^#### Scenario:", part, flags=re.MULTILINE)
        seen: dict[tuple[str, str], str] = {}
        for sc in scenarios[1:]:
            title = sc.splitlines()[0].strip() if sc.strip() else ""
            given, when = _first_given_when(sc)
            if not when:
                continue
            key = (given, when)
            if key in seen:
                return False, (
                    f"同一 Requirement 底下兩條 Scenario 觸發相同，應合併："
                    f"「{seen[key]}」與「{title}」（{when}）"
                )
            seen[key] = title
    return True, None


def _first_given_when(scenario_body: str) -> tuple[str, str]:
    given = ""
    when = ""
    for line in scenario_body.splitlines():
        stripped = line.strip()
        if not given and stripped.startswith("- GIVEN"):
            given = stripped
        elif not when and stripped.startswith("- WHEN"):
            when = stripped
            break
    return given, when


def check_has_intent(proposal_text: str) -> tuple[bool, Optional[str]]:
    """proposal.md must have a non-empty ## Intent section."""
    if "## Intent" not in proposal_text:
        return False, "proposal.md missing ## Intent section"
    idx = proposal_text.index("## Intent")
    after = proposal_text[idx + len("## Intent"):].strip()
    if not after or after.startswith("##"):
        return False, "## Intent section is empty"
    return True, None
