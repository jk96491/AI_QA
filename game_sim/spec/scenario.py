"""시나리오 = 보스 정의서에 적용하는 패치 (수치 변경)."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

from game_sim.spec.boss_spec import BossSpec


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str = ""
    boss: str = "default"
    scale: Dict[str, float] = field(default_factory=dict)  # 필드 × 배율
    set: Dict[str, Any] = field(default_factory=dict)      # 필드 = 값

    def apply(self, boss: BossSpec) -> BossSpec:
        changes: Dict[str, Any] = {}
        for key, mult in self.scale.items():
            changes[key] = getattr(boss, key) * float(mult)
        changes.update(self.set)
        if not changes:
            return boss
        return dataclasses.replace(boss, name="%s@%s" % (boss.name, self.name), **changes)

    @classmethod
    def from_dict(cls, name: str, d: Mapping[str, Any]) -> "Scenario":
        return cls(
            name=name,
            description=d.get("description", ""),
            boss=d.get("boss", "default"),
            scale=dict(d.get("scale", {})),
            set=dict(d.get("set", {})),
        )
