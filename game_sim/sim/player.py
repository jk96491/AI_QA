"""플레이어 엔티티."""
from __future__ import annotations

from typing import Dict, Optional

from game_sim.core.types import EPS
from game_sim.spec.class_spec import ClassSpec
from game_sim.spec.skill_def import SkillDef


class Player:
    def __init__(self, spec: ClassSpec, gcd: float) -> None:
        s = spec.stats
        self.spec = spec
        self.gcd_duration = gcd
        self.max_hp = s.max_hp
        self.hp = s.max_hp
        self.max_resource = s.max_resource
        self.resource = s.start_resource
        self.cooldowns: Dict[str, float] = {sk.name: 0.0 for sk in spec.skills}
        self.gcd = 0.0
        self.potions = s.potions
        self.potion_cd = 0.0
        self.shield = 0.0
        self.shield_time = 0.0
        self.evade_time = 0.0
        self.casting: Optional[SkillDef] = None
        self.cast_remaining = 0.0
        self.dead = False
        self.revive_timer = 0.0
        self.since_hit = 0.0

    # ----- 상태 -----
    @property
    def hp_ratio(self) -> float:
        return max(0.0, self.hp / self.max_hp)

    @property
    def resource_ratio(self) -> float:
        return 0.0 if self.max_resource <= 0 else self.resource / self.max_resource

    @property
    def gcd_ready(self) -> bool:
        return self.gcd <= EPS and self.casting is None

    def available(self, skill: SkillDef) -> bool:
        """쿨·자원 기준 (GCD 무시)."""
        return self.cooldowns[skill.name] <= EPS and self.resource + EPS >= skill.cost

    def can_use(self, skill: SkillDef) -> bool:
        return not self.dead and self.gcd_ready and self.available(skill)

    @property
    def potion_ready(self) -> bool:
        return self.potions > 0 and self.potion_cd <= EPS

    # ----- 시간 경과 -----
    def tick(self, dt: float) -> None:
        for k in self.cooldowns:
            if self.cooldowns[k] > 0:
                self.cooldowns[k] = max(0.0, self.cooldowns[k] - dt)
        self.gcd = max(0.0, self.gcd - dt)
        self.potion_cd = max(0.0, self.potion_cd - dt)
        if self.shield_time > 0:
            self.shield_time -= dt
            if self.shield_time <= EPS:
                self.shield = 0.0
                self.shield_time = 0.0
        self.evade_time = max(0.0, self.evade_time - dt)
        if not self.dead:
            s = self.spec.stats
            self.resource = min(self.max_resource, self.resource + s.resource_regen * dt)
            self.since_hit += dt
            if self.since_hit >= s.regen_delay:
                self.hp = min(self.max_hp, self.hp + self.max_hp * s.hp_regen_ratio * dt)

    # ----- 행동 -----
    def start_skill(self, skill: SkillDef) -> None:
        self.resource -= skill.cost
        self.cooldowns[skill.name] = skill.cooldown
        self.gcd = max(self.gcd_duration, skill.cast_time)
        if skill.shield > 0:
            self.shield = skill.shield
            self.shield_time = skill.effect_duration
        if skill.evade > 0:
            self.evade_time = skill.evade
        if skill.cast_time > 0:
            self.casting = skill
            self.cast_remaining = skill.cast_time

    def gain_resource(self, amount: float) -> None:
        self.resource = min(self.max_resource, self.resource + amount)

    def drink_potion(self) -> float:
        self.potions -= 1
        self.potion_cd = self.spec.stats.potion_cooldown
        before = self.hp
        self.hp = min(self.max_hp, self.hp + self.max_hp * self.spec.stats.potion_heal_ratio)
        return self.hp - before

    def receive_damage(self, raw: float, ignore_mitigation: bool = False) -> float:
        if self.dead or self.evade_time > EPS:
            return 0.0
        dmg = raw
        if not ignore_mitigation:
            dmg *= (1.0 - self.spec.stats.armor) * (1.0 - self.shield)
        self.hp -= dmg
        self.since_hit = 0.0
        return dmg

    def interrupt(self) -> None:
        self.casting = None
        self.cast_remaining = 0.0

    def die(self, revive_delay: float) -> None:
        self.dead = True
        self.hp = 0.0
        self.revive_timer = revive_delay
        self.interrupt()
        self.shield = self.shield_time = self.evade_time = 0.0

    def revive(self) -> None:
        self.dead = False
        self.hp = self.max_hp
        self.gcd = 0.0
        self.since_hit = 0.0
