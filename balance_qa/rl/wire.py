"""학습기 ↔ 액터 전송 형식 (TCP JSON Lines, 실수 배열은 base64 float32).

게임 프로토콜(docs/PROTOCOL.md)과 별개인 balance_qa 내부 프로토콜이다 (양쪽 모두 파이썬).

액터 → 학습기                          학습기 → 액터
  register {actor_id, token}             config {spec}            | error
  work_request {have_version}            work {seed, version, weights|null} | stop
  episode {trajectory} | {invalid}       ack
  fatal {code, message}                  ack
  bye
"""
from __future__ import annotations

import base64
import json
from typing import Any, Dict, Optional

import numpy as np

from balance_qa.core.types import EpisodeResult
from balance_qa.rl.trajectory import Step, Trajectory

WIRE_VERSION = "1"


def encode(msg: Dict[str, Any]) -> bytes:
    return (json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def decode(line: bytes) -> Dict[str, Any]:
    msg = json.loads(line.decode("utf-8"))
    if not isinstance(msg, dict) or "type" not in msg:
        raise ValueError("메시지에 'type' 없음")
    return msg


def pack_floats(arr) -> str:
    return base64.b64encode(np.asarray(arr, dtype=np.float32).tobytes()).decode("ascii")


def unpack_floats(s: Optional[str]) -> Optional[np.ndarray]:
    if s is None:
        return None
    return np.frombuffer(base64.b64decode(s), dtype=np.float32).astype(float)


def trajectory_to_wire(t: Trajectory) -> Dict[str, Any]:
    return {
        "seed": t.seed,
        "version": t.policy_version,
        "rewards": [float(r) for r in t.rewards],
        "result": t.result.to_dict(),
        "steps": [
            {
                "index": s.index,
                "obs": pack_floats(s.obs),
                "action": pack_floats(s.action),
                "logp": float(s.behavior_logp),
                "value": float(s.value),
                "totals": s.totals,
            }
            for s in t.steps
        ],
    }


def trajectory_from_wire(d: Dict[str, Any]) -> Trajectory:
    steps = [
        Step(int(s["index"]), unpack_floats(s["obs"]), unpack_floats(s["action"]), float(s["logp"]),
             dict(s.get("totals", {})), float(s.get("value", 0.0)))
        for s in d["steps"]
    ]
    return Trajectory(steps, [float(r) for r in d["rewards"]], EpisodeResult.from_dict(d["result"]),
                      int(d["version"]), int(d["seed"]))
