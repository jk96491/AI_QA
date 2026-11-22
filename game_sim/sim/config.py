"""시뮬레이션 공통 설정."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimConfig:
    dt: float = 0.3               # 1스텝 = BT 결정 주기 300ms
    time_limit: float = 600.0     # 시간 초과(중도절단)
    max_deaths: int = 3           # 이 횟수를 넘겨 사망하면 실패 (부활 3회 허용)
    revive_delay: float = 15.0
    start_distance: float = 8.0
    revive_distance: float = 10.0
    min_distance: float = 1.0
    max_distance: float = 30.0
    stall_seconds: float = 90.0   # 이 시간 동안 보스에게 피해가 없으면 멈춘 판(stalled) = 실패로 종료
    crit_mult: float = 1.5
    gcd: float = 0.9
    record_events: bool = False
