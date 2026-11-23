"""E4 (H4) 밸런스 붕괴 탐색: 기획 의도 범위(정의서 range) 안에서 클리어 시간만 최소화.

speedrun 페르소나(λ=0) 로 최적화하고, 손 튜닝 대비 단축률이 임계값(기본 15%)을 넘으면 '붕괴 후보'로 표시.
범위 끝에 붙은 파라미터도 함께 보고한다 (범위 설정이 결과를 만든 것인지 확인용).
"""
from __future__ import annotations

from balance_qa.report.report import ReportBuilder
from balance_qa.report.sections import summary_table
from experiments.common import CLASSES, parse_args, session


def main() -> None:
    args = parse_args(__doc__, lambda p: p.add_argument("--threshold", type=float, default=0.15))
    sc = args.scale
    rb = ReportBuilder("E4 밸런스 붕괴 후보 탐색", args.out)
    rb.meta(budget=sc.budget, threshold=args.threshold)
    rows, summaries = [], []
    with session(args) as s:
        for c in CLASSES:
            info = s.class_info(c)
            hand = s.evaluate(c, "speedrun", n=sc.eval_n, label="%s 손튜닝" % c)
            out = s.optimize(c, "speedrun", budget=sc.budget, k=sc.k, eval_n=sc.eval_n, seed=args.seed, verbose=False)
            out.evaluation.label = "%s 최속" % c
            summaries += [hand, out.evaluation]
            cut = 1 - out.evaluation.effective_time.estimate / hand.effective_time.estimate
            edge = [
                n for n, d in info.params.items()
                if info.is_weight(n) and min(abs(out.params[n] - d.low), abs(out.params[n] - d.high)) < 0.02 * d.span
            ]
            rows.append([c, "%.1f" % hand.effective_time.estimate, "%.1f" % out.evaluation.effective_time.estimate,
                         "%.1f%%" % (100 * cut), "붕괴 후보" if cut >= args.threshold else "-", ", ".join(edge) or "-"])
            rb.data("params_%s" % c, out.params)
            print(rows[-1], flush=True)
    summary_table(rb, summaries)
    rb.section("결과")
    rb.table(["class", "손 튜닝(s)", "최속(s)", "단축", "판정", "범위 끝 파라미터"], rows)
    print("E4 →", rb.save())


if __name__ == "__main__":
    main()
