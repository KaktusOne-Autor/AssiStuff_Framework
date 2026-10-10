"""Skill: unit conversion."""

from __future__ import annotations

from assistuff.primitives import units
from assistuff.skills.registry import SkillContext


def run(value: str, _ctx: SkillContext) -> str:
    number, source, target = units.parse_conversion(value)
    result, src_unit, dst_unit = units.convert(number, source, target)
    return f"{number:g} {src_unit} = {result:.6g} {dst_unit}"