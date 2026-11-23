"""game_sim 의 EpisodeHost (게임 쪽 SDK `btqa_game` 구현체).

SDK 가 메시지 처리·요청 검증·트리거 왕복 검사를 하고, 여기는 이 게임 고유의 두 가지만 한다:
  - declaration(): 정의서 (직업 파라미터 + BT 전략 블록 가중치)
  - run_episode(): CombatSim 으로 판 1개 실행
Unity 판은 unity_game/Assets/QA/Protocol/QaArenaHost.cs.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Dict, Mapping, Optional

from btqa_game import (
    BlockDecl,
    ClassDecl,
    EpisodeHost,
    EpisodeRequest,
    GameDecl,
    GameSession as _SdkSession,
    ParamDecl,
    ScenarioDecl,
    TriggerChannel,
    TriggerDecl,
)
from btqa_game.protocol import ProtocolError
from game_sim.bt.agent import strategy_blocks
from game_sim.core.types import TRIGGER_STATE_FEATURES, TRIGGER_TOTALS_FIELDS
from game_sim.server import protocol as P
from game_sim.sim.config import SimConfig
from game_sim.sim.engine import CombatSim
from game_sim.spec.class_spec import ClassSpec, ParamError
from game_sim.spec.loader import SpecRepository

Send = Callable[[Dict[str, Any]], None]
Recv = Callable[[], Optional[Dict[str, Any]]]

RESULT_FIELDS = (
    "seed", "cleared", "elapsed", "clear_time", "boss_hp_remaining", "deaths",
    "consumables_used", "damage_dealt", "damage_taken", "segment_times", "block_time",
    "gimmick_success", "gimmick_fail", "triggers_fired", "invalid_actions",
    "stalled", "stall_reason", "invalid", "invalid_reason",
)


def class_decl(spec: ClassSpec) -> ClassDecl:
    return ClassDecl(
        name=spec.name,
        display_name=spec.display_name,
        ranged=spec.ranged,
        spec_version=spec.spec_version,
        params=tuple(
            ParamDecl(p.name, p.low, p.high, p.default, group=p.group, unit=p.unit,
                      description=p.description, optimize=p.explicit_optimize)
            for p in spec.params.values()
        ),
        blocks=tuple(BlockDecl(name, weight, desc) for name, weight, desc in strategy_blocks()),
    )


class GameSimHost(EpisodeHost):
    def __init__(self, repo: SpecRepository, sim_config: Optional[SimConfig] = None) -> None:
        self.repo = repo
        self.sim_config = sim_config or SimConfig()
        self._decl: Optional[GameDecl] = None

    def declaration(self) -> GameDecl:
        if self._decl is None:
            cfg = self.sim_config
            boss = self.repo.load_boss("default")
            self._decl = GameDecl(
                game=P.GAME_NAME,
                game_version=P.GAME_VERSION,
                time_limit=cfg.time_limit,
                max_deaths=cfg.max_deaths,
                decision_interval=cfg.dt,
                classes=tuple(class_decl(self.repo.load_class(n)) for n in self.repo.class_names()),
                scenarios=tuple(ScenarioDecl(sc.name, sc.description) for sc in self.repo.scenarios().values()),
                triggers=TriggerDecl("boss_hp_below", tuple(boss.phase_thresholds),
                                     tuple(TRIGGER_STATE_FEATURES), tuple(TRIGGER_TOTALS_FIELDS)),
                result_fields=RESULT_FIELDS,
            )
        return self._decl

    def run_episode(self, request: EpisodeRequest, triggers: TriggerChannel) -> Dict[str, Any]:
        spec = self.repo.load_class(request.class_name)
        boss = self.repo.boss_for(request.scenario)
        cfg = replace(self.sim_config, record_events=True) if request.record_events else self.sim_config

        def on_trigger(index: int, state: Dict[str, float], totals: Dict[str, float]) -> Mapping[str, float]:
            return triggers.fire(index, state, totals)

        try:
            sim = CombatSim(spec, boss, request.params, request.seed, cfg, request.thresholds, on_trigger)
            result = sim.run()
        except ParamError as exc:
            raise ProtocolError(exc.code, str(exc))
        return result.to_dict(include_events=request.record_events)


class GameSession(_SdkSession):
    """기존 호출 호환: GameSession(repo, sim_config)."""

    def __init__(self, repo: SpecRepository, sim_config: Optional[SimConfig] = None) -> None:
        super().__init__(GameSimHost(repo, sim_config))

    def description(self) -> Dict[str, Any]:
        return self.decl.to_wire()
