"""E2 (H2) 효과 크기: 파라미터 변경 효과 vs 밸런스 패치(보스 체력 ±5% 등) 효과."""
from __future__ import annotations

from balance_qa.analysis.sensitivity import OATSensitivity
from balance_qa.report.report import ReportBuilder
from balance_qa.runner.seed_pool import EVAL_SEEDS
from experiments.common import CLASSES, parse_args, session

PATCHES = ["base", "patch_boss_hp_up5", "patch_boss_hp_down5", "patch_boss_dmg_up10", "patch_boss_fast"]


def main() -> None:
    args = parse_args(__doc__, lambda p: p.add_argument("--persona", default="stable"))
    sc = args.scale
    rb = ReportBuilder("E2 파라미터 효과 vs 패치 효과 (%s)" % args.persona, args.out)
    rb.meta(persona=args.persona, n_per_level=sc.sens_n)
    seeds = EVAL_SEEDS.first(sc.sens_n)

    with session(args) as s:
        sens = OATSensitivity(s.evaluator)
        summary_rows = []
        for c in CLASSES:
            space = s.class_info(c).optimizable_space()
            base = s.base_params(c, args.persona)
            reward = s.reward_fn(args.persona)
            rows = sens.run(c, "base", base, space, reward, seeds)
            patches = sens.patch_effects(c, [p for p in PATCHES if p in s.game.scenarios], base, reward, seeds)

            rb.section("%s: 파라미터별 소요 시간 변화 (OAT, 범위 전체)" % c)
            rb.table(
                ["param", "range(s)", "range(%)", "best", "mean_time by level"],
                [[r.param, r.time_range, r.time_range_pct, r.best_value, r.mean_time] for r in rows],
            )
            rb.section("%s: 패치 효과 (같은 파라미터, 소요 시간 변화율 %%)" % c)
            rb.table(["scenario", "Δtime(%)"], [[k, v] for k, v in patches.items() if k != "base"])
            rb.data("sensitivity_%s" % c, [r.as_dict() for r in rows])
            rb.data("patch_%s" % c, patches)

            top = rows[0]
            hp5 = abs(patches.get("patch_boss_hp_up5", 0.0))
            summary_rows.append([c, top.param, top.time_range_pct, hp5, "예" if top.time_range_pct >= hp5 else "아니오"])
            print(c, "top", top.param, top.time_range_pct, "% vs hp+5%", hp5, flush=True)

    rb.section("요약: 최대 파라미터 효과 ≥ 보스 체력 5% 패치 효과?")
    rb.table(["class", "top param", "param effect(%)", "boss hp +5% effect(%)", "H2 성립"], summary_rows)
    print("E2 →", rb.save())


if __name__ == "__main__":
    main()
