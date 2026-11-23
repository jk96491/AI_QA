"""E8 컨텍스트 밴딧 (docs/BANDIT_IMPALA_DESIGN.md 6장): 판 시작 상황마다 다른 가중치가 이득인가, IMPALA 가 그것을 싸게 배우는가.

컨텍스트 칸 = (직업, 시나리오) × 판 시작 상태(프로토콜 v1.4 initial_state, 예: 물약 0/⅓/⅔/1 × 체력). 모든 방법을 같은 평가 시드로 칸마다 평가 (짝지은 비교).

| 방법 | 학습 판 분포 | 판 수 |
|---|---|---|
| 손튜닝        | 정의서 default (학습 없음)                          | 0 |
| CMA-가득      | 가득 찬 시작에서만 (지금까지의 표준 최적화)           | B |
| CMA-전역      | 밴딧과 같은 시작 상태 분포, 가중치 하나              | B |
| CMA-칸별(상한) | 평가 칸마다 따로 (사실상 최적치)                      | 칸 수 × B_cell |
| IMPALA 밴딧   | 같은 분포, 정책 하나 (컨텍스트 → 가중치)              | B |

--holdout 이름=값 으로 그 시작 상태를 학습 분포에서 빼면 그 칸은 '미학습' 일반화 칸이 된다 (CMA-칸별은 그 칸도 직접 학습).
결론을 내기 전에 /bt-sim-balance-review 로 점검한다 (단일 실행, 칸별 CI 확인).

    python -m experiments.e8_bandit --workers 8 --game-cmd "unity_game/Build/QaArena.exe -batchmode -nographics -qaPort {port}" \\
        --combos warrior:forest_wolf_king --quick
"""
from __future__ import annotations

import json
import time
from typing import Dict, List, Mapping, Optional, Tuple

import numpy as np

from balance_qa.control.param_source import StaticParamSource
from balance_qa.report.report import ReportBuilder
from balance_qa.rl.bandit import ContextCell
from experiments.common import parse_args, session


def _levels(items: Optional[List[str]]) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    for it in items or []:
        name, _, vals = it.partition("=")
        out[name.strip()] = [float(v) for v in vals.split(",") if v.strip()]
    return out


def _combos(items: List[str]) -> List[Tuple[str, str]]:
    return [(c.partition(":")[0], c.partition(":")[2] or "base") for c in items]


def main() -> None:
    def extra(p):
        p.add_argument("--combos", nargs="+", default=["warrior:forest_wolf_king"], help="class:scenario …")
        p.add_argument("--persona", default="stable")
        p.add_argument("--levels", nargs="*", default=["potions_ratio=0,0.333,0.667,1"],
                       help="학습 시작 상태 단계 (이름=값,…). 없는 키는 범위 균등")
        p.add_argument("--eval-levels", nargs="*", default=["potions_ratio=0,0.333,0.667,1", "hp_ratio=1,0.5"],
                       help="평가 격자 (이름=값,…)")
        p.add_argument("--holdout", nargs="*", default=[], help="학습 분포에서 뺄 값 (이름=값). 그 칸 = 미학습")
        p.add_argument("--p-full", type=float, default=0.25)
        p.add_argument("--budget", type=int, default=None, help="CMA-가득·CMA-전역·밴딧 판 수 (기본: 규모 프리셋)")
        p.add_argument("--cell-budget", type=int, default=None, help="CMA-칸별 칸당 판 수 (기본: budget/2)")
        p.add_argument("--no-cell", action="store_true", help="CMA-칸별(비쌈) 생략")
        p.add_argument("--batch", type=int, default=32)

    args = parse_args(__doc__, extra)
    sc = args.scale
    budget = args.budget or (sc.budget * 2)
    cell_budget = args.cell_budget or max(120, budget // 2)
    eval_n = sc.eval_n
    train_levels = _levels(args.levels)
    holdout = _levels(args.holdout)
    for name, vals in holdout.items():
        if name in train_levels:
            train_levels[name] = [v for v in train_levels[name] if all(abs(v - h) > 1e-6 for h in vals)]
    eval_levels = _levels(args.eval_levels)
    combos = _combos(args.combos)
    pid = args.persona

    rb = ReportBuilder("E8 컨텍스트 밴딧 (%s, %s)" % ("+".join("%s:%s" % c for c in combos), pid), args.out)
    rb.meta(budget=budget, cell_budget=cell_budget, eval_n=eval_n, p_full=args.p_full, levels=train_levels,
            eval_levels=eval_levels, holdout=holdout)
    t0 = time.time()
    with session(args) as s:
        rb.meta(game="%s %s" % (s.game.game, s.game.game_version), protocol=s.game.protocol_version, actors=s.pool.size,
                initial_state=[x.name for x in s.game.initial_state])
        if not s.game.initial_state:
            raise SystemExit("게임이 describe.initial_state 를 선언하지 않음 (프로토콜 v1.4 필요) — E8 은 시작 상태가 있어야 의미가 있다")
        setup = s.bandit_setup(combos, pid, p_full=args.p_full, levels=train_levels)
        cells = setup.cells_grid(eval_levels)

        def is_holdout(cell: ContextCell) -> bool:
            st = cell.state_dict() or {}
            return any(any(abs(st.get(k, -9) - h) < 1e-6 for h in vs) for k, vs in holdout.items())

        results: Dict[str, Dict[ContextCell, object]] = {}
        weights: Dict[str, Dict[ContextCell, Dict[str, float]]] = {}
        budgets: Dict[str, int] = {}

        def put(method: str, cell: ContextCell, summary, w: Mapping[str, float]) -> None:
            results.setdefault(method, {})[cell] = summary
            weights.setdefault(method, {})[cell] = dict(w)

        # 1) 손튜닝
        for cell in cells:
            p = s.base_params(cell.class_name, pid)
            put("손튜닝", cell, s.evaluate(cell.class_name, pid, n=eval_n, scenario=cell.scenario, label="손튜닝",
                                         initial_state=cell.state_dict()), {k: p[k] for k in s.class_info(cell.class_name).weight_names})
        budgets["손튜닝"] = 0
        print("손튜닝 끝 (%.0fs)" % (time.time() - t0), flush=True)

        for cls, scen in combos:
            mine = [c for c in cells if (c.class_name, c.scenario) == (cls, scen)]
            names = s.class_info(cls).weight_names
            # 2) CMA-가득
            full = s.optimize(cls, pid, budget=budget, k=sc.k, scenario=scen, seed=args.seed, eval_n=1, verbose=False)
            for cell in mine:
                put("CMA-가득", cell, s.evaluate(cls, pid, params=full.params, n=eval_n, scenario=scen, label="CMA-가득",
                                               initial_state=cell.state_dict()), {k: full.params[k] for k in names})
            # 3) CMA-전역 (밴딧과 같은 분포, 이 조합만)
            sampler = setup.sampler

            def state_fn(seed: int, _c=(cls, scen)) -> Optional[Dict[str, float]]:
                rng = np.random.default_rng([args.seed + 7, int(seed)])
                for _ in range(64):   # 이 조합이 나올 때까지 (조합 여러 개일 때)
                    cell = sampler.sample(rng)
                    if (cell.class_name, cell.scenario) == _c:
                        return cell.state_dict()
                return None

            glob = s.optimize(cls, pid, budget=budget, k=sc.k, scenario=scen, seed=args.seed, eval_n=1,
                              initial_state_fn=state_fn, verbose=False)
            for cell in mine:
                put("CMA-전역", cell, s.evaluate(cls, pid, params=glob.params, n=eval_n, scenario=scen, label="CMA-전역",
                                               initial_state=cell.state_dict()), {k: glob.params[k] for k in names})
            print("%s/%s CMA-가득·전역 끝 (%.0fs)" % (cls, scen, time.time() - t0), flush=True)
            # 4) CMA-칸별
            if not args.no_cell:
                for cell in mine:
                    o = s.optimize(cls, pid, budget=cell_budget, k=sc.k, scenario=scen, seed=args.seed, eval_n=eval_n,
                                   initial_state=cell.state_dict(), verbose=False)
                    put("CMA-칸별", cell, o.evaluation, {k: o.params[k] for k in names})
                print("%s/%s CMA-칸별 %d칸 끝 (%.0fs)" % (cls, scen, len(mine), time.time() - t0), flush=True)
        budgets["CMA-가득"] = budgets["CMA-전역"] = budget * len(combos)
        if not args.no_cell:
            budgets["CMA-칸별"] = cell_budget * len(cells)

        # 5) IMPALA 밴딧 (모든 조합을 정책 하나로)
        b = s.train_bandit(combos, pid, budget=budget * len(combos), batch_size=args.batch, p_full=args.p_full,
                           levels=train_levels, seed=args.seed, eval_n=0, verbose=True)
        for cell in cells:
            src = b.trainer.bandit_source(cell)
            put("IMPALA 밴딧", cell, s.evaluate(cell.class_name, pid, n=eval_n, scenario=cell.scenario, source=src,
                                              label="IMPALA 밴딧", initial_state=cell.state_dict()), src.weights)
        budgets["IMPALA 밴딧"] = budget * len(combos)
        print("밴딧 끝 (%.0fs)" % (time.time() - t0), flush=True)

        methods = [m for m in ("손튜닝", "CMA-가득", "CMA-전역", "CMA-칸별", "IMPALA 밴딧") if m in results]
        # 칸별 표
        rb.section("칸별 보상 (평가 시드 %d판, 평균 [95%% CI]; 클리어율)" % eval_n)
        rows = []
        for cell in cells:
            row = [cell.label + (" (미학습)" if is_holdout(cell) else "")]
            for m in methods:
                ev = results[m][cell]
                row.append("%s / %s" % (ev.reward.fmt(2), ev.clear_rate.fmt(2)))
            rows.append(row)
        rb.table(["칸"] + methods, rows)

        # 요약: 칸 평균 보상, CMA-칸별 대비 달성률
        rb.section("요약 (칸 평균)")
        ref = "CMA-칸별" if "CMA-칸별" in results else None
        srows, summary = [], {}
        hand = results["손튜닝"]
        for m in methods:
            rs = [results[m][c].reward.estimate for c in cells]
            clr = [results[m][c].clear_rate.estimate for c in cells]
            rec = {"reward_mean": float(np.mean(rs)), "clear_mean": float(np.mean(clr)), "budget": budgets.get(m)}
            if ref:
                gaps = []
                for c in cells:   # (방법 − 손튜닝) / (칸별 − 손튜닝): 칸별 최적화가 얻은 개선 중 몇 % 를 얻었나
                    denom = results[ref][c].reward.estimate - hand[c].reward.estimate
                    if abs(denom) > 1e-6:
                        gaps.append((results[m][c].reward.estimate - hand[c].reward.estimate) / denom)
                rec["share_of_cell_gain"] = float(np.median(gaps)) if gaps else None
            ho = [results[m][c].reward.estimate for c in cells if is_holdout(c)]
            rec["holdout_reward_mean"] = float(np.mean(ho)) if ho else None
            summary[m] = rec
            srows.append([m, "%.2f" % rec["reward_mean"], "%.2f" % rec["clear_mean"],
                          "-" if rec.get("share_of_cell_gain") is None else "%.0f%%" % (100 * rec["share_of_cell_gain"]),
                          "-" if rec["holdout_reward_mean"] is None else "%.2f" % rec["holdout_reward_mean"],
                          rec["budget"]])
        rb.table(["방법", "칸 평균 보상", "칸 평균 클리어", "칸별 개선 중 얻은 몫(중앙값)", "미학습 칸 보상", "학습 판 수"], srows)

        rb.section("칸별 가중치")
        wnames = s.class_info(combos[0][0]).weight_names
        rb.table(["칸"] + methods, [[c.label] + [" ".join("%.2f" % weights[m][c][n] for n in wnames) for m in methods]
                                   for c in cells])
        rb.text("가중치 순서: %s" % ", ".join(wnames))
        rb.text("판정 기준(설계 6장 초안): IMPALA 밴딧이 같은 판 수의 CMA-전역을 유의하게 이기고, CMA-칸별 개선의 90%% 이상. "
                "아니면 'CMA 로 충분'. 단일 실행 — 결론 전 /bt-sim-balance-review.")
        path = rb.save()
        (path / "summary_e8.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        b.outcome.save_params(path / "policy.json", s.game)
    for m, rec in summary.items():
        print("%-12s %s" % (m, rec), flush=True)
    print("E8 → %s (%.0fs)" % (path, time.time() - t0))


if __name__ == "__main__":
    main()
