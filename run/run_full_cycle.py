"""[PyCharm ▶] 전체 사이클 점검: 연결 → 기준선 평가 → 최적화 → IMPALA → 결과 재평가 → 리포트.

목적은 성능이 아니라 **처음부터 끝까지 끊김 없이 도는지** 확인하는 것 (예산은 작게).

게임 선택
- GAME_CMD = UNITY, VIEW = 0 : Unity 빌드를 헤드리스로 WORKERS 개 실행
- GAME_CMD = UNITY, VIEW = 1 : 그중 1개를 **화면(창) 모드**로 → 전투 뷰어로 학습 판을 보고,
                               마지막에 같은 seed 로 손 튜닝 / CMA-ES / IMPALA 판을 차례로 보여 준다 (7. 쇼케이스)
- GAME = "127.0.0.1:7777,..." : 이미 떠 있는 게임에 접속
- 모두 None                   : 파이썬 게임 대역
"""
import json
import time
import traceback

from _bootstrap import UNITY, setup

# ===================== 설정 =====================
GAME_CMD = None           # Unity 빌드 실행: UNITY / None = GAME 또는 파이썬 게임 대역
VIEW = 0                  # GAME_CMD 인스턴스 중 화면(창) 모드로 띄울 수 (1 이면 전투가 보인다)
VIEW_SIZE = None          # 창 크기 (가로, 세로). None = 창 1개면 1280x720, 여러 개면 900x506
SHOWCASE_WAIT = None      # 쇼케이스 판 사이 대기: None = Enter 키 / 숫자 = 초
GAME = None               # 이미 떠 있는 게임: "127.0.0.1:7777,127.0.0.1:7778"
WORKERS = 4               # GAME_CMD / 파이썬 대역일 때 띄울 인스턴스 수
CLASS = None              # None = 게임 describe 의 첫 직업
PERSONA = "stable"
EVAL_N = 50               # 평가 판수
OPT_BUDGET = 600          # CMA-ES 판수
IMPALA_BUDGET = 800       # IMPALA 판수
SEED = 0
# ================================================


def main() -> int:
    setup()
    from balance_qa.control.param_source import StaticParamSource
    import shlex

    from balance_qa.game_api.client import EpisodeRequest, GameClient, parse_endpoint
    from balance_qa.game_api.conformance import ConformanceChecker
    from balance_qa.game_api.launcher import CommandLauncher, LocalSimLauncher
    from balance_qa.runner.seed_pool import EVAL_SEEDS
    from balance_qa.session import QASession

    stages = []   # (이름, 성공 여부, 소요 초, 내용)
    ctx = {}

    def stage(name, fn):
        t0 = time.time()
        print("\n▶ %s" % name, flush=True)
        try:
            detail = fn() or ""
            stages.append((name, True, time.time() - t0, detail))
            print("  ✔ %s (%.1fs)" % (detail, time.time() - t0), flush=True)
            return True
        except Exception as exc:  # 어느 단계에서 끊겼는지 기록
            traceback.print_exc()
            stages.append((name, False, time.time() - t0, "%s: %s" % (type(exc).__name__, exc)))
            print("  ✘ 실패", flush=True)
            return False

    endpoints = [parse_endpoint(e) for e in GAME.split(",")] if GAME else None
    game_cmd = shlex.split(GAME_CMD, posix=False) if (GAME_CMD and not endpoints) else None

    # 1. 프로토콜 적합성 (연결 1개로 먼저)
    def conformance():
        launcher = None
        if endpoints:
            host, port = endpoints[0]
        else:
            launcher = (CommandLauncher(game_cmd, 1) if game_cmd else LocalSimLauncher(1)).start()
            host, port = launcher.endpoints[0]
        client = GameClient(host, port)
        try:
            checker = ConformanceChecker(client)
            results = checker.run()
            ctx["conformance"] = results
            failed = [r.name for r in results if r.required and not r.passed]
            warned = [r.name for r in results if not r.required and not r.passed]
            if failed:
                raise RuntimeError("필수 검사 실패: %s" % failed)
            return "%d개 검사 통과%s" % (len(results), (", 경고 %s" % warned) if warned else "")
        finally:
            client.close()
            if launcher:
                launcher.stop()

    if not stage("1. 게임 프로토콜 적합성", conformance):
        return report(stages, ctx)

    if endpoints:
        session = QASession(endpoints=endpoints)
    elif game_cmd:
        if VIEW:
            print("\n화면 모드 인스턴스 %d개를 띄웁니다. 창마다 학습 판이 자동으로 재생됩니다 (-qaFollow, 8배속) "
                  "(속도: 숫자키 1~6 = 0.5x~16x, Tab 패널)." % VIEW, flush=True)
        size = VIEW_SIZE or ((1280, 720) if VIEW <= 1 else (900, 506))
        session = QASession(game_command=game_cmd, spawn=WORKERS, view=VIEW, view_size=size)
    else:
        session = QASession(spawn_local=WORKERS)
    with session as s:
        cls = CLASS or s.class_names()[0]
        ctx["meta"] = {"game": "%s %s" % (s.game.game, s.game.game_version), "protocol": s.game.protocol_version,
                       "instances": s.pool.size, "class": cls, "persona": PERSONA}

        def describe():
            info = s.class_info(cls)
            return "game=%s, 인스턴스 %d개, 직업 %s, 학습 파라미터 %d개, 트리거 %s" % (
                ctx["meta"]["game"], s.pool.size, s.class_names(), info.optimizable_space().dim,
                list(s.game.trigger_supported))

        stage("2. 정의서 수신 (describe)", describe)

        def baseline():
            ctx["baseline"] = s.evaluate(cls, PERSONA, n=EVAL_N, label="손 튜닝(default)")
            b = ctx["baseline"]
            return "%s, 무효 %.0f%%" % (b.row()["effective_time_s"], 100 * b.invalid_ratio)

        stage("3. 기준선 평가 (손 튜닝)", baseline)

        def optimize():
            out = s.optimize(cls, PERSONA, budget=OPT_BUDGET, eval_n=EVAL_N, seed=SEED, verbose=False)
            ctx["opt"] = out
            return "%d판 학습 → %s" % (out.training.episodes_used, out.evaluation.row()["effective_time_s"])

        if not stage("4. 판당 1회 최적화 (CMA-ES)", optimize):
            return report(stages, ctx)

        def save_and_reload_params():
            out = ctx["opt"]
            path = out.save_params(ctx_path("params.json", ctx), s.game)
            loaded = json.loads(path.read_text(encoding="utf-8"))["source"]["params"]
            again = s.evaluate(cls, PERSONA, n=EVAL_N, label="최적화 params 재평가", source=StaticParamSource(loaded))
            ctx["reload"] = again
            same = abs(again.effective_time.estimate - out.evaluation.effective_time.estimate) < 1e-9
            if not same:
                raise RuntimeError("저장 → 재로드 → 평가 결과가 학습 직후 평가와 다름")
            return "params.json 저장·재로드 후 같은 결과 (%s)" % again.row()["effective_time_s"]

        stage("5. 결과 저장·재사용 (params.json)", save_and_reload_params)

        def impala():
            out = s.train_impala(cls, PERSONA, budget=IMPALA_BUDGET, eval_n=EVAL_N, init_params=ctx["opt"].params,
                                 seed=SEED, log_every=10, verbose=True)
            ctx["impala"] = out
            out.save_params(ctx_path("policy.json", ctx), s.game)
            h = out.training.history
            return "%d판, 갱신 %d회, 무효 %.0f%% → %s" % (
                out.training.episodes_used, int(h[-1].optimizer.get("updates", 0)) if h else 0,
                100 * max((x.invalid_ratio for x in h), default=0.0), out.evaluation.row()["effective_time_s"])

        stage("6. IMPALA 학습 (최적화 결과에서 시작)", impala)

        viewers = s.view_clients
        if viewers and all(k in ctx for k in ("opt", "impala")):
            def wait(msg):
                if SHOWCASE_WAIT is None:
                    input("   %s — Enter ▶ " % msg)
                else:
                    print("   %s (%.0f초 대기)" % (msg, SHOWCASE_WAIT), flush=True)
                    time.sleep(SHOWCASE_WAIT)

            def showcase():
                seed = EVAL_SEEDS.first(1)[0]
                runs = [("손 튜닝(default)", StaticParamSource(s.base_params(cls, PERSONA))),
                        ("CMA-ES 최적화", ctx["opt"].source),
                        ("IMPALA 정책", ctx["impala"].source)]
                side_by_side = len(viewers) >= len(runs)   # 창이 3개 이상이면 창마다 하나씩 동시에
                print("   창에 판이 재생됩니다 (seed %d, %s)%s" % (
                    seed, cls, " — 창 1·2·3 = 손 튜닝·CMA-ES·IMPALA 동시 비교" if side_by_side else ""))
                lines = []
                for i, (label, src) in enumerate(runs):
                    viewer = viewers[i] if side_by_side else viewers[0]
                    res = viewer.run_episode(EpisodeRequest(cls, seed), src)
                    line = "%s: %s %.0fs, 사망 %d, 물약 %d%s" % (
                        label, "클리어" if res.cleared else "실패", res.elapsed, res.deaths, res.consumables_used,
                        ", 멈춤" if res.stalled else "")
                    print("   ▶ %s (창 %d, 포트 %d)" % (line, i + 1 if side_by_side else 1, viewer.port), flush=True)
                    lines.append(line)
                    if not side_by_side:
                        wait("재생을 보고 다음 판으로")
                if side_by_side:
                    wait("세 창의 재생을 비교해 보고")
                return " / ".join(lines)

            stage("7. 화면 쇼케이스 (같은 seed: 손 튜닝 → CMA-ES → IMPALA)", showcase)
            if SHOWCASE_WAIT is None:
                input("\n화면 창을 닫고 종료하려면 Enter ▶ ")

    return report(stages, ctx)


def ctx_path(name, ctx):
    from pathlib import Path

    from balance_qa.report.report import ReportBuilder

    if ctx.get("rb") is None:
        ctx["rb"] = ReportBuilder("전체 사이클 점검", "reports")
    ctx["rb"].dir.mkdir(parents=True, exist_ok=True)
    return Path(ctx["rb"].dir) / name


def report(stages, ctx) -> int:
    from balance_qa.report.report import ReportBuilder
    from balance_qa.report.sections import behavior_table, summary_table

    rb = ctx.get("rb") or ReportBuilder("전체 사이클 점검", "reports")
    ok = all(s[1] for s in stages) and len(stages) >= 6
    rb.meta(result="PASS" if ok else "FAIL", **ctx.get("meta", {}))
    rb.section("단계별 결과")
    rb.table(["단계", "결과", "소요(s)", "내용"], [[n, "OK" if p else "FAIL", "%.1f" % t, d] for n, p, t, d in stages])
    if "conformance" in ctx:
        rb.section("프로토콜 적합성 상세")
        rb.table(["검사", "결과", "내용"], [[r.name, "PASS" if r.passed else ("FAIL" if r.required else "WARN"), r.detail]
                                         for r in ctx["conformance"]])
    evals = [ctx[k].evaluation if hasattr(ctx.get(k), "evaluation") else ctx[k]
             for k in ("baseline", "opt", "reload", "impala") if k in ctx]
    if evals:
        summary_table(rb, evals, "평가 비교 (작은 예산 — 성능 판단용 아님)")
        behavior_table(rb, evals)
    path = rb.save()

    print("\n" + "=" * 70)
    for n, p, t, d in stages:
        print("%s %-34s %6.1fs  %s" % ("OK  " if p else "FAIL", n, t, d))
    print("=" * 70)
    print("전체 사이클: %s   리포트: %s" % ("PASS" if ok else "FAIL", path))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
