"""play_agent — 학습 이후 플레이 모드 클라이언트 (AI_QA 쪽). 계약 docs/PLAY_PROTOCOL.md v0.3.

공통 부분(프로토콜 클라이언트·LLM 도구·tool use 루프·relay·LLM 백엔드)은 **SDK `btqa_play`** (별도 레포 btqa_sdk 를 직접 참조).
여기에는 학습 결과에 묶인 부분만 있다: 로드아웃(LoadoutBuilder), 전투 응답기(CombatResponder·BanditPolicy, numpy),
그 둘을 SDK 에 붙인 relay·CLI, QaArena 전용 검사(check-play), QaArena 플레이 스펙 `specs/qa_arena.play.json`
(LLM 도구 설명·안내 — SDK 에는 게임 내용이 없다).
game_sim · balance_qa · torch · btqa_game 을 import 하지 않는다 (학습 결과 파일만 읽는다).
"""
from pathlib import Path

from btqa_play.client import ActResult, Combat, PlayClient, PlayError
from play_agent.loadout import LoadoutBuilder, LoadoutEntry
from play_agent.responder import CombatResponder, ImpalaPolicy

#: QaArena 플레이 스펙 (btqa-play-spec/1) — 게임이 아직 선언하지 않은 LLM 도구 설명·스키마·안내. 게임 선언이 우선한다
QA_ARENA_SPEC = Path(__file__).resolve().parent / "specs" / "qa_arena.play.json"

__all__ = ["QA_ARENA_SPEC", "PlayClient", "PlayError", "ActResult", "Combat", "LoadoutBuilder", "LoadoutEntry", "CombatResponder", "ImpalaPolicy"]
