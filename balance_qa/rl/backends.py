"""IMPALA 액터 백엔드 — 액터를 어디서 어떻게 돌릴지.

| 모드        | 클래스                                   | 액터 위치                               | 용도 |
|-------------|------------------------------------------|-----------------------------------------|------|
| threads     | ThreadActorBackend                       | 학습기 프로세스 안 스레드                | 테스트·가벼운 실행 |
| processes   | RemoteActorBackend(game_endpoints=[...]) | 로컬 액터 프로세스 N개 (자동 실행)        | **로컬 다중 액터 (기본)** |
| external    | RemoteActorBackend(game_endpoints=None)  | 어디서든 `python -m balance_qa actor` 로 접속 | 클라우드·다른 머신 |

processes / external 은 같은 LearnerServer(TCP) 를 쓰므로, 로컬에서 검증한 구조가 그대로 클라우드로 간다.
"""
from __future__ import annotations

import itertools
import os
import queue
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from balance_qa.core.types import GameError
from balance_qa.game_api.client import GameClient
from balance_qa.rl import wire
from balance_qa.rl.actor import ActorCore, ActorWorker, InvalidEpisode, ParameterServer
from balance_qa.rl.spec import ActorSpec
from balance_qa.runner.seed_pool import SeedPool

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class ActorContext:
    """학습기와 액터들이 공유하는 상태: 설정, 가중치, 작업(seed) 발급, 결과 큐, 정지 신호."""

    def __init__(self, spec: ActorSpec, params: ParameterServer, seeds: SeedPool, queue_size: int = 256) -> None:
        self.spec = spec
        self.params = params
        self.seeds = seeds
        self.out: "queue.Queue" = queue.Queue(maxsize=queue_size)
        self.stop = threading.Event()
        self._counter = itertools.count()
        self._lock = threading.Lock()
        self.issued = 0

    def next_seed(self) -> Optional[int]:
        """다음 판의 seed. 학습기가 정지했으면 None."""
        with self._lock:
            if self.stop.is_set():
                return None
            n = next(self._counter)
            self.issued += 1
        return self.seeds.batch(n, 1)[0]

    def put(self, item: Any) -> bool:
        """결과 전달. 정지 후에는 버리고 False (큐가 가득 차도 막히지 않음)."""
        while not self.stop.is_set():
            try:
                self.out.put(item, timeout=0.5)
                return True
            except queue.Full:
                continue
        return False


class ActorBackend(ABC):
    name = "backend"

    @abstractmethod
    def start(self, ctx: ActorContext) -> None:
        ...

    @abstractmethod
    def alive(self) -> bool:
        """결과를 더 보낼 수 있는 액터가 남아 있는가."""

    @abstractmethod
    def stop(self) -> None:
        ...

    @property
    @abstractmethod
    def n_actors(self) -> int:
        ...

    def describe(self) -> Dict[str, Any]:
        return {"mode": self.name, "actors": self.n_actors}


# ---------------------------------------------------------------------- threads
class ThreadActorBackend(ActorBackend):
    name = "threads"

    def __init__(self, clients: Sequence[GameClient]) -> None:
        if not clients:
            raise ValueError("액터용 게임 연결이 최소 1개 필요")
        self.clients = list(clients)
        self.workers: List[ActorWorker] = []

    @property
    def n_actors(self) -> int:
        return len(self.clients)

    def start(self, ctx: ActorContext) -> None:
        self.workers = [ActorWorker(i, ActorCore(c, ctx.spec), ctx) for i, c in enumerate(self.clients)]
        for w in self.workers:
            w.start()

    def alive(self) -> bool:
        return any(w.is_alive() for w in self.workers)

    def stop(self) -> None:
        for w in self.workers:
            w.join(timeout=60)


# ---------------------------------------------------------------------- 학습기 서버 (processes / external)
class _ActorHandler(socketserver.StreamRequestHandler):
    server: "LearnerServer"

    def _send(self, msg: Dict[str, Any]) -> None:
        self.wfile.write(wire.encode(msg))
        self.wfile.flush()

    def handle(self) -> None:
        srv = self.server
        ctx = srv.ctx
        self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        actor_id: Optional[str] = None
        try:
            while True:
                line = self.rfile.readline()
                if not line:
                    break
                if not line.strip():
                    continue
                msg = wire.decode(line)
                kind = msg.get("type")
                if kind == "register":
                    if srv.token and msg.get("token") != srv.token:
                        self._send({"type": "error", "message": "token 불일치"})
                        break
                    actor_id = str(msg.get("actor_id") or "%s:%d" % self.client_address[:2])
                    srv.on_register(actor_id, msg)
                    self._send({"type": "config", "wire_version": wire.WIRE_VERSION, "spec": ctx.spec.to_wire()})
                elif actor_id is None:
                    self._send({"type": "error", "message": "register 먼저"})
                    break
                elif kind == "work_request":
                    seed = ctx.next_seed()
                    if seed is None:
                        self._send({"type": "stop"})
                        continue
                    version, flat = ctx.params.fetch_flat(int(msg.get("have_version", -1)))
                    self._send({"type": "work", "seed": seed, "version": version,
                                "weights": wire.pack_floats(flat) if flat is not None else None})
                elif kind == "episode":
                    if msg.get("invalid") is not None:
                        item: Any = InvalidEpisode(int(msg.get("seed", -1)), "actor %s: %s" % (actor_id, msg["invalid"]))
                    else:
                        item = wire.trajectory_from_wire(msg["trajectory"])
                    srv.on_episode(actor_id)
                    ctx.put(item)
                    self._send({"type": "ack"})
                elif kind == "fatal":
                    ctx.put(GameError(str(msg.get("code", "actor")), "actor %s: %s" % (actor_id, msg.get("message", ""))))
                    self._send({"type": "ack"})
                elif kind == "bye":
                    break
                else:
                    self._send({"type": "error", "message": "알 수 없는 type %r" % kind})
        except (OSError, ConnectionError, ValueError):
            pass
        finally:
            if actor_id is not None:
                srv.on_disconnect(actor_id)


class LearnerServer(socketserver.ThreadingTCPServer):
    """액터 접속을 받는 학습기 쪽 TCP 서버 (연결마다 스레드)."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: Tuple[str, int], ctx: ActorContext, token: Optional[str] = None) -> None:
        self.ctx = ctx
        self.token = token
        self._lock = threading.Lock()
        self.connected: Dict[str, float] = {}
        self.episodes_by_actor: Dict[str, int] = {}
        self.ever_connected = 0
        super().__init__(address, _ActorHandler)

    @property
    def address(self) -> Tuple[str, int]:
        host, port = self.server_address[:2]
        return str(host), int(port)

    def on_register(self, actor_id: str, msg: Dict[str, Any]) -> None:
        with self._lock:
            self.connected[actor_id] = time.time()
            self.episodes_by_actor.setdefault(actor_id, 0)
            self.ever_connected += 1

    def on_episode(self, actor_id: str) -> None:
        with self._lock:
            self.episodes_by_actor[actor_id] = self.episodes_by_actor.get(actor_id, 0) + 1

    def on_disconnect(self, actor_id: str) -> None:
        with self._lock:
            self.connected.pop(actor_id, None)

    @property
    def n_connected(self) -> int:
        with self._lock:
            return len(self.connected)


class ActorProcessLauncher:
    """로컬 액터 프로세스 N개: `python -m balance_qa --game <ep> actor --learner <addr>`."""

    def __init__(self, learner: Tuple[str, int], game_endpoints: Sequence[Tuple[str, int]],
                 token: Optional[str] = None) -> None:
        self.learner = learner
        self.game_endpoints = list(game_endpoints)
        self.token = token
        self.procs: List[subprocess.Popen] = []
        self.logs: List[Any] = []

    def start(self) -> "ActorProcessLauncher":
        env = dict(os.environ)
        env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        for i, (host, port) in enumerate(self.game_endpoints):
            cmd = [sys.executable, "-m", "balance_qa", "--game", "%s:%d" % (host, port),
                   "actor", "--learner", "%s:%d" % self.learner, "--actor-id", "local-%d" % i]
            if self.token:
                cmd += ["--token", self.token]
            log = tempfile.TemporaryFile()
            self.logs.append(log)
            self.procs.append(subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), env=env,
                                               stdout=subprocess.DEVNULL, stderr=log))
        return self

    def any_alive(self) -> bool:
        return any(p.poll() is None for p in self.procs)

    def failures(self) -> List[str]:
        out = []
        for i, (p, log) in enumerate(zip(self.procs, self.logs)):
            if p.poll() not in (None, 0):
                log.seek(0)
                out.append("actor %d (exit %s): %s" % (i, p.returncode, log.read().decode("utf-8", "replace")[-800:]))
        return out

    def stop(self, timeout: float = 30.0) -> None:
        deadline = time.time() + timeout
        for p in self.procs:
            try:
                p.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        for log in self.logs:
            log.close()
        self.procs, self.logs = [], []


class RemoteActorBackend(ActorBackend):
    """학습기 서버 + (선택) 로컬 액터 프로세스 자동 실행.

    game_endpoints 를 주면 엔드포인트마다 액터 프로세스 1개를 띄운다 (processes 모드).
    None 이면 외부 액터 접속만 기다린다 (external 모드, 클라우드용).
    """

    def __init__(
        self,
        listen: Tuple[str, int] = ("127.0.0.1", 0),
        game_endpoints: Optional[Sequence[Tuple[str, int]]] = None,
        token: Optional[str] = None,
        on_listen=None,
    ) -> None:
        self.listen = listen
        self.game_endpoints = list(game_endpoints) if game_endpoints is not None else None
        self.token = token
        self.on_listen = on_listen
        self.server: Optional[LearnerServer] = None
        self.launcher: Optional[ActorProcessLauncher] = None
        self._thread: Optional[threading.Thread] = None
        self.name = "processes" if self.game_endpoints is not None else "external"

    @property
    def n_actors(self) -> int:
        if self.game_endpoints is not None:
            return len(self.game_endpoints)
        return self.server.ever_connected if self.server else 0

    @property
    def address(self) -> Tuple[str, int]:
        assert self.server is not None
        return self.server.address

    def start(self, ctx: ActorContext) -> None:
        self.server = LearnerServer(self.listen, ctx, self.token)
        self._thread = threading.Thread(target=self.server.serve_forever, name="learner-server", daemon=True)
        self._thread.start()
        if self.on_listen:
            self.on_listen(self.server.address)
        if self.game_endpoints is not None:
            learner_addr = self.server.address
            if learner_addr[0] in ("0.0.0.0", ""):
                learner_addr = ("127.0.0.1", learner_addr[1])
            self.launcher = ActorProcessLauncher(learner_addr, self.game_endpoints, self.token).start()

    def alive(self) -> bool:
        if self.launcher is not None:
            return self.launcher.any_alive()
        return True  # external: 접속 대기 (무응답 시간은 학습기의 idle_timeout 으로 판단)

    def failures(self) -> List[str]:
        return self.launcher.failures() if self.launcher else []

    def stop(self) -> None:
        if self.launcher is not None:
            self.launcher.stop()
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()

    def describe(self) -> Dict[str, Any]:
        d = super().describe()
        if self.server is not None:
            d["listen"] = "%s:%d" % self.server.address
            d["episodes_by_actor"] = dict(self.server.episodes_by_actor)
        return d
