"""블랙보드: 관측값·파라미터·선택 상태를 BT 노드들이 공유하는 공간."""
from __future__ import annotations

from typing import Dict, List, Optional

from game_sim.core.types import EPS, Action, Observation
from game_sim.spec.class_spec import ClassSpec
from game_sim.spec.skill_def import SkillDef, SkillRole


class Blackboard:
    def __init__(self, spec: ClassSpec) -> None:
        self.spec = spec
        self.params: Dict[str, float] = {}
        self.obs: Optional[Observation] = None
        self.action: Optional[Action] = None
        self.current_block: str = "none"
        self.block_since: float = 0.0
        self.scores: Dict[str, float] = {}
        self._by_role: Dict[SkillRole, List[SkillDef]] = {
            role: spec.skills_by_role(role) for role in SkillRole
        }

    # ----- 파라미터 -----
    def p(self, key: str, default: Optional[float] = None) -> float:
        if key in self.params:
            return self.params[key]
        if default is None:
            raise KeyError("BT parameter %r 가 설정되지 않음" % key)
        return default

    # ----- 스킬 헬퍼 -----
    def skills(self, role: SkillRole) -> List[SkillDef]:
        return self._by_role[role]

    def available(self, skill: SkillDef) -> bool:
        """쿨타임·자원 기준 (GCD 무시)."""
        assert self.obs is not None
        return self.obs.skill_available.get(skill.name, False)

    def usable_now(self, skill: SkillDef) -> bool:
        assert self.obs is not None
        return self.obs.gcd_ready and self.available(skill)

    def in_range(self, skill: SkillDef) -> bool:
        assert self.obs is not None
        return skill.is_self_target or self.obs.distance <= skill.range + EPS

    def keeps_reserve(self, skill: SkillDef) -> bool:
        """사용 후에도 resource_reserve 비율 이상의 자원이 남는가 (버스트용 비축)."""
        assert self.obs is not None
        reserve = self.p("resource_reserve", 0.0) * self.obs.max_resource
        return self.obs.resource - skill.cost >= reserve - EPS

    def any_available(self, role: SkillRole) -> bool:
        return any(self.available(s) for s in self.skills(role))
