"""E0 정합성: 게임 프로토콜 적합성 · 시드 결정성 · 처리량 · 손 튜닝 기본값 매트릭스 · 필요 표본 수.

문서 7장 수치(생존 전환 61%/16%) 재현은 게임 내부 BT 의 일이므로 tests/game/test_need.py 에서 검사한다.
"""
from __future__ import annotations

import time

from balance_qa.analysis.stats import Stats
from balance_qa.game_api.client import GameClient
from balance_qa.game_api.conformance import ConformanceChecker
from balance_qa.report.report import ReportBuilder
from balance_qa.report.sections import behavior_table, summary_table
from experiments.common import CLASSES, PERSONAS, parse_args, session


def main() -> None:
    args = parse_args(__doc__)
    rb = ReportBuilder("E0 정합성 점검", args.out)

    with session(args) as s:
        rb.meta(game="%s %s" % (s.game.game, s.game.game_version), protocol=s.game.protocol_version,
                instances=s.pool.size)

        # 프로토콜 적합성 (풀과 별도 연결 1개)
        host, port = s.pool.clients[0].host, s.pool.clients[0].port
        s.pool.close()  # 게임 1개는 동시 연결 1개만 받으므로 잠시 풀을 닫음
        client = GameClient(host, port)
        checker = ConformanceChecker(client)
        results = checker.run()
        client.close()
        rb.section("프로토콜 적합성 (docs/PROTOCOL.md)")
        rb.table(["검사", "결과", "내용"],
                 [[r.name, "PASS" if r.passed else ("FAIL" if r.required else "WARN"), r.detail] for r in results])
        ok = checker.passed

    with session(args) as s:
        # 처리량
        t0 = time.time()
        n_probe = 40
        s.evaluate("warrior", "stable", n=n_probe)
        per = (time.time() - t0) / n_probe * 1000
        rb.section("처리량")
        rb.text("- 게임 인스턴스 %d개, 1판 평균 %.1f ms (프로토콜 왕복 포함, 병렬 실효값)" % (s.pool.size, per))

        # 손 튜닝 기본값 매트릭스
        n = args.scale.eval_n
        classes = [c for c in CLASSES if c in s.game.classes]
        summaries = [s.evaluate(c, p, n=n, label="%s/%s" % (c, p)) for c in classes for p in PERSONAS]
        summary_table(rb, summaries, "손 튜닝 기본값 매트릭스")
        behavior_table(rb, summaries)

        cvs = sorted(x.time_cv for x in summaries)
        rb.section("필요 표본 수 (설계 문서 9장)")
        rb.table(
            ["CV", "δ=1%", "δ=3%", "δ=5%"],
            [["%.3f (최대)" % cvs[-1]] + [Stats.required_n(cvs[-1], d) for d in (0.01, 0.03, 0.05)],
             ["%.3f (중앙)" % cvs[len(cvs) // 2]] + [Stats.required_n(cvs[len(cvs) // 2], d) for d in (0.01, 0.03, 0.05)]],
        )
    rb.meta(passed=ok)
    print("E0 %s → %s" % ("PASS" if ok else "FAIL", rb.save()))


if __name__ == "__main__":
    main()
