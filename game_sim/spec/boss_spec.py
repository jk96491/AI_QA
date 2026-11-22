"""보스 정의서."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple


@dataclass(frozen=True)
class BossSpec:
    name: str
    max_hp: float
    reach: float                 # 근접 공격 사거리(m)
    move_speed: float            # 추격 속도(m/s)
    auto_damage: float
    auto_interval: float
    aoe_damage: float            # 거리 무관 광역기
    aoe_interval: float
    aoe_jitter: float
    gimmick_first_at: float
    gimmick_interval: float
    gimmick_jitter: float
    gimmick_window: float        # 경고 후 대응 제한 시간(초)
    gimmick_damage_ratio: float  # 미대응 시 플레이어 최대 체력 대비 피해
    damage_variance: float       # 피해 ±비율
    phase_thresholds: Tuple[float, ...] = (0.75, 0.5, 0.25)
    phase_damage_mult: Tuple[float, ...] = (1.0, 1.1, 1.25, 1.4)
    phase_speed_mult: Tuple[float, ...] = (1.0, 1.05, 1.1, 1.2)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "BossSpec":
        kw = dict(d)
        for key in ("phase_thresholds", "phase_damage_mult", "phase_speed_mult"):
            if key in kw:
                kw[key] = tuple(float(v) for v in kw[key])
        return cls(**kw)
