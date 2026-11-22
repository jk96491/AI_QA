"""게임 인스턴스 실행기.

- LocalSimLauncher   : 파이썬 게임 대역(`python -m game_sim serve`)을 N개 띄움 (개발용)
- CommandLauncher    : 임의 명령 템플릿으로 N개 띄움 (Unity 헤드리스 빌드 등)
    예) ["MyGame.exe", "-batchmode", "-nographics", "-qaPort", "{port}"]
    view=K 를 주면 앞의 K개는 **화면(창) 모드**로 띄운다 (전투 뷰어로 학습 판을 보기 위함, 나머지는 헤드리스)

학습 쪽은 게임 패키지를 import 하지 않는다. 프로세스를 띄우고 포트로 접속할 뿐이다.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

#: 화면 모드 명령을 만들 때 헤드리스 명령에서 빼는 인자
HEADLESS_FLAGS = ("-batchmode", "-nographics")
#: 화면 모드에 붙이는 Unity 플레이어 창 인자
WINDOW_FLAGS = ("-screen-fullscreen", "0", "-screen-width", "1280", "-screen-height", "720")
#: 화면 모드 뷰어 인자 (QaArena, unity_game/VIEWER_REQUEST.md 반영분): 학습 판 자동 따라보기 + 8배속
VIEWER_FLAGS = ("-qaFollow", "-qaViewSpeed", "8")


def view_command_from(headless: Sequence[str], size: Optional[Tuple[int, int]] = None) -> List[str]:
    """헤드리스 명령 템플릿 → 화면(창) 모드 명령 (-batchmode/-nographics 제거 + 창 크기)."""
    out = [part for part in headless if part.lower() not in HEADLESS_FLAGS]
    lowered = [p.lower() for p in out]
    if "-screen-fullscreen" not in lowered:
        w, h = size or (1280, 720)
        out += ["-screen-fullscreen", "0", "-screen-width", str(w), "-screen-height", str(h)]
    if "-qafollow" not in lowered:
        out += list(VIEWER_FLAGS)
    return out


def free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def wait_for_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


class CommandLauncher:
    def __init__(
        self,
        command: Sequence[str],
        n: int,
        host: str = "127.0.0.1",
        ports: Optional[Sequence[int]] = None,
        startup_timeout: float = 60.0,
        cwd: Optional[Path] = None,
        env: Optional[dict] = None,
        view: int = 0,
        view_command: Optional[Sequence[str]] = None,
    ) -> None:
        self.command = list(command)
        self.n = n
        self.view = max(0, min(int(view), n))
        self.view_command = list(view_command) if view_command else view_command_from(self.command)
        self.host = host
        self.ports: List[int] = list(ports) if ports else [free_port(host) for _ in range(n)]
        self.startup_timeout = startup_timeout
        self.cwd = cwd
        self.env = env
        self.procs: List[subprocess.Popen] = []
        self._logs: list = []

    @property
    def endpoints(self) -> List[Tuple[str, int]]:
        return [(self.host, p) for p in self.ports]

    @property
    def view_endpoints(self) -> List[Tuple[str, int]]:
        """화면 모드로 띄운 인스턴스 (endpoints 의 앞쪽)."""
        return self.endpoints[: self.view]

    def _executable(self, command: Optional[Sequence[str]] = None) -> str:
        """실행 파일 경로를 절대 경로로. Windows 는 '/' 가 섞인 상대 경로 실행 파일을 찾지 못한다.

        상대 경로는 작업 폴더(cwd) → 프로젝트 루트(AI_QA) 순서로 찾는다.
        """
        exe = (command or self.command)[0].strip('"')
        p = Path(exe)
        if p.is_absolute():
            return str(p)
        for base in (Path(self.cwd) if self.cwd else Path.cwd(), PROJECT_ROOT):
            cand = (base / p).resolve()
            if cand.exists():
                return str(cand)
        return exe  # PATH 에서 찾는 명령 (예: python)

    def _cmd(self, port: int, index: int = 0) -> List[str]:
        command = self.view_command if index < self.view else self.command
        parts = [self._executable(command)] + list(command[1:])
        return [part.replace("{port}", str(port)).replace("{host}", self.host) for part in parts]

    def start(self) -> "CommandLauncher":
        for index, port in enumerate(self.ports):
            log = tempfile.TemporaryFile()  # stderr 를 파이프로 받으면 버퍼가 차서 게임이 멈출 수 있음
            self._logs.append(log)
            self.procs.append(
                subprocess.Popen(
                    self._cmd(port, index), cwd=str(self.cwd) if self.cwd else None, env=self.env,
                    stdout=subprocess.DEVNULL, stderr=log,
                )
            )
        for port, proc, log in zip(self.ports, self.procs, self._logs):
            if not wait_for_port(self.host, port, self.startup_timeout):
                log.seek(0)
                err = log.read()
                self.stop()
                raise RuntimeError("게임 인스턴스(port %d) 기동 실패: %s" % (port, err.decode("utf-8", "replace")[-500:]))
        return self

    def stop(self) -> None:
        for proc in self.procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in self.procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.procs = []
        for log in self._logs:
            log.close()
        self._logs = []

    def __enter__(self) -> "CommandLauncher":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


class LocalSimLauncher(CommandLauncher):
    """파이썬 게임 대역 서버 N개."""

    def __init__(self, n: int, host: str = "127.0.0.1", startup_timeout: float = 60.0) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        super().__init__(
            [sys.executable, "-m", "game_sim", "serve", "--host", "{host}", "--port", "{port}"],
            n, host=host, startup_timeout=startup_timeout, cwd=PROJECT_ROOT, env=env,
        )
