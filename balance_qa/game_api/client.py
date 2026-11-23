"""게임 연결 1개 (TCP JSON Lines 클라이언트)."""
from __future__ import annotations

import itertools
import socket
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from balance_qa.control.param_source import ParamSource
from balance_qa.core.types import EpisodeResult, GameError, TriggerState
from balance_qa.game_api import protocol as P
from balance_qa.spec.game_info import GameDescription

_ids = itertools.count(1)


def parse_endpoint(text: str) -> Tuple[str, int]:
    host, _, port = text.strip().rpartition(":")
    return (host or "127.0.0.1"), int(port)


@dataclass
class EpisodeRequest:
    class_name: str
    seed: int
    scenario: str = "base"
    record_events: bool = False


class GameClient:
    def __init__(self, host: str, port: int, timeout: float = 120.0, connect_timeout: float = 10.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.name = "%s:%d" % (host, port)
        self._sock: Optional[socket.socket] = None
        self._rfile = None
        self._wfile = None
        self._desc: Optional[GameDescription] = None
        self.hello_info: Dict[str, Any] = {}
        #: 디버깅용 메시지 기록 훅 (direction, msg)
        self.tap: Optional[Callable[[str, Dict[str, Any]], None]] = None

    # ------------------------------------------------------------------ 연결
    def connect(self) -> "GameClient":
        self.close()
        sock = socket.create_connection((self.host, self.port), timeout=self.connect_timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(self.timeout)
        self._sock = sock
        self._rfile = sock.makefile("rb")
        self._wfile = sock.makefile("wb")
        self.hello()
        return self

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def close(self) -> None:
        if self._sock is None:
            return
        try:
            self._send({"type": P.BYE})
        except OSError:
            pass
        for f in (self._rfile, self._wfile, self._sock):
            try:
                f.close()  # type: ignore[union-attr]
            except OSError:
                pass
        self._sock = self._rfile = self._wfile = None

    def __enter__(self) -> "GameClient":
        return self.connect() if not self.connected else self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ 송수신
    def _send(self, msg: Dict[str, Any]) -> None:
        if self._wfile is None:
            raise ConnectionError("게임 %s 에 연결되지 않음" % self.name)
        if self.tap:
            self.tap("send", msg)
        self._wfile.write(P.encode(msg))
        self._wfile.flush()

    def _recv(self) -> Dict[str, Any]:
        if self._rfile is None:
            raise ConnectionError("게임 %s 에 연결되지 않음" % self.name)
        while True:
            line = self._rfile.readline()
            if not line:
                raise ConnectionError("게임 %s 가 연결을 닫음" % self.name)
            if line.strip():
                msg = P.decode(line)
                if self.tap:
                    self.tap("recv", msg)
                return msg

    def request(self, msg: Dict[str, Any], expect: str) -> Dict[str, Any]:
        self._send(msg)
        reply = self._recv()
        if reply["type"] == P.ERROR:
            raise GameError(reply.get("code", "?"), reply.get("message", ""), reply.get("episode_id"))
        if reply["type"] != expect:
            raise GameError("bad_request", "%s 를 기대했으나 %s" % (expect, reply["type"]))
        return reply

    # ------------------------------------------------------------------ API
    def hello(self) -> Dict[str, Any]:
        reply = self.request({"type": P.HELLO, "protocol_version": P.PROTOCOL_VERSION, "client": P.CLIENT_NAME}, P.HELLO_OK)
        if P.major(reply.get("protocol_version", "")) != P.major(P.PROTOCOL_VERSION):
            raise GameError("protocol_version", "게임 %s, 클라이언트 %s" % (reply.get("protocol_version"), P.PROTOCOL_VERSION))
        self.hello_info = reply
        return reply

    def describe(self, refresh: bool = False) -> GameDescription:
        if self._desc is None or refresh:
            self._desc = GameDescription.from_wire(self.request({"type": P.DESCRIBE}, P.DESCRIPTION))
        return self._desc

    def run_episode(self, req: EpisodeRequest, source: ParamSource) -> EpisodeResult:
        """판 1개 실행. 트리거가 오면 source.on_trigger 로 응답한다."""
        # describe 는 run_episode 를 보내기 *전에* 확보해야 함 (판 진행 중 다른 요청을 끼워 넣으면 응답이 섞임)
        desc = self.describe()
        features: List[str] = list(desc.state_features)
        episode_id = "%s#%d" % (self.name, next(_ids))
        msg: Dict[str, Any] = {
            "type": P.RUN_EPISODE,
            "episode_id": episode_id,
            "class": req.class_name,
            "scenario": req.scenario,
            "seed": int(req.seed),
            "params": source.base_params(),
        }
        if source.trigger_thresholds:
            msg["triggers"] = {desc.trigger_type: list(source.trigger_thresholds)}   # 키 = describe.triggers.type
        if req.record_events:
            msg["record_events"] = True
        self._send(msg)
        while True:
            reply = self._recv()
            kind = reply["type"]
            if kind == P.TRIGGER:
                state = TriggerState(int(reply["index"]), dict(reply.get("state", {})), features,
                                     dict(reply.get("totals", {})))
                params = source.on_trigger(state)
                self._send({"type": P.TRIGGER_RESPONSE, "episode_id": episode_id, "index": state.index, "params": params})
            elif kind == P.EPISODE_RESULT:
                return EpisodeResult.from_dict(reply["result"])
            elif kind == P.ERROR:
                raise GameError(reply.get("code", "?"), reply.get("message", ""), reply.get("episode_id"))
            else:
                raise GameError("bad_request", "run_episode 중 예상하지 못한 메시지 %r" % kind)
