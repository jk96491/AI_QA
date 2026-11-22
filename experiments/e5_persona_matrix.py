"""E5 (H5) 페르소나 × 직업 매트릭스: 같은 BT 에 페르소나별 최적 파라미터를 학습해 클리어 시간·사망·행동 분포 비교."""
from __future__ import annotations

from balance_qa.report.report import ReportBuilder
from balance_qa.report.sections import behavior_table, summary_table
from experiments.common import CLASSES, PERSONAS, parse_args, session


def main() -> None:
    args = parse_args(__doc__)
    sc = args.scale
    rb = ReportBuilder("E5 페르소나 × 직업 매트릭스", args.out)
    rb.meta(budget=sc.budget, k=sc.k, eval_n=sc.eval_n)
    results = {}
    with session(args) as s:
        for c in CLASSES:
            for p in PERSONAS:
                out = s.optimize(c, p, budget=sc.budget, k=sc.k, eval_n=sc.eval_n, seed=args.seed, verbose=False)
                out.evaluation.label = "%s/%s" % (c, p)
                results[(c, p)] = out
                print(out.evaluation.row(), flush=True)

    rb.section("클리어 시간 매트릭스 (effective, 초)")
    rb.table(["class \\ persona"] + PERSONAS,
             [[c] + ["%.1f" % results[(c, p)].evaluation.effective_time.estimate for p in PERSONAS] for c in CLASSES])
    rb.section("사망 수 매트릭스")
    rb.table(["class \\ persona"] + PERSONAS,
             [[c] + ["%.2f" % results[(c, p)].evaluation.deaths.estimate for p in PERSONAS] for c in CLASSES])
    rb.section("소모품 사용 매트릭스")
    rb.table(["class \\ persona"] + PERSONAS,
             [[c] + ["%.2f" % results[(c, p)].evaluation.consumables.estimate for p in PERSONAS] for c in CLASSES])
    evals = [results[k].evaluation for k in results]
    summary_table(rb, evals)
    behavior_table(rb, evals)
    rb.data("params", {"%s/%s" % k: v.params for k, v in results.items()})
    print("E5 →", rb.save())


if __name__ == "__main__":
    main()
