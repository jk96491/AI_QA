"""[PyCharm ▶] 새 Unity 빌드 측정 — "빌드 끝났어, 측정해줘" 를 한 번에.

1) 프로토콜 적합성 (check-game)
2) 손 튜닝 기준선: CLASSES × PERSONAS (클리어율·소요·멈춤·사망)
3) 학습 후: CMA-ES (LEARN_CLASSES) + IMPALA (IMPALA_CLASS)
4) 결과 표 → 콘솔 + reports/<run_id>/report.md  (docs/STATUS.md 의 '빌드별 측정 이력' 에 옮겨 적는다)
"""
import shlex
import time

from _bootstrap import UNITY, setup

# ===================== 설정 =====================
GAME_CMD = UNITY                     # 측정할 빌드 (헤드리스)
WORKERS = 4                          # 인스턴스 수 = 병렬 판 수 = IMPALA 액터 수
CLASSES = ["warrior", "mage", "archer"]
PERSONAS = ["stable", "aggressive"]
BASE_N = 200                         # 기준선 판수
LEARN_CLASSES = ["warrior", "mage"]  # CMA-ES 로 학습해 볼 직업
LEARN_PERSONA = "stable"
CMA_BUDGET = 3000
IMPALA_CLASS = "warrior"             # None 이면 IMPALA 생략
IMPALA_BUDGET = 8000
EVAL_N = 300
# ================================================


def main() -> int:
    setup()
    from balance_qa.game_api.client import GameClient
    from balance_qa.game_api.conformance import ConformanceChecker
    from balance_qa.game_api.launcher import CommandLauncher
    from balance_qa.report.report import ReportBuilder
    from balance_qa.report.sections import behavior_table, summary_table
    from balance_qa.session import QASession

    cmd = shlex.split(GAME_CMD, posix=False)
    t0 = time.time()

    # 1) 적합성
    launcher = CommandLauncher(cmd, 1).start()
    client = GameClient(*launcher.endpoints[0])
    try:
        checker = ConformanceChecker(client)
        results = checker.run()
    finally:
        client.close()
        launcher.stop()
    bad = [r.line() for r in results if not r.passed]
    print("적합성: %s (%d개)%s" % ("PASS" if checker.passed else "FAIL", len(results),
                                  "" if not bad else "\n  " + "\n  ".join(bad)), flush=True)

    rows, summaries = [], []
    with QASession(game_command=cmd, spawn=WORKERS) as s:
        game = "%s %s" % (s.game.game, s.game.game_version)
        print("게임: %s, 인스턴스 %d" % (game, s.pool.size), flush=True)

        def add(label, summ):
            summ.label = label
            summaries.append(summ)
            r = summ.row()
            rows.append([label, r["clear_rate"], r["effective_time_s"], r["stalled"], r["deaths"], r["reward"]])
            print("  %-28s 클리어 %-18s 소요 %-22s 멈춤 %-16s 사망 %s" % (
                label, r["clear_rate"], r["effective_time_s"], r["stalled"], r["deaths"]), flush=True)

        print("\n[손 튜닝 기준선]", flush=True)
        for c in CLASSES:
            for p in PERSONAS:
                add("%s/%s 손튜닝" % (c, p), s.evaluate(c, p, n=BASE_N))

        print("\n[학습 후]", flush=True)
        for c in LEARN_CLASSES:
            out = s.optimize(c, LEARN_PERSONA, budget=CMA_BUDGET, eval_n=EVAL_N, verbose=False)
            add("%s/%s CMA-ES %d판" % (c, LEARN_PERSONA, CMA_BUDGET), out.evaluation)
        if IMPALA_CLASS:
            out = s.train_impala(IMPALA_CLASS, LEARN_PERSONA, budget=IMPALA_BUDGET, eval_n=EVAL_N, verbose=False)
            add("%s/%s IMPALA %d판" % (IMPALA_CLASS, LEARN_PERSONA, IMPALA_BUDGET), out.evaluation)

    rb = ReportBuilder("빌드 측정: %s" % game, "reports")
    rb.meta(game=game, conformance="PASS" if checker.passed else "FAIL", workers=WORKERS,
            cma_budget=CMA_BUDGET, impala_budget=IMPALA_BUDGET)
    rb.section("요약 (평균 [95% CI])")
    rb.table(["조건", "클리어율", "소요(s, 중도절단)", "멈춘 판", "사망", "보상"], rows)
    if bad:
        rb.section("적합성 실패·경고")
        rb.text("\n".join("- " + b for b in bad))
    summary_table(rb, summaries, "상세")
    behavior_table(rb, summaries)
    print("\n리포트: %s  (%.0f초)" % (rb.save(), time.time() - t0))
    return 0 if checker.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
