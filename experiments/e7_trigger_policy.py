"""E7 (H7) 결정 트리거 정책: 판당 1회 최적 파라미터 vs 보스 페이즈(75·50·25%) 트리거 정책 (ES / IMPALA).

공정 비교를 위해 정책들은 판당 1회 최적값에서 출발하고(init_params), 같은 추가 예산(판수)을 쓴다.
- 판당1회(+추가예산) : CMA-ES 를 같은 예산만큼 더 돌린 것 (추가 예산 효과 통제)
- 트리거정책(ES)     : MLP + OpenAI-ES
- 트리거정책(IMPALA) : Actor-Critic + V-trace, 액터 = 게임 인스턴스
"""
from __future__ import annotations

from balance_qa.report.report import ReportBuilder
from balance_qa.report.sections import behavior_table, comparison, summary_table
from experiments.common import csv_list, parse_args, session


def main() -> None:
    def extra(p):
        p.add_argument("--classes", type=csv_list, default=["warrior", "mage"])
        p.add_argument("--persona", default="stable")
        p.add_argument("--no-es", action="store_true", help="ES 정책 생략")
        p.add_argument("--no-impala", action="store_true", help="IMPALA 생략")

    args = parse_args(__doc__, extra)
    sc = args.scale
    rb = ReportBuilder("E7 트리거 정책 vs 판당 1회 (%s)" % args.persona, args.out)
    rb.meta(budget=sc.budget, eval_n=sc.eval_n)
    with session(args) as s:
        rb.meta(game="%s %s" % (s.game.game, s.game.game_version), actors=s.pool.size)
        for c in args.classes:
            static = s.optimize(c, args.persona, budget=sc.budget, k=sc.k, eval_n=sc.eval_n, seed=args.seed, verbose=False)
            static.evaluation.label = "%s 판당1회" % c
            more = s.optimize(c, args.persona, budget=sc.budget, k=sc.k, eval_n=sc.eval_n, seed=args.seed + 1,
                              fixed_overrides=static.params, verbose=False)
            more.evaluation.label = "%s 판당1회(+추가예산)" % c
            rows = [static.evaluation, more.evaluation]
            curves = []
            if not args.no_es:
                pol = s.train_policy(c, args.persona, budget=sc.budget, k=max(4, sc.k // 2), eval_n=sc.eval_n,
                                     init_params=static.params, seed=args.seed, verbose=False)
                pol.evaluation.label = "%s 트리거정책(ES)" % c
                rows.append(pol.evaluation)
                curves.append(("%s ES 세대 평균 보상" % c, [h.gen_mean_reward for h in pol.training.history]))
            if not args.no_impala:
                imp = s.train_impala(c, args.persona, budget=sc.budget, eval_n=sc.eval_n, init_params=static.params,
                                     seed=args.seed, verbose=False)
                imp.evaluation.label = "%s 트리거정책(IMPALA)" % c
                rows.append(imp.evaluation)
                curves.append(("%s IMPALA 평균 return" % c, [h.gen_mean_reward for h in imp.training.history]))
            summary_table(rb, rows, "%s 결과" % c)
            behavior_table(rb, rows)
            rb.section("%s 비교 (추가 예산 통제)" % c)
            for r in rows[2:]:
                comparison(rb, r, more.evaluation)
            for label, ys in curves:
                rb.curve(label, ys)
            for r in rows:
                print(r.row(), flush=True)
    print("E7 →", rb.save())


if __name__ == "__main__":
    main()
