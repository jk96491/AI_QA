"""PyCharm 실행 스크립트 공통 준비.

- 프로젝트 루트(AI_QA)를 import 경로와 작업 폴더로 설정 (어디서 실행해도 reports/ 가 루트에 생김)
- 콘솔 출력 UTF-8
- CLI(balance_qa.cli) 를 인자 목록으로 호출
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent


def setup() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.chdir(str(ROOT))
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


#: Unity 빌드 헤드리스 실행 템플릿 (GAME_CMD = UNITY 로 쓰면 됨)
UNITY = "unity_game/Build/QaArena.exe -batchmode -nographics -qaPort {port}"


def connection_args(game: Optional[str], workers: int, game_cmd: Optional[str] = None, view: int = 0) -> List[str]:
    """게임 연결 옵션: game 이 있으면 접속, game_cmd 가 있으면 명령으로 실행, 없으면 파이썬 게임 대역 workers 개.

    view: game_cmd 로 띄우는 인스턴스 중 앞의 N개를 화면(창) 모드로 (Unity 전투 뷰어).
    """
    if game:
        return ["--game", game]
    if game_cmd:
        return ["--workers", str(workers), "--game-cmd", game_cmd] + (["--view", str(view)] if view else [])
    return ["--workers", str(workers)]


def run_cli(argv: Sequence[str]) -> None:
    setup()
    from balance_qa.cli import main

    print("$ python -m balance_qa " + " ".join(argv), flush=True)
    main(list(argv))


def run_module(module: str, argv: Sequence[str]) -> None:
    """python -m <module> <argv> 와 같게 실행 (experiments 용)."""
    setup()
    print("$ python -m %s %s" % (module, " ".join(argv)), flush=True)
    sys.argv = [module] + list(argv)
    runpy.run_module(module, run_name="__main__", alter_sys=True)


def opt(flag: str, value) -> List[str]:
    """값이 None/빈 값이면 생략하는 옵션."""
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, (list, tuple)):
        return [flag] + [str(v) for v in value]
    return [flag, str(value)]
