"""python -m play_agent <명령>

  check-play  플레이 프로토콜 적합성 + 스크립트 튜토리얼 (LLM 없음)
      --game 127.0.0.1:7800 [--omni ...] [--balance ...] [--game2 ...]   이미 띄운 인스턴스
      --exe unity_game/Build/QaArena.exe                                  헤드리스 인스턴스 4개를 직접 띄움
      [--loadout reports/<run> ...]                                       T9: 학습 결과로 필드 전투
  loadout     학습 결과 → set_loadout 항목 미리 보기  (--loadout reports/<run> ... [--game ...])
  play        LLM 이 튜토리얼을 플레이 (anthropic SDK, Python ≥ 3.10 venv 필요, ANTHROPIC_API_KEY)
      --game ... --loadout ... [--seed 1 --cls warrior --effort low --max-actions 150 --out reports]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

from play_agent.check import Instances, run_all
from play_agent.client import PlayClient
from play_agent.loadout import LoadoutBuilder


def _utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
    except AttributeError:
        pass


def cmd_check(a: argparse.Namespace) -> int:
    inst = None
    game, omni, bal, game2 = a.game, a.omni, a.balance, a.game2
    if a.exe:
        inst = Instances(a.exe)
        print("인스턴스 띄우는 중 (%s)…" % a.exe, flush=True)
        game = inst.start(["-qaPlay"])
        omni = inst.start(["-qaPlay", "-qaPlayOmniscient"])
        game2 = inst.start(["-qaPlay"])
        bal = inst.start([])
        print("  play %s / omni %s / play2 %s / balance %s" % (game, omni, game2, bal), flush=True)
    if not game:
        print("--game 또는 --exe 가 필요함", file=sys.stderr)
        return 2
    try:
        ck = run_all(game, omni, bal, game2, loadout=a.loadout or (), only=a.only)
    finally:
        if inst is not None:
            inst.stop()
    return 0 if ck.passed else 1


def _builder(paths: List[str]) -> LoadoutBuilder:
    lb = LoadoutBuilder()
    for p in paths:
        lb.add_file(p)
    return lb


def cmd_loadout(a: argparse.Namespace) -> int:
    lb = _builder(a.loadout)
    desc = None
    if a.game:
        with PlayClient.connect(a.game) as c:
            c.hello()
            desc = c.describe()
        for p in lb.check_against(desc):
            print("문제:", p)
    for n in lb.notes:
        print("참고:", n)
    print(json.dumps({"type": "set_loadout", "persona": lb.persona(), "entries": lb.wire_entries(desc)}, ensure_ascii=False, indent=2))
    for e in lb.entries.values():
        print("%s/%s ← %s, 트리거 응답: %s" % (e.cls, e.scenario, e.source, "IMPALA 정책 (numpy)" if e.policy else "없음 (고정 params)"))
    return 0


def cmd_play(a: argparse.Namespace) -> int:
    from play_agent.pilot import LlmPilot, PilotConfig   # anthropic 은 run() 안에서 import

    lb = _builder(a.loadout or [])
    cfg = PilotConfig(model=a.model, effort=a.effort, max_actions=a.max_actions, max_calls=a.max_calls)
    with PlayClient.connect(a.game) as c:
        c.hello()
        desc = c.describe()
        problems = lb.check_against(desc)
        if problems:
            print("로드아웃 문제:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 2
        if lb.entries:
            c.set_loadout(lb.wire_entries(desc), persona=lb.persona())
        obs = c.reset(seed=a.seed, cls=a.cls)
        pilot = LlmPilot(c, responder=lb.responder(), config=cfg)
        run = pilot.run(obs)
        log = c.get_log()
        notes = c.notes + lb.notes
    out = Path(a.out) / ("play-" + time.strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    meta = {"game": "%s %s" % (desc.get("game"), desc.get("game_version")), "seed": a.seed, "class": a.cls,
            "model": cfg.model, "effort": cfg.effort, "loadout": [e.source for e in lb.entries.values()], "notes": notes}
    (out / "run.json").write_text(json.dumps(dict(meta, **run.to_dict()), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / "play_log.json").write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")
    done = [e[2].get("quest") for e in log.get("entries", []) if e[1] == "quest_completed"]
    print("끝: %s | 행동 %d, API %d회, %ss | 완료 퀘스트 %s | 전투 %s" % (
        run.end_reason, run.actions, run.api_calls, run.seconds, done,
        ["%s:%s" % (x["enemy"], "승" if x["cleared"] else "패") for x in run.combats]))
    print("토큰:", run.usage)
    if run.finish:
        print("finish:", json.dumps(run.finish, ensure_ascii=False))
    print("기록:", out)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    _utf8()
    ap = argparse.ArgumentParser(prog="python -m play_agent", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check-play", help="플레이 프로토콜 적합성 + 스크립트 튜토리얼")
    p.add_argument("--game")
    p.add_argument("--omni", help="-qaPlayOmniscient 인스턴스")
    p.add_argument("--balance", help="같은 빌드의 밸런스 모드 인스턴스 (T5·T8·T9 비교)")
    p.add_argument("--game2", help="T7 교차 비교용 두 번째 플레이 인스턴스")
    p.add_argument("--exe", help="이 실행 파일로 헤드리스 인스턴스 4개를 띄워서 검사")
    p.add_argument("--loadout", nargs="*", help="T9: reports/<run> 또는 params.json/policy.json")
    p.add_argument("--only", nargs="*", choices=["T2", "T3", "T4", "T56", "T78", "T9"])
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("loadout", help="학습 결과 → set_loadout 미리 보기")
    p.add_argument("--loadout", nargs="+", required=True)
    p.add_argument("--game", help="있으면 play_description 과 맞춰 본다")
    p.set_defaults(fn=cmd_loadout)

    p = sub.add_parser("play", help="LLM 이 튜토리얼을 플레이 (Python ≥ 3.10 + anthropic)")
    p.add_argument("--game", required=True)
    p.add_argument("--loadout", nargs="*")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--cls", default="warrior")
    p.add_argument("--model", default="claude-opus-5-5")
    p.add_argument("--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--max-actions", type=int, default=150)
    p.add_argument("--max-calls", type=int, default=250)
    p.add_argument("--out", default="reports")
    p.set_defaults(fn=cmd_play)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
