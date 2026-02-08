from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class Skill:
    name: str
    endpoint: str


class SkillRegistry:
    def __init__(self, skills: list[Skill] | None = None) -> None:
        self.skills = {s.name: s for s in (skills or [])}

    @classmethod
    def from_env(cls, raw: str | None) -> "SkillRegistry":
        if not raw:
            return cls([])
        data = json.loads(raw)
        skills = [Skill(**item) for item in data]
        return cls(skills)

    async def call(self, skill_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        skill = self.skills.get(skill_name)
        if not skill:
            raise ValueError(f"Skill not found: {skill_name}")
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(skill.endpoint, json=payload)
            res.raise_for_status()
            return res.json()

