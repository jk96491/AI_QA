"""원격 액터 (액터 프로세스 쪽). 학습기에 접속해 설정·작업·가중치를 받고, 게임에서 판을 돌려 궤적을 보낸다.

    python -m balance_qa --game 127.0.0.1:7777 actor --learner 127.0.0.1:7000
    python -m balance_qa --game-cmd "Game.exe -batchmode -qaPort {port}" actor --learner 10.0.0.5:7000 --token xxx

로컬 processes 모드에서는 학습기가 이 명령을 자동으로 띄우고, 클라우드에서는 각 머신에서 직접 실행한다.
"""
from __future__ import annotations

import socket
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from balance_qa.core.types import GameError
from balance_qa.game_api.client import GameClient
from balance_qa.rl import wire
from balance_qa.rl.actor import ActorCore, InvalidEpisode
from balance_qa.rl.spec import ActorSpec


class ActorConfigError(RuntimeError):
    pass


def check_compatible(spec: ActorSpec, client: GameClient) -> List[str]:
    """학습기 설정과 이 액터가 붙은 게임이 맞는지. 치명적 문제 목록 반환."""
    d = client.describe()
    problems = []
    if spec.class_name not in d.classes:
        problems.append("게임에 class %r 없음" % spec.class_name)
    if spec.scenario not in d.scenarios:
        problems.append("게임에 scenario %r 없음" % spec.scenario)
    if tuple(d.state_features) != tuple(spec.state_features):
        problems.append("state_features 불일치: 게임 %s / 학습기 %s" % (list(d.state_features), list(spec.state_features)))
    bandit = spec.extra.get("bandit")
    if bandit:   # 컨텍스트 밴딧: 모든 조합 + 판 시작 상태 선언 필요, 구간 보상(totals)은 불필요
        for cls, sc in bandit["sampler"].get("combos", []):
            if cls not in d.classes or sc not in d.scenarios:
                problems.append("게임에 조합 %s/%s 없음" % (cls, sc))
        declared = {s.name for s in d.initial_state}
        missing = [s["name"] for s in bandit["sampler"].get("states", []) if s["name"] not in declared]
        if missing:
            problems.append("게임이 initial_state %s 를 선언하지 않음 (프로토콜 v1.4 필요)" % missing)
    elif not d.supports_segment_rewards:
        problems.append("게임이 trigger.totals 를 보내지 않음 (프로토콜 v1.1 필요)")
    if abs(d.time_limit - spec.time_limit) > 1e-6:
        problems.append("time_limit 불일치: 게임 %s / 학습기 %s" % (d.time_limit, spec.time_limit))
    return problems


class RemoteActor:
    def __init__(
        self,
        learner: Tuple[str, int],
        game: GameClient,
        actor_id: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 600.0,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.learner = learner
        self.game = game
        self.actor_id = actor_id or "%s-%d" % (socket.gethostname(), game.port)
        self.token = token
        self.timeout = timeout
        self.log = log or (lambda s: None)
        self._sock: Optional[socket.socket] = None
        self._r = self._w = None
        self.spec: Optional[ActorSpec] = None

    # ------------------------------------------------------------------ 학습기 통신
    def _send(self, msg: Dict[str, Any]) -> None:
        assert self._w is not None
        self._w.write(wire.encode(msg))
        self._w.flush()

    def _recv(self) -> Dict[str, Any]:
        assert self._r is not None
        while True:
            line = self._r.readline()
            if not line:
                raise ConnectionError("학습기가 연결을 닫음")
            if line.strip():
                return wire.decode(line)

    def _connect(self, retry_seconds: float = 30.0) -> None:
        deadline = time.time() + retry_seconds
        while True:
            try:
                sock = socket.create_connection(self.learner, timeout=10)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(self.timeout)
        self._sock = sock
        self._r = sock.makefile("rb")
        self._w = sock.makefile("wb")

    def close(self) -> None:
        for f in (self._r, self._w, self._sock):
            try:
                if f is not None:
                    f.close()
            except OSError:
                pass
        self._sock = self._r = self._w = None

    # ------------------------------------------------------------------ 메인 루프
    def run(self) -> Dict[str, Any]:
        self._connect()
        try:
            self._send({"type": "register", "actor_id": self.actor_id, "token": self.token,
                        "game": "%s:%d" % (self.game.host, self.game.port)})
            reply = self._recv()
            if reply.get("type") != "config":
                raise ActorConfigError("학습기 거부: %s" % reply.get("message", reply))
            self.spec = spec = ActorSpec.from_wire(reply["spec"])

            if not self.game.connected:
                self.game.connect()
            problems = check_compatible(spec, self.game)
            if problems:
                self._send({"type": "fatal", "code": "incompatible_game", "message": "; ".join(problems)})
                self._recv()
                raise ActorConfigError("; ".join(problems))
            self.log("[actor %s] 학습기 %s:%d / 게임 %s:%d / %s %s"
                     % (self.actor_id, self.learner[0], self.learner[1], self.game.host, self.game.port,
                        spec.class_name, spec.scenario))

            core = ActorCore(self.game, spec)
            while True:
                self._send({"type": "work_request", "have_version": core.version})
                work = self._recv()
                if work.get("type") == "stop":
                    break
                if work.get("type") != "work":
                    raise ActorConfigError("예상하지 못한 메시지: %s" % work)
                flat = wire.unpack_floats(work.get("weights"))
                if flat is not None:
                    core.load_flat(int(work["version"]), flat)
                try:
                    item = core.run(int(work["seed"]))
                except GameError as exc:
                    self._send({"type": "fatal", "code": exc.code, "message": exc.message})
                    self._recv()
                    raise
                if isinstance(item, InvalidEpisode):
                    self._send({"type": "episode", "seed": item.seed, "invalid": item.reason})
                else:
                    self._send({"type": "episode", "trajectory": wire.trajectory_to_wire(item)})
                self._recv()  # ack
            self._send({"type": "bye"})
            return {"actor_id": self.actor_id, "episodes": core.episodes, "invalid": core.invalid}
        finally:
            self.close()
