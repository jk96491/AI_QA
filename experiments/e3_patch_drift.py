"""E3 (H3) 패치 노후화: 패치마다 최적 파라미터가 이동하고, 고정된 손 튜닝 값과의 격차가 변하는가."""
from __future__ import annotations

import numpy as np

from balance_qa.report.report import ReportBuilder
from experiments.common import csv_list, parse_args, session

SCENARIOS = ["base", "patch_boss_dmg_up10", "patch_boss_fast", "patch_gimmick_tight"]


def main() -> None:
    def extra(p):
        p.add_argument("--cls", default="warrior")
        p.add_argument("--persona", default="stable")
        p.add_argument("--scenarios", type=csv_list, default=SCENARIOS)

    args = parse_args(__doc__, extra)
    sc = args.scale
    rb = ReportBuilder("E3 패치 노후화 (%s/%s)" % (args.cls, args.persona), args.out)
    rb.meta(budget=sc.budget, eval_n=sc.eval_n, scenarios=args.scenarios)

    rows, params_by = [], {}
    with session(args) as s:
        space = s.class_info(args.cls).optimizable_space()
        for scen in args.scenarios:
            hand = s.evaluate(args.cls, args.persona, n=sc.eval_n, scenario=scen)
            out = s.optimize(args.cls, args.persona, budget=sc.budget, k=sc.k, scenario=scen,
                             eval_n=sc.eval_n, seed=args.seed, verbose=False)
            params_by[scen] = out.params
            gap = hand.effective_time.estimate - out.evaluation.effective_time.estimate
            rows.append([scen, "%.1f" % hand.effective_time.estimate, "%.1f" % out.evaluation.effective_time.estimate,
                         "%.1f (%.1f%%)" % (gap, 100 * gap / out.evaluation.effective_time.estimate)])
            print(scen, rows[-1], flush=True)

    rb.section("시나리오별 손 튜닝 vs 재최적화 소요 시간(s)")
    rb.table(["scenario", "손 튜닝", "재최적화", "격차"], rows)

    rb.section("최적 파라미터 이동 (정규화 [0,1] 기준, base 대비)")
    base_vec = space.encode(params_by[args.scenarios[0]])
    table = []
    for scen in args.scenarios:
        vec = space.encode(params_by[scen])
        table.append([scen] + ["%.3f" % params_by[scen][n] for n in space.names] + ["%.3f" % float(np.linalg.norm(vec - base_vec))])
    rb.table(["scenario"] + space.names + ["‖Δ‖"], table)
    rb.text("주의: 최적화 노이즈만으로도 ‖Δ‖ 가 0 이 아니다. 같은 시나리오를 다른 --seed 로 반복해 노이즈 수준과 비교할 것.")
    rb.data("params_by_scenario", params_by)
    print("E3 →", rb.save())


if __name__ == "__main__":
    main()
