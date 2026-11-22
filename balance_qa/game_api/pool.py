"""게임 인스턴스 풀: 여러 게임 연결에 판을 병렬로 분배 (문서 11장 VM 풀에 대응).

게임 1개는 한 번에 판 1개만 돌린다. 풀은 연결마다 스레드 1개로 요청을 보내고 결과를 모은다.
연결이 끊기면 그 판은 무효 판으로 기록하고 재연결을 1회 시도한다.
"""
from __future__ import annotations

import queue
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Sequence, Tuple

from balance_qa.core.types import EpisodeResult, GameError
from balance_qa.game_api.client import EpisodeRequest, GameClient
from balance_qa.runner.episode_runner import EpisodeJob, EpisodeRunner
from balance_qa.spec.game_info import GameDescription


class GamePool(EpisodeRunner):
    def __init__(self, endpoints: Sequence[Tuple[str, int]], timeout: float = 120.0) -> None:
        if not endpoints:
            raise ValueError("게임 엔드포인트가 최소 1개 필요")
        self.clients: List[GameClient] = [GameClient(h, p, timeout=timeout).connect() for h, p in endpoints]
        self._idle: "queue.Queue[GameClient]" = queue.Queue()
        for c in self.clients:
            self._idle.put(c)
        self._executor: Optional[ThreadPoolExecutor] = ThreadPoolExecutor(max_workers=len(self.clients))
        self.episodes_run = 0
        self._check_same_game()

    def _check_same_game(self) -> None:
        descs = [c.describe() for c in self.clients]
        key = {(d.game, d.game_version, tuple(sorted(d.classes))) for d in descs}
        if len(key) > 1:
            raise GameError("bad_request", "풀의 게임 인스턴스 버전/데이터가 서로 다름: %s" % key)

    @property
    def size(self) -> int:
        return len(self.clients)

    def describe(self) -> GameDescription:
        return self.clients[0].describe()

    def _run_one(self, job: EpisodeJob) -> EpisodeResult:
        client = self._idle.get()
        try:
            req = EpisodeRequest(job.class_name, job.seed, job.scenario, job.record_events)
            try:
                return client.run_episode(req, job.source)
            except GameError:
                raise  # 요청 자체의 오류 (파라미터 등) 는 호출부에 알림
            except (OSError, ConnectionError, ValueError) as exc:
                try:
                    client.connect()
                except OSError:
                    pass
                return EpisodeResult.failed(job.seed, "connection: %s" % exc)
        finally:
            self._idle.put(client)

    def run(self, jobs: Sequence[EpisodeJob]) -> List[EpisodeResult]:
        self.episodes_run += len(jobs)
        if len(self.clients) == 1:
            return [self._run_one(j) for j in jobs]
        assert self._executor is not None
        return list(self._executor.map(self._run_one, jobs))

    @property
    def endpoints(self) -> List[Tuple[str, int]]:
        return [(c.host, c.port) for c in self.clients]

    def suspend(self) -> None:
        """게임 연결을 잠시 놓는다 (게임 1개 = 동시 연결 1개라, 액터 프로세스가 대신 접속할 수 있게)."""
        for c in self.clients:
            c.close()

    def resume(self) -> None:
        for c in self.clients:
            if not c.connected:
                c.connect()

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None
        for c in self.clients:
            c.close()
