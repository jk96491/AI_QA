"""틱 기반 전투 시뮬레이터 (헤드리스, 시드 결정론).

학습 쪽과의 접점은 두 가지뿐이다 (docs/PROTOCOL.md 의 run_episode / trigger 에 대응).
- params      : 판 시작 시 BT 파라미터 (정의서 이름 → 값)
- on_trigger  : 결정 트리거마다 호출. (index, state, totals) → 갱신할 파라미터 (부분 덮어쓰기)
                totals 는 판 시작부터의 누적값 (학습 쪽이 트리거 사이 구간 보상을 계산하는 데 사용)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, List, Mapping, Optional, Sequence

import numpy as np

from game_sim.bt.agent import BTAgent
from game_sim.core.event_log import EventLog
from game_sim.core.types import EPS, TRIGGER_STATE_FEATURES, Action, ActionKind, EpisodeResult, Observation
from game_sim.sim.boss import Boss
from game_sim.sim.config import SimConfig
from game_sim.sim.player import Player
from game_sim.spec.boss_spec import BossSpec
from game_sim.spec.class_spec import ClassSpec
from game_sim.spec.skill_def import SkillDef, SkillRole

#: (트리거 번호, 정규화 상태, 누적값) → 갱신 파라미터
TriggerHandler = Callable[[int, Dict[str, float], Dict[str, float]], Mapping[str, float]]


class CombatSim:
    """전투 1판을 실행한다.

    같은 (class_spec, boss_spec, params, triggers, seed, config, 트리거 응답) 이면 항상 같은 결과.

    트리거를 요청하면(triggers 비어 있지 않음) 판 시작 시 index 0 트리거를 먼저 보내고,
    이후 보스 체력이 각 경계 아래로 내려갈 때마다 index 1, 2, ... 를 보낸다.
    """

    def __init__(
        self,
        class_spec: ClassSpec,
        boss_spec: BossSpec,
        params: Mapping[str, float],
        seed: int,
        config: Optional[SimConfig] = None,
        triggers: Sequence[float] = (),
        on_trigger: Optional[TriggerHandler] = None,
    ) -> None:
        self.cfg = config or SimConfig()
        self.class_spec = class_spec
        self.boss_spec = boss_spec
        # 정의서 default 위에 요청 파라미터를 덮어씀 (이름·범위 검사)
        self.params = class_spec.resolve_params(class_spec.default_params(), params)
        self.on_trigger = on_trigger
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.log = EventLog(self.cfg.record_events)

        self.player = Player(class_spec, self.cfg.gcd)
        self.boss = Boss(boss_spec, self.rng)
        self.agent = BTAgent(class_spec)
        self.distance = self.cfg.start_distance
        self.t = 0.0

        # 집계
        self.deaths = 0
        self.consumables = 0
        self.damage_dealt = 0.0
        self.damage_taken = 0.0
        self.gimmick_success = 0
        self.gimmick_fail = 0
        self.invalid_actions = 0
        self.block_time: Dict[str, float] = defaultdict(float)
        self.phase_times: List[float] = []
        self.last_damage_t = 0.0
        self.pending_triggers: List[float] = sorted((float(t) for t in triggers), reverse=True)
        self.use_triggers = bool(self.pending_triggers) and on_trigger is not None
        self.triggers_fired = 0

    # ------------------------------------------------------------------ 관측
    def _observe(self) -> Observation:
        p = self.player
        return Observation(
            time=self.t,
            hp_ratio=p.hp_ratio,
            resource=p.resource,
            resource_ratio=p.resource_ratio,
            max_resource=p.max_resource,
            distance=self.distance,
            boss_reach=self.boss_spec.reach,
            boss_hp_ratio=self.boss.hp_ratio,
            gcd_ready=p.gcd_ready,
            skill_available={s.name: p.available(s) for s in self.class_spec.skills},
            potions_left=p.potions,
            potion_ready=p.potion_ready,
            gimmick_warning=self.boss.gimmick_warning,
        )

    def trigger_state(self) -> Dict[str, float]:
        """결정 트리거 상태 (TRIGGER_STATE_FEATURES 순서, 0~1 정규화)."""
        p = self.player
        bursts = self.class_spec.skills_by_role(SkillRole.BURST)
        state = {
            "hp_ratio": p.hp_ratio,
            "boss_hp_ratio": self.boss.hp_ratio,
            "potions_ratio": p.potions / max(1, self.class_spec.stats.potions),
            "resource_ratio": p.resource_ratio,
            "burst_ready": float(any(p.available(s) for s in bursts)),
            "time_ratio": min(1.0, self.t / self.cfg.time_limit),
            "deaths_ratio": min(1.0, self.deaths / max(1, self.cfg.max_deaths)),
        }
        return {k: round(float(state[k]), 6) for k in TRIGGER_STATE_FEATURES}

    def trigger_totals(self) -> Dict[str, float]:
        """판 시작부터의 누적값 (TRIGGER_TOTALS_FIELDS). episode_result 의 같은 이름 필드와 단위가 같다."""
        return {
            "elapsed": round(self.t, 3),
            "deaths": self.deaths,
            "consumables_used": self.consumables,
            "boss_hp_remaining": round(self.boss.hp_ratio, 6),
        }

    def _fire_trigger(self) -> None:
        assert self.on_trigger is not None
        updates = self.on_trigger(self.triggers_fired, self.trigger_state(), self.trigger_totals())
        self.params = self.class_spec.resolve_params(self.params, updates or {})
        self.agent.set_params(self.params)
        self.log.record(self.t, "trigger", index=self.triggers_fired)
        self.triggers_fired += 1

    # ------------------------------------------------------------------ 행동 적용
    def _apply(self, action: Action) -> None:
        p = self.player
        kind = action.kind
        if kind == ActionKind.SKILL:
            skill = self.class_spec.skill(action.skill or "")
            in_range = skill.is_self_target or self.distance <= skill.range + EPS
            if not p.can_use(skill) or not in_range:
                self.invalid_actions += 1
                return
            p.start_skill(skill)
            if skill.gap_close:
                self.distance = max(self.cfg.min_distance, self.boss_spec.reach - 1.5)
            if skill.retreat > 0:
                self.distance = min(self.cfg.max_distance, self.distance + skill.retreat)
            self.log.record(self.t, "skill", name=skill.name, block=self.agent.current_block)
            if skill.cast_time <= 0:
                self._resolve(skill)
        elif kind == ActionKind.MOVE_TOWARD:
            step = p.spec.stats.move_speed * self.cfg.dt
            self.distance = max(self.cfg.min_distance, self.distance - step)
        elif kind == ActionKind.MOVE_AWAY:
            step = p.spec.stats.move_speed * self.cfg.dt
            self.distance = min(self.cfg.max_distance, self.distance + step)
        elif kind == ActionKind.POTION:
            if not p.potion_ready:
                self.invalid_actions += 1
                return
            healed = p.drink_potion()
            self.consumables += 1
            self.log.record(self.t, "potion", healed=round(healed, 1))
        elif kind == ActionKind.RESPOND_GIMMICK:
            if self.boss.resolve_gimmick():
                self.gimmick_success += 1
                p.gcd = max(p.gcd, self.cfg.gcd)
                self.log.record(self.t, "gimmick_ok")

    def _resolve(self, skill: SkillDef) -> None:
        """시전 완료 시 피해 적용."""
        if skill.damage > 0 and (skill.is_self_target or self.distance <= skill.range + 0.5):
            dmg = skill.damage
            if self.rng.random() < self.class_spec.stats.crit_chance:
                dmg *= self.cfg.crit_mult
            self.damage_dealt += dmg
            self.last_damage_t = self.t
            crossed = self.boss.take_damage(dmg)
            if skill.resource_gain:
                self.player.gain_resource(skill.resource_gain)
            if crossed:
                self._on_phase_cross(crossed)

    def _on_phase_cross(self, crossed: List[float]) -> None:
        for thr in crossed:
            self.phase_times.append(self.t + self.cfg.dt)
            self.log.record(self.t, "phase", threshold=thr)
        # 결정 트리거: 넘어간 경계마다 한 번씩 (같은 스텝 다중 통과 시 마지막 상태로 한 번)
        fired = False
        while self.pending_triggers and self.boss.hp_ratio <= self.pending_triggers[0] + EPS:
            self.pending_triggers.pop(0)
            fired = True
        if fired and self.boss.alive and self.use_triggers:
            self._fire_trigger()

    # ------------------------------------------------------------------ 메인 루프
    def run(self) -> EpisodeResult:
        cfg = self.cfg
        p = self.player
        self.agent.set_params(self.params)
        if self.use_triggers:
            self._fire_trigger()  # index 0: 판 시작 결정
        cleared = False
        stall_reason: Optional[str] = None
        clear_time: Optional[float] = None

        while self.t < cfg.time_limit - EPS:
            p.tick(cfg.dt)

            # --- 플레이어 ---
            if p.dead:
                self.block_time["dead"] += cfg.dt
                p.revive_timer -= cfg.dt
                if p.revive_timer <= EPS:
                    p.revive()
                    self.distance = cfg.revive_distance
                    self.log.record(self.t, "revive")
            else:
                if p.casting is not None:
                    p.cast_remaining -= cfg.dt
                    if p.cast_remaining <= EPS:
                        skill = p.casting
                        p.interrupt()
                        self._resolve(skill)
                else:
                    self._apply(self.agent.decide(self._observe()))
                self.block_time[self.agent.current_block] += cfg.dt

            if not self.boss.alive:
                cleared = True
                clear_time = self.t + cfg.dt
                self.t += cfg.dt
                break

            # --- 보스 ---
            self.distance, attacks = self.boss.update(cfg.dt, self.distance, not p.dead)
            for atk in attacks:
                raw = atk.raw_damage + atk.hp_ratio_damage * p.max_hp
                taken = p.receive_damage(raw, atk.ignore_mitigation)
                self.damage_taken += taken
                if atk.kind == "gimmick":
                    self.gimmick_fail += 1
                self.log.record(self.t, "hit", kind=atk.kind, dmg=round(taken, 1))

            # --- 사망 ---
            if not p.dead and p.hp <= EPS:
                self.deaths += 1
                self.log.record(self.t, "death", count=self.deaths)
                if self.deaths > cfg.max_deaths:
                    self.t += cfg.dt
                    break
                p.die(cfg.revive_delay)

            self.t += cfg.dt

            # --- 무효 판 감지 ---
            # --- 멈춘 판 감지: BT 가 진전 없이 맴돔 → 실패 (환경 오류가 아니므로 invalid 아님) ---
            if not p.dead and self.t - self.last_damage_t > cfg.stall_seconds:
                stall_reason = "%.0fs 동안 보스 피해 없음" % cfg.stall_seconds
                break

        return self._result(cleared, clear_time, stall_reason)

    def _result(self, cleared: bool, clear_time: Optional[float], stall_reason: Optional[str]) -> EpisodeResult:
        marks = [0.0] + self.phase_times + ([clear_time] if clear_time is not None else [])
        segments = [round(b - a, 3) for a, b in zip(marks[:-1], marks[1:])]
        return EpisodeResult(
            seed=self.seed,
            cleared=cleared,
            elapsed=round(self.t, 3),
            clear_time=round(clear_time, 3) if clear_time is not None else None,
            boss_hp_remaining=self.boss.hp_ratio,
            deaths=self.deaths,
            consumables_used=self.consumables,
            damage_dealt=round(self.damage_dealt, 1),
            damage_taken=round(self.damage_taken, 1),
            segment_times=segments,
            block_time={k: round(v, 3) for k, v in self.block_time.items()},
            gimmick_success=self.gimmick_success,
            gimmick_fail=self.gimmick_fail,
            triggers_fired=self.triggers_fired,
            invalid_actions=self.invalid_actions,
            stalled=stall_reason is not None,
            stall_reason=stall_reason,
            events=self.log.events if self.cfg.record_events else None,
        )
