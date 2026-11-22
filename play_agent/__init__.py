"""play_agent — 학습 이후 플레이 모드 클라이언트 (docs/PLAY_PROTOCOL.md v0.2).

비전투 = LLM(Claude API tool use 루프), 전투 = 게임 안 CombatSim+BT(학습 params) + 트리거 즉답(IMPALA 정책 numpy).
game_sim · balance_qa · torch 를 import 하지 않는다 (학습 결과 파일만 읽는다).
"""
from play_agent.client import ActResult, Combat, PlayClient, PlayError
from play_agent.loadout import LoadoutBuilder, LoadoutEntry
from play_agent.responder import CombatResponder, ImpalaPolicy

__all__ = ["PlayClient", "PlayError", "ActResult", "Combat", "LoadoutBuilder", "LoadoutEntry", "CombatResponder", "ImpalaPolicy"]
