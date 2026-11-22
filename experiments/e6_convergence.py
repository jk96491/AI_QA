"""E6 (H6) 수렴 비용: 무작위 탐색 vs CMA-ES — 예산(판수)별 평가 성능."""
from __future__ import annotations

from balance_qa.report.report import ReportBuilder
from experiments.common import csv_list, parse_args, session


def main() -> None:
    def extra(p):
        p.add_argument("--cls", default="mage")
        p.add_argument("--persona", default="stable")
        p.add_argument("--budgets", type=lambda v: [int(x) for x in csv_list(v)], default=[300, 900, 2700])
        p.add_argument("--repeats", type=int, default=3)

    args = parse_args(__doc__, extra)
    sc = args.scale
    budgets = args.budgets if not args.quick else [120, 360]
    repeats = args.repeats if not args.quick else 1
    rb = ReportBuilder("E6 수렴 비용 (%s/%s)" % (args.cls, args.persona), args.out)
    rb.meta(budgets=budgets, repeats=repeats, k=sc.k, eval_n=sc.eval_n)

    rows = []
    with session(args) as s:
        hand = s.evaluate(args.cls, args.persona, n=sc.eval_n)
        rows.append(["손 튜닝", "-", "-", "%.3f" % hand.reward.estimate, "%.1f" % hand.effective_time.estimate])
        for method in ("random", "cma"):
            for b in budgets:
                rewards, times = [], []
                for r in range(repeats):
                    out = s.optimize(args.cls, args.persona, method=method, budget=b, k=sc.k,
                                     eval_n=sc.eval_n, seed=args.seed + r, verbose=False)
                    rewards.append(out.evaluation.reward.estimate)
                    times.append(out.evaluation.effective_time.estimate)
                rows.append([method, b, repeats, "%.3f ± %.3f" % (sum(rewards) / len(rewards), max(rewards) - min(rewards)),
                             "%.1f" % (sum(times) / len(times))])
                print(rows[-1], flush=True)
    rb.section("예산별 평가 성능 (평가 시드, 반복 평균 ± 범위)")
    rb.table(["method", "budget(판)", "repeats", "reward", "effective_time(s)"], rows)
    print("E6 →", rb.save())


if __name__ == "__main__":
    main()
