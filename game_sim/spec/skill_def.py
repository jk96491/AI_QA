"""스킬 정의 (정의서 데이터)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class SkillRole(Enum):
    BASIC = "basic"          # 기본 공격 (쿨 없음)
    DPS = "dps"              # 딜 유지 블록이 쓰는 스킬
    BURST = "burst"          # 버스트 콤보 블록이 쓰는 스킬
    DEFENSE = "defense"      # 생존 모드 블록이 쓰는 스킬
    GAP_CLOSE = "gap_close"  # 접근기


@dataclass(frozen=True)
class SkillDef:
    name: str
    role: SkillRole
    damage: float = 0.0
    cooldown: float = 0.0
    cost: float = 0.0
    cast_time: float = 0.0
    range: float = 3.0          # 0 이면 자기 대상 (사거리 검사 없음)
    resource_gain: float = 0.0  # 적중 시 자원 획득 (전사 분노 등)
    shield: float = 0.0         # 받는 피해 감소율
    evade: float = 0.0          # 피해 무효 시간(초)
    effect_duration: float = 0.0
    retreat: float = 0.0        # 뒤로 이동 거리(m)
    gap_close: bool = False     # 보스 앞으로 순간 이동

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "SkillDef":
        kw = dict(d)
        kw["role"] = SkillRole(kw["role"])
        return cls(**kw)

    @property
    def is_self_target(self) -> bool:
        return self.range <= 0
