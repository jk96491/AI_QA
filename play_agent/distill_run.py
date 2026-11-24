"""증류 후반 단계 실행 (QaArena) — SDK btqa_play/btqa_distill 에 QaArena 전처리·로드아웃·보상을 붙인다.

    # DPO 쌍: 교정 기록 → 쌍 (+ chosen thought 에 상황 읽기 접두)
    venv\\Scripts\\python.exe -m play_agent.distill_run pairs reports/distill/dagger.jsonl --out distill_out/data/pairs_v1.jsonl
    # RFT (GPU, 게임 2개: main·scratch)
    venv_distill\\Scripts\\python.exe -m play_agent.distill_run rft --base distill_out/r4/merged --game 127.0.0.1:7801 \\
        --scratch 127.0.0.1:7802 --seeds 11 12 --out distill_out/r5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from play_agent import QA_ARENA_SPEC
from play_agent.distill_prep import situation

LOADOUT = "reports/20261123-230419"


def cmd_pairs(a: argparse.Namespace) -> int:
    from btqa_play.actions import action_text
    from btqa_play.dataset import build_pairs
    st = build_pairs(a.inputs, a.out)
    rows = [json.loads(x) for x in Path(a.out).read_text(encoding="utf-8").splitlines() if x.strip()]
    for r in rows:   # SFT(v3)와 같은 thought 형식: chosen 앞에 상황 읽기
        c = json.loads(r["chosen"])
        if not c["thought"].startswith("상황:"):
            c["thought"] = "%s → %s" % (situation(r["prompt"][1]["content"]), c["thought"])
        r["chosen"] = action_text(c["thought"], c["tool"], c["input"])
    Path(a.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(json.dumps(st, ensure_ascii=False))
    return 0


def prepare(client, desc):
    from play_agent.loadout import LoadoutBuilder
    lb = LoadoutBuilder()
    lb.add_file(LOADOUT)
    if not lb.check_against(desc):
        client.set_loadout(lb.wire_entries(desc), persona=lb.persona())
    return lb.responder()


def cmd_rft(a: argparse.Namespace) -> int:
    from btqa_distill.rft import train_rft
    from play_agent.distill_reward import reward
    print(train_rft(a.base, a.game, a.scratch, a.seeds, reward, a.out, prepare=prepare, spec=str(QA_ARENA_SPEC),
                    cls=a.cls, k=a.k, max_steps=a.max_steps, lr=a.lr, kl_coef=a.kl))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="python -m play_agent.distill_run")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pairs")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_pairs)
    p = sub.add_parser("rft")
    p.add_argument("--base", required=True)
    p.add_argument("--game", required=True)
    p.add_argument("--scratch", required=True)
    p.add_argument("--seeds", type=int, nargs="+", default=[11, 12])
    p.add_argument("--cls", default="warrior")
    p.add_argument("--k", type=int, default=4)
    p.add_argument("--max-steps", type=int, default=45)
    p.add_argument("--lr", type=float, default=1e-5)
    p.add_argument("--kl", type=float, default=0.05)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_rft)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
