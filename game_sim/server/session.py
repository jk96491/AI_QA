"""연결 1개에 대한 게임 세션: 메시지를 받아 처리하고 응답한다.

Unity 구현 시 이 클래스가 하는 일을 그대로 옮기면 된다:
  hello → hello_ok, describe → description,
  run_episode → (trigger ↔ trigger_response)* → episode_result
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from game_sim.core.types import TRIGGER_STATE_FEATURES, TRIGGER_TOTALS_FIELDS
from game_sim.server import protocol as P
from game_sim.sim.config import SimConfig
from game_sim.sim.engine import CombatSim
from game_sim.spec.class_spec import ParamError
from game_sim.spec.loader import SpecRepository

Send = Callable[[Dict[str, Any]], None]
Recv = Callable[[], Optional[Dict[str, Any]]]


class GameSession:
    def __init__(self, repo: SpecRepository, sim_config: Optional[SimConfig] = None) -> None:
        self.repo = repo
        self.sim_config = sim_config or SimConfig()
        self.greeted = False

    # ------------------------------------------------------------------ describe
    def description(self) -> Dict[str, Any]:
        cfg = self.sim_config
        boss = self.repo.load_boss("default")
        return {
            "type": P.DESCRIPTION,
            "protocol_version": P.PROTOCOL_VERSION,
            "game": P.GAME_NAME,
            "game_version": P.GAME_VERSION,
            "time_limit": cfg.time_limit,
            "max_deaths": cfg.max_deaths,
            "decision_interval": cfg.dt,
            "classes": [self.repo.load_class(n).to_wire() for n in self.repo.class_names()],
            "scenarios": [
                {"name": sc.name, "description": sc.description} for sc in self.repo.scenarios().values()
            ],
            "triggers": {
                "type": "boss_hp_below",
                "supported": list(boss.phase_thresholds),
                "state_features": list(TRIGGER_STATE_FEATURES),
                "totals": list(TRIGGER_TOTALS_FIELDS),
            },
            "result_fields": [
                "seed", "cleared", "elapsed", "clear_time", "boss_hp_remaining", "deaths",
                "consumables_used", "damage_dealt", "damage_taken", "segment_times", "block_time",
                "gimmick_success", "gimmick_fail", "triggers_fired", "invalid_actions",
                "stalled", "stall_reason", "invalid", "invalid_reason",
            ],
        }

    # ------------------------------------------------------------------ run_episode
    def _validate_episode(self, msg: Mapping[str, Any]) -> None:
        for key in ("episode_id", "class", "seed"):
            if key not in msg:
                raise P.ProtocolError(P.E_BAD_REQUEST, "run_episode 에 %r 필요" % key)
        if msg["class"] not in self.repo.class_names():
            raise P.ProtocolError(P.E_UNKNOWN_CLASS, "알 수 없는 class %r" % msg["class"])
        scenario = msg.get("scenario") or "base"
        if scenario not in self.repo.scenarios():
            raise P.ProtocolError(P.E_UNKNOWN_SCENARIO, "알 수 없는 scenario %r" % scenario)
        if not isinstance(msg.get("params", {}), dict):
            raise P.ProtocolError(P.E_BAD_REQUEST, "params 는 객체여야 함")

    def run_episode(self, msg: Mapping[str, Any], send: Send, recv: Recv) -> Dict[str, Any]:
        self._validate_episode(msg)
        episode_id = msg["episode_id"]
        spec = self.repo.load_class(msg["class"])
        boss = self.repo.boss_for(msg.get("scenario") or "base")
        triggers = (msg.get("triggers") or {}).get("boss_hp_below", [])
        cfg = self.sim_config
        if msg.get("record_events"):
            from dataclasses import replace

            cfg = replace(cfg, record_events=True)

        def on_trigger(index: int, state: Dict[str, float], totals: Dict[str, float]) -> Mapping[str, float]:
            send({"type": P.TRIGGER, "episode_id": episode_id, "index": index, "state": state, "totals": totals})
            reply = recv()
            if reply is None:
                raise ConnectionError("trigger 응답 대기 중 연결 종료")
            if reply.get("type") != P.TRIGGER_RESPONSE or reply.get("episode_id") != episode_id:
                raise P.ProtocolError(P.E_BAD_REQUEST, "trigger_response(episode_id=%r) 를 기대했으나 %r" % (episode_id, reply.get("type")))
            if reply.get("index") != index:
                raise P.ProtocolError(P.E_BAD_REQUEST, "trigger_response index %r != %r" % (reply.get("index"), index))
            return reply.get("params") or {}

        try:
            sim = CombatSim(spec, boss, msg.get("params") or {}, int(msg["seed"]), cfg, triggers, on_trigger)
            result = sim.run()
        except ParamError as exc:
            raise P.ProtocolError(exc.code, str(exc))
        return {
            "type": P.EPISODE_RESULT,
            "episode_id": episode_id,
            "result": result.to_dict(include_events=bool(msg.get("record_events"))),
        }

    # ------------------------------------------------------------------ 디스패치
    def handle(self, msg: Mapping[str, Any], send: Send, recv: Recv) -> bool:
        """메시지 1개 처리. 연결을 닫아야 하면 False."""
        kind = msg.get("type")
        try:
            if kind == P.HELLO:
                if str(msg.get("protocol_version", "")).split(".")[0] != P.PROTOCOL_VERSION.split(".")[0]:
                    raise P.ProtocolError(P.E_PROTOCOL_VERSION, "지원 버전 %s, 요청 %r" % (P.PROTOCOL_VERSION, msg.get("protocol_version")))
                self.greeted = True
                send({"type": P.HELLO_OK, "protocol_version": P.PROTOCOL_VERSION, "game": P.GAME_NAME, "game_version": P.GAME_VERSION})
            elif kind == P.DESCRIBE:
                send(self.description())
            elif kind == P.RUN_EPISODE:
                send(self.run_episode(msg, send, recv))
            elif kind == P.BYE:
                return False
            else:
                raise P.ProtocolError(P.E_UNKNOWN_TYPE, "알 수 없는 type %r" % kind)
        except P.ProtocolError as exc:
            send(P.error(exc.code, exc.message, episode_id=msg.get("episode_id")))
        except ConnectionError:
            return False
        except Exception as exc:  # 게임 내부 오류도 연결은 유지
            send(P.error(P.E_INTERNAL, "%s: %s" % (type(exc).__name__, exc), episode_id=msg.get("episode_id")))
        return True
