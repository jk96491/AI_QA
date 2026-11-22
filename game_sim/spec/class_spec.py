"""직업 정의서."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Tuple

from game_sim.spec.param import ParamDef
from game_sim.spec.skill_def import SkillDef, SkillRole


class ParamError(ValueError):
    """프로토콜 error 응답으로 변환되는 파라미터 오류."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PlayerStats:
    max_hp: float
    armor: float
    max_resource: float
    start_resource: float
    resource_regen: float
    move_speed: float
    potions: int
    potion_heal_ratio: float
    potion_cooldown: float
    crit_chance: float = 0.1
    # 마지막 피격 후 regen_delay 초가 지나면 초당 최대 체력의 hp_regen_ratio 만큼 회복 (후퇴·회복)
    hp_regen_ratio: float = 0.02
    regen_delay: float = 4.0

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "PlayerStats":
        return cls(**d)


@dataclass(frozen=True)
class ClassSpec:
    name: str
    display_name: str
    ranged: bool
    stats: PlayerStats
    skills: Tuple[SkillDef, ...]
    params: Dict[str, ParamDef] = field(default_factory=dict)
    spec_version: str = "0.1"

    # ----- 스킬 조회 -----
    def skill(self, name: str) -> SkillDef:
        for s in self.skills:
            if s.name == name:
                return s
        raise KeyError("unknown skill %r for class %r" % (name, self.name))

    def skills_by_role(self, role: SkillRole) -> List[SkillDef]:
        """역할별 스킬을 피해량 내림차순으로 반환."""
        return sorted((s for s in self.skills if s.role == role), key=lambda s: -s.damage)

    @property
    def basic_skill(self) -> SkillDef:
        return self.skills_by_role(SkillRole.BASIC)[0]

    # ----- 파라미터 -----
    def default_params(self) -> Dict[str, float]:
        """정의서 default = 개발팀이 손으로 튜닝한 값 (손 튜닝 기준선)."""
        return {k: p.default for k, p in self.params.items()}

    def resolve_params(self, base: Mapping[str, float], updates: Mapping[str, float]) -> Dict[str, float]:
        """base 위에 updates 를 덮어쓴 파라미터. 정의서에 없는 이름·범위 밖 값은 ParamError."""
        out = dict(base)
        for name, value in updates.items():
            if name not in self.params:
                raise ParamError("unknown_param", "class %r 에 파라미터 %r 없음" % (self.name, name))
            try:
                v = float(value)
            except (TypeError, ValueError):
                raise ParamError("bad_request", "파라미터 %r 값이 숫자가 아님: %r" % (name, value))
            if not self.params[name].contains(v):
                p = self.params[name]
                raise ParamError("param_out_of_range", "%s=%g 가 범위 [%g, %g] 밖" % (name, v, p.low, p.high))
            out[name] = v
        return out

    def to_wire(self) -> Dict[str, Any]:
        """describe 응답용 (스킬·스탯 수치는 공개하지 않는다: 학습 쪽은 파라미터만 안다)."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "ranged": self.ranged,
            "spec_version": self.spec_version,
            "params": [p.to_wire() for p in self.params.values()],
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ClassSpec":
        return cls(
            name=d["class"],
            display_name=d.get("display_name", d["class"]),
            ranged=bool(d.get("ranged", False)),
            stats=PlayerStats.from_dict(d["stats"]),
            skills=tuple(SkillDef.from_dict(s) for s in d["skills"]),
            params={k: ParamDef.from_dict(k, v) for k, v in d["params"].items()},
            spec_version=str(d.get("spec_version", "0.1")),
        )
