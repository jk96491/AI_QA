"""실험 스크립트 공통: 인자 파싱, 세션 생성, 규모 프리셋."""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional

from balance_qa.game_api.client import parse_endpoint
from balance_qa.session import QASession

CLASSES = ["warrior", "mage", "archer"]
PERSONAS = ["aggressive", "stable", "efficient"]


@dataclass
class Scale:
    budget: int       # 최적화 예산(판)
    k: int            # 후보당 판수
    eval_n: int       # 평가 판수
    sens_n: int       # 민감도 분석 레벨당 판수


FULL = Scale(budget=3000, k=10, eval_n=300, sens_n=100)
QUICK = Scale(budget=600, k=6, eval_n=60, sens_n=30)


def parse_args(description: str, extra: Optional[Callable[[argparse.ArgumentParser], None]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--workers", type=int, default=4, help="자동 실행할 게임 대역 인스턴스 수")
    p.add_argument("--game", default=None, help="이미 떠 있는 게임 HOST:PORT[,..] (Unity 빌드 등)")
    p.add_argument("--game-cmd", default=None, help="게임 실행 명령 템플릿 ({port} 자동), --workers 개 띄움 (Unity 헤드리스 등)")
    p.add_argument("--quick", action="store_true", help="작은 규모로 빠르게 (동작 확인용)")
    p.add_argument("--out", default="reports")
    p.add_argument("--seed", type=int, default=0)
    if extra:
        extra(p)
    args = p.parse_args()
    args.scale = QUICK if args.quick else FULL
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    return args


def session(args: argparse.Namespace) -> QASession:
    if args.game:
        return QASession(endpoints=[parse_endpoint(e) for e in args.game.split(",") if e.strip()])
    if getattr(args, "game_cmd", None):
        import shlex

        return QASession(game_command=shlex.split(args.game_cmd, posix=False), spawn=args.workers)
    return QASession(spawn_local=args.workers)


def csv_list(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]
