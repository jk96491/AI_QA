"""TCP 게임 서버 (게임 인스턴스 1개 = 서버 1개 = 동시 연결 1개 처리). 게임 쪽 SDK `btqa_game.QaGameServer` 사용.

여러 판을 병렬로 돌리려면 서버를 포트별로 여러 개 띄운다 (문서 11장 VM 풀에 대응).
"""
from __future__ import annotations

from typing import Optional

from btqa_game import QaGameServer
from game_sim.server.session import GameSimHost
from game_sim.sim.config import SimConfig
from game_sim.spec.loader import SpecRepository


class GameServer(QaGameServer):
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
        super().__init__(lambda: GameSimHost(self.repo, self.sim_config), host, port)
