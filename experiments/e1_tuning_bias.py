"""E1 (H1) 튜닝 편차: 손 튜닝 BT 와 동일 예산 최적화 BT 의 직업 비교가 달라지는가.

- 손 튜닝 = 정의서 default (마법사는 의도적으로 덜 다듬은 값)
- 최적화 = 직업별 동일 예산 CMA-ES, 평가 시드로 재측정
"""
from __future__ import annotations

from balance_qa.report.report import ReportBuilder
from balance_qa.report.sections import behavior_table, comparison, summary_table
from experiments.common import CLASSES, parse_args, session


def main() -> None:
    args = parse_args(__doc__, lambda p: p.add_argument("--persona", default="stable"))
    sc = args.scale
    rb = ReportBuilder("E1 튜닝 편차 (%s)" % args.persona, args.out)
    rb.meta(persona=args.persona, budget=sc.budget, k=sc.k, eval_n=sc.eval_n)

    hand, opt = [], []
    with session(args) as s:
        for c in CLASSES:
            hand.append(s.evaluate(c, args.persona, n=sc.eval_n, label="%s 손튜닝" % c))
            out = s.optimize(c, args.persona, budget=sc.budget, k=sc.k, eval_n=sc.eval_n, seed=args.seed, verbose=False)
            out.evaluation.label = "%s 최적화" % c
            opt.append(out.evaluation)
            rb.data("params_%s" % c, out.params)
            print(c, hand[-1].row()["effective_time_s"], "→", opt[-1].row()["effective_time_s"], flush=True)

    summary_table(rb, hand + opt)
    behavior_table(rb, hand + opt)

    def ranking(summ):
        return sorted(summ, key=lambda x: x.effective_time.estimate)

    rb.section("직업 순위 (빠른 순)")
    rb.table(
        ["순위", "손 튜닝", "최적화"],
        [
            [i + 1, "%s %.1fs" % (h.label, h.effective_time.estimate), "%s %.1fs" % (o.label, o.effective_time.estimate)]
            for i, (h, o) in enumerate(zip(ranking(hand), ranking(opt)))
        ],
    )
    spread_h = max(x.effective_time.estimate for x in hand) - min(x.effective_time.estimate for x in hand)
    spread_o = max(x.effective_time.estimate for x in opt) - min(x.effective_time.estimate for x in opt)
    rb.text("- 직업 간 최대 격차: 손 튜닝 %.1fs → 최적화 %.1fs" % (spread_h, spread_o))
    rb.section("직업별 손 튜닝 → 최적화")
    for h, o in zip(hand, opt):
        comparison(rb, o, h)
    print("E1 →", rb.save())


if __name__ == "__main__":
    main()
