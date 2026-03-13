from pathlib import Path

from msagent.cli.handlers.skills import SkillsHandler
from msagent.skills.factory import DEFAULT_SKILL_CATEGORY, Skill


def test_skills_handler_hides_default_category_for_legacy_skills() -> None:
    skill = Skill(
        name="op-mfu-calculator",
        description="Legacy flat skill",
        category=DEFAULT_SKILL_CATEGORY,
        path=Path("/tmp/op-mfu-calculator/SKILL.md"),
    )

    formatted = SkillsHandler._format_skill_list([skill], 0, set(), 0, 10)
    rendered = "".join(text for _, text in formatted)

    assert "op-mfu-calculator" in rendered
    assert "default/op-mfu-calculator" not in rendered


def test_skills_handler_keeps_category_for_grouped_skills() -> None:
    skill = Skill(
        name="workspace-skill",
        description="Grouped skill",
        category="analysis",
        path=Path("/tmp/analysis/workspace-skill/SKILL.md"),
    )

    formatted = SkillsHandler._format_skill_list([skill], 0, set(), 0, 10)
    rendered = "".join(text for _, text in formatted)

    assert "analysis/workspace-skill" in rendered
