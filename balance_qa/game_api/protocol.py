"""게임 프로토콜 (학습 쪽 사본). 명세: docs/PROTOCOL.md

게임 쪽 구현(game_sim/server/protocol.py, 추후 Unity C#)과 코드를 공유하지 않는다.
두 구현은 docs/PROTOCOL.md 와 conformance 검사로만 맞춘다.
"""
from __future__ import annotations

import json
from typing import Any, Dict

PROTOCOL_VERSION = "1.3"  # 1.1: trigger.totals / 1.2: result.stalled / 1.3: classes[].blocks (같은 주 버전 1.x 게임과 호환)
CLIENT_NAME = "balance_qa"

# 학습 → 게임
HELLO = "hello"
DESCRIBE = "describe"
RUN_EPISODE = "run_episode"
TRIGGER_RESPONSE = "trigger_response"
BYE = "bye"

# 게임 → 학습
HELLO_OK = "hello_ok"
DESCRIPTION = "description"
TRIGGER = "trigger"
EPISODE_RESULT = "episode_result"
ERROR = "error"

ERROR_CODES = (
    "bad_request",
    "unknown_type",
    "protocol_version",
    "unknown_class",
    "unknown_scenario",
    "unknown_param",
    "param_out_of_range",
    "internal",
)


def encode(msg: Dict[str, Any]) -> bytes:
    return (json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def decode(line: bytes) -> Dict[str, Any]:
    msg = json.loads(line.decode("utf-8"))
    if not isinstance(msg, dict) or "type" not in msg:
        raise ValueError("게임 메시지에 'type' 없음: %r" % (msg,))
    return msg


def major(version: str) -> str:
    return str(version).split(".")[0]
