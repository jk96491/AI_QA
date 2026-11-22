"""보스 엔티티: 추격·평타·광역기·기믹·페이즈."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from game_sim.core.types import EPS
from game_sim.spec.boss_spec import BossSpec


@dataclass
class BossAttack:
    kind: str                 # auto / aoe / gimmick
    raw_damage: float
    ignore_mitigation: bool = False
    hp_ratio_damage: float = 0.0  # 플레이어 최대 체력 비례 피해 (기믹)


class Boss:
    def __init__(self, spec: BossSpec, rng: np.random.Generator) -> None:
        self.spec = spec
        self.rng = rng
        self.hp = spec.max_hp
        self.phase = 0
        self.auto_timer = spec.auto_interval
        self.aoe_timer = self._jittered(spec.aoe_interval, spec.aoe_jitter)
        self.gimmick_timer = self._jittered(spec.gimmick_first_at, spec.gimmick_jitter)
        self.gimmick_remaining = 0.0  # >0 이면 경고 중

    def _jittered(self, base: float, jitter: float) -> float:
        return max(1.0, base + self.rng.uniform(-jitter, jitter))

    # ----- 상태 -----
    @property
    def hp_ratio(self) -> float:
        return max(0.0, self.hp / self.spec.max_hp)

    @property
    def alive(self) -> bool:
        return self.hp > EPS

    @property
    def gimmick_warning(self) -> bool:
        return self.gimmick_remaining > EPS

    @property
    def damage_mult(self) -> float:
        return self.spec.phase_damage_mult[self.phase]

    @property
    def speed_mult(self) -> float:
        return self.spec.phase_speed_mult[self.phase]

    # ----- 피격 -----
    def take_damage(self, amount: float) -> List[float]:
        """피해 적용. 새로 넘어간 페이즈 경계(체력 비율) 목록을 반환."""
        before = self.hp_ratio
        self.hp = max(0.0, self.hp - amount)
        after = self.hp_ratio
        crossed = [t for t in self.spec.phase_thresholds if before > t >= after]
        self.phase += len(crossed)
        return crossed

    def resolve_gimmick(self) -> bool:
        if self.gimmick_warning:
            self.gimmick_remaining = 0.0
            return True
        return False

    # ----- 시간 경과 -----
    def _roll(self, base: float) -> float:
        v = self.spec.damage_variance
        return base * self.damage_mult * self.rng.uniform(1.0 - v, 1.0 + v)

    def update(self, dt: float, distance: float, target_alive: bool) -> Tuple[float, List[BossAttack]]:
        """이동·공격 처리 후 (새 거리, 공격 목록) 반환."""
        attacks: List[BossAttack] = []
        s = self.spec

        # 추격
        if distance > s.reach + EPS:
            distance = max(s.reach, distance - s.move_speed * dt)

        # 평타: 사거리 안일 때만, 밖이면 타이머 대기
        self.auto_timer -= dt * self.speed_mult
        if self.auto_timer <= EPS:
            if target_alive and distance <= s.reach + EPS:
                attacks.append(BossAttack("auto", self._roll(s.auto_damage)))
                self.auto_timer = s.auto_interval
            else:
                self.auto_timer = 0.0

        # 광역기: 거리 무관
        self.aoe_timer -= dt
        if self.aoe_timer <= EPS:
            if target_alive:
                attacks.append(BossAttack("aoe", self._roll(s.aoe_damage)))
            self.aoe_timer = self._jittered(s.aoe_interval, s.aoe_jitter)

        # 기믹: 경고 → 제한 시간 내 미대응 시 대량 피해
        if self.gimmick_warning:
            self.gimmick_remaining -= dt
            if self.gimmick_remaining <= EPS:
                self.gimmick_remaining = 0.0
                if target_alive:
                    attacks.append(
                        BossAttack("gimmick", 0.0, ignore_mitigation=True, hp_ratio_damage=s.gimmick_damage_ratio)
                    )
        else:
            self.gimmick_timer -= dt
            if self.gimmick_timer <= EPS:
                if target_alive:
                    self.gimmick_remaining = s.gimmick_window
                self.gimmick_timer = self._jittered(s.gimmick_interval, s.gimmick_jitter)

        return distance, attacks
