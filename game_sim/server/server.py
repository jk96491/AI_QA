"""TCP 게임 서버 (게임 인스턴스 1개 = 서버 1개 = 동시 연결 1개 처리).

여러 판을 병렬로 돌리려면 서버를 포트별로 여러 개 띄운다 (문서 11장 VM 풀에 대응).
"""
from __future__ import annotations

import socket
import socketserver
import threading
from typing import Any, Dict, Optional, Tuple

from game_sim.server import protocol as P
from game_sim.server.session import GameSession
from game_sim.sim.config import SimConfig
from game_sim.spec.loader import SpecRepository


class _Handler(socketserver.StreamRequestHandler):
    server: "GameServer"

    def handle(self) -> None:
        self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        session = GameSession(self.server.repo, self.server.sim_config)

        def send(msg: Dict[str, Any]) -> None:
            self.wfile.write(P.encode(msg))
            self.wfile.flush()

        def recv() -> Optional[Dict[str, Any]]:
            while True:
                line = self.rfile.readline()
                if not line:
                    return None
                if line.strip():
                    return P.decode(line)

        while True:
            try:
                msg = recv()
            except P.ProtocolError as exc:
                send(P.error(exc.code, exc.message))
                continue
            except (ConnectionError, OSError):
                return
            if msg is None:
                return
            try:
                if not session.handle(msg, send, recv):
                    return
            except (ConnectionError, OSError):
                return


class GameServer(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7777,
        repo: Optional[SpecRepository] = None,
        sim_config: Optional[SimConfig] = None,
    ) -> None:
        self.repo = repo or SpecRepository()
        self.repo.validate_all()
        self.sim_config = sim_config or SimConfig()
        super().__init__((host, port), _Handler)

    @property
    def address(self) -> Tuple[str, int]:
        host, port = self.server_address[:2]
        return str(host), int(port)

    def start_in_thread(self) -> threading.Thread:
        """테스트·노트북용: 백그라운드 스레드에서 serve_forever."""
        t = threading.Thread(target=self.serve_forever, name="game_sim-%d" % self.address[1], daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
