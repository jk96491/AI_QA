"""PilotRelay (AI_QA) — SDK `btqa_play.PilotRelay` 에 학습 결과 로드아웃·전투 응답기를 붙인 것. API 호출 없음.

중계 방식·step 메시지·기록 형식은 SDK 와 같다 (btqa_sdk/python/btqa_play/relay.py). 여기서 더하는 것:
    prepare  : reports/<run> 의 params.json·policy.json → play_description 과 맞춰 보고 set_loadout, 응답기 = LoadoutBuilder.responder()
    run_meta : run.json 에 로드아웃 출처
    spec     : 기본 = QaArena 플레이 스펙 (play_agent/specs/qa_arena.play.json)
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from btqa_play.client import PlayClient, TriggerResponder
from btqa_play.relay import DEFAULT_RELAY_PORT, relay_step
from btqa_play.relay import PilotRelay as SdkPilotRelay
from play_agent import QA_ARENA_SPEC
from play_agent.loadout import LoadoutBuilder


class PilotRelay(SdkPilotRelay):
    def __init__(self, game: str, loadout: Optional[List[str]] = None, seed: int = 1, cls: str = "warrior",
                 port: int = DEFAULT_RELAY_PORT, out: str = "reports", pilot: str = "claude-code",
                 spec: Any = QA_ARENA_SPEC) -> None:
        super().__init__(game, seed=seed, cls=cls, port=port, out=out, pilot=pilot, spec=spec)
        self.lb = LoadoutBuilder()
        for p in loadout or []:
            self.lb.add_file(p)

    def prepare(self, client: PlayClient, desc: Mapping[str, Any]) -> Optional[TriggerResponder]:
        problems = self.lb.check_against(desc)
        if problems:
            raise SystemExit("로드아웃 문제: " + "; ".join(problems))
        if self.lb.entries:
            client.set_loadout(self.lb.wire_entries(desc), persona=self.lb.persona())
        return self.lb.responder()

    def run_meta(self) -> Dict[str, Any]:
        return {"loadout": [e.source for e in self.lb.entries.values()]}

    def notes(self) -> List[str]:
        return list(self.lb.notes)


__all__ = ["PilotRelay", "relay_step", "DEFAULT_RELAY_PORT"]
