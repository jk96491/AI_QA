"""게임 ↔ 학습 플랫폼 프로토콜 (게임 쪽). 명세: docs/PROTOCOL.md

상수·인코딩은 게임 쪽 SDK(`btqa_game.protocol`)를 그대로 쓴다. 여기에는 이 게임의 이름·버전만 둔다.
"""
from __future__ import annotations

from btqa_game.protocol import *  # noqa: F401,F403  (기존 import 경로 호환)
from btqa_game.protocol import PROTOCOL_VERSION, ProtocolError, decode, encode, error  # noqa: F401

GAME_NAME = "game_sim"
GAME_VERSION = "0.5.0"   # 0.5.0: 프로토콜 1.3 (블록 가중치 선언, btqa_game SDK 사용)
