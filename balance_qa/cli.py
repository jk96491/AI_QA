"""명령행 인터페이스.

게임 연결 (셋 중 하나, 기본은 --workers N 개의 파이썬 게임 대역을 자동 실행):
  --game 127.0.0.1:7777,127.0.0.1:7778                       이미 떠 있는 게임(Unity 빌드 등)에 접속
  --game-cmd "MyGame.exe -batchmode -qaPort {port}" --workers 4  명령으로 게임 N개 실행
  --workers 4                                                python -m game_sim serve 4개 실행
  --view 1 (+ --game-cmd)                                    그중 1개를 화면(창) 모드로 — 전투 뷰어로 학습 판 보기

python -m balance_qa list
python -m balance_qa check-game [--game 127.0.0.1:7777]
python -m balance_qa --workers 4 evaluate    --cls mage --persona stable -n 300
python -m balance_qa --workers 4 optimize    --cls mage --persona stable --budget 3000
python -m balance_qa --workers 4 policy      --cls warrior --persona stable --budget 6000
python -m balance_qa --workers 8 impala      --cls warrior --persona stable --budget 8000          # 로컬 액터 프로세스 8개
python -m balance_qa --workers 1 impala --actors external --listen 0.0.0.0:7000 --token T ...      # 클라우드: 액터 접속 대기
python -m balance_qa --game 10.0.0.7:7777 actor --learner 10.0.0.5:7000 --token T                # 액터 (각 머신)
python -m balance_qa --workers 4 sensitivity --cls archer --persona stable -n 100
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Dict, List, Optional

from balance_qa.analysis.sensitivity import OATSensitivity
from balance_qa.analysis.stats import Stats
from balance_qa.game_api.client import GameClient, parse_endpoint
from balance_qa.game_api.conformance import ConformanceChecker
from balance_qa.game_api.launcher import LocalSimLauncher
from balance_qa.report.report import ReportBuilder
from balance_qa.report.sections import behavior_table, outcome_section, summary_table
from balance_qa.runner.seed_pool import EVAL_SEEDS
from balance_qa.session import QASession


def _utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def _load_params(path: Optional[str]) -> Dict[str, float]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # optimize 결과 파일(params.json) 또는 평범한 dict 모두 허용
    if "source" in data and isinstance(data["source"], dict):
        return dict(data["source"].get("params", {}))
    return {k: float(v) for k, v in data.items()}


# ---------------------------------------------------------------------- 명령
def cmd_list(args: argparse.Namespace, s: QASession) -> None:
    g = s.game
    print("게임: %s %s (protocol %s), 인스턴스 %d개" % (g.game, g.game_version, g.protocol_version, s.pool.size))
    print("제한 시간 %.0fs, 최대 사망 %d, 트리거 %s %s" % (g.time_limit, g.max_deaths, g.trigger_type, list(g.trigger_supported)))
    print("트리거 상태:", ", ".join(g.state_features))
    print("직업:", ", ".join(s.class_names()))
    print("페르소나:", ", ".join("%s(%s)" % (p.id, p.name) for p in s.personas.all().values()))
    print("시나리오:", ", ".join(g.scenarios))
    for name in s.class_names():
        info = s.class_info(name)
        print("\n[%s %s] 최적화 파라미터 %d개" % (name, info.display_name, info.optimizable_space().dim))
        for p in info.params.values():
            print("  %-22s [%g, %g] default=%-6g %-8s %s" % (p.name, p.low, p.high, p.default, p.group, p.description))


def cmd_evaluate(args: argparse.Namespace, s: QASession) -> None:
    summaries = []
    for cls in args.cls:
        for pid in args.persona:
            summ = s.evaluate(cls, pid, params=_load_params(args.params), n=args.n, scenario=args.scenario)
            print(summ.row())
            summaries.append(summ)
    rb = ReportBuilder("평가: %s × %s" % (",".join(args.cls), ",".join(args.persona)), args.out)
    rb.meta(game="%s %s" % (s.game.game, s.game.game_version), n=args.n, scenario=args.scenario or "base",
            params_file=args.params or "default(손 튜닝)")
    summary_table(rb, summaries)
    behavior_table(rb, summaries)
    cv = [x.time_cv for x in summaries if x.time_cv == x.time_cv]
    if cv:
        mcv = max(cv)
        rb.section("필요 표본 수", "최대 CV %.3f 기준, 3%% 차이 검출(α .05, 검정력 .8)에 조건당 %d판"
                   % (mcv, Stats.required_n(mcv, 0.03)))
    print("리포트:", rb.save())


def cmd_optimize(args: argparse.Namespace, s: QASession) -> None:
    baseline = s.evaluate(args.cls, args.persona, n=args.eval_n, scenario=args.scenario, label="손 튜닝(default)")
    out = s.optimize(args.cls, args.persona, method=args.method, budget=args.budget, k=args.k, popsize=args.pop,
                     scenario=args.scenario, seed=args.seed, eval_n=args.eval_n)
    print("기준선:", baseline.row())
    print("최적화:", out.evaluation.row())
    rb = ReportBuilder("최적화: %s/%s (%s)" % (args.cls, args.persona, args.method), args.out)
    rb.meta(game="%s %s" % (s.game.game, s.game.game_version), budget=args.budget, k=args.k,
            scenario=args.scenario or "base", seed=args.seed)
    outcome_section(rb, out, baseline)
    path = rb.save()
    out.save_params(path / "params.json", s.game)
    print("리포트:", path)


def cmd_policy(args: argparse.Namespace, s: QASession) -> None:
    init = _load_params(args.init_params)
    baseline_label = "고정 파라미터(%s)" % ("init_params" if init else "default")
    baseline = s.evaluate(args.cls, args.persona, params=init, n=args.eval_n, scenario=args.scenario, label=baseline_label)
    out = s.train_policy(args.cls, args.persona, budget=args.budget, k=args.k, popsize=args.pop,
                         hidden=tuple(args.hidden), sigma=args.sigma, lr=args.lr, init_params=init,
                         scenario=args.scenario, seed=args.seed, eval_n=args.eval_n)
    print("기준선:", baseline.row())
    print("정책  :", out.evaluation.row())
    rb = ReportBuilder("트리거 정책: %s/%s" % (args.cls, args.persona), args.out)
    rb.meta(game="%s %s" % (s.game.game, s.game.game_version), budget=args.budget, k=args.k,
            hidden=args.hidden, sigma=args.sigma, lr=args.lr)
    outcome_section(rb, out, baseline)
    path = rb.save()
    out.save_params(path / "policy.json", s.game)
    print("리포트:", path)


def cmd_impala(args: argparse.Namespace, s: QASession) -> None:
    init = _load_params(args.init_params)
    baseline_label = "고정 파라미터(%s)" % ("init_params" if init else "default")
    baseline = s.evaluate(args.cls, args.persona, params=init, n=args.eval_n, scenario=args.scenario, label=baseline_label)
    out = s.train_impala(args.cls, args.persona, budget=args.budget, batch_size=args.batch, hidden=tuple(args.hidden),
                         lr=args.lr, entropy_coef=args.entropy, gamma=args.gamma, concentration=args.concentration,
                         init_params=init, scenario=args.scenario, seed=args.seed, eval_n=args.eval_n,
                         log_every=args.log_every, actors=args.actors, listen=parse_endpoint(args.listen),
                         token=args.token, idle_timeout=args.idle_timeout)
    print("기준선:", baseline.row())
    print("IMPALA:", out.evaluation.row())
    rb = ReportBuilder("IMPALA: %s/%s" % (args.cls, args.persona), args.out)
    rb.meta(game="%s %s" % (s.game.game, s.game.game_version), actor_mode=args.actors, budget=args.budget,
            batch=args.batch, hidden=args.hidden, lr=args.lr, entropy=args.entropy, gamma=args.gamma)
    outcome_section(rb, out, baseline)
    path = rb.save()
    out.save_params(path / "policy.json", s.game)
    if out.model is not None:
        import torch

        torch.save({"state_dict": out.model.state_dict(), "obs_dim": out.model.obs_dim,
                    "act_dim": out.model.act_dim, "hidden": list(out.model.hidden)}, str(path / "impala_model.pt"))
    print("리포트:", path)


def cmd_sensitivity(args: argparse.Namespace, s: QASession) -> None:
    info = s.class_info(args.cls)
    base = s.base_params(args.cls, args.persona, _load_params(args.params))
    rows = OATSensitivity(s.evaluator).run(
        args.cls, s.scenario(args.scenario), base, info.optimizable_space(), s.reward_fn(args.persona),
        EVAL_SEEDS.first(args.n), levels=args.levels,
    )
    rb = ReportBuilder("민감도(OAT): %s/%s" % (args.cls, args.persona), args.out)
    rb.meta(game="%s %s" % (s.game.game, s.game.game_version), n=args.n, levels=args.levels)
    rb.section("파라미터별 소요 시간 변화 (큰 순)")
    rb.table(["param", "values", "mean_time(s)", "range(s)", "range(%)", "best"],
             [[r.param, r.values, r.mean_time, r.time_range, r.time_range_pct, r.best_value] for r in rows])
    rb.data("rows", [r.as_dict() for r in rows])
    for r in rows:
        print("%-18s range %6.1fs (%5.1f%%)  best=%g" % (r.param, r.time_range, r.time_range_pct, r.best_value))
    print("리포트:", rb.save())


def check_game(args: argparse.Namespace) -> int:
    """게임 프로토콜 적합성 검사 (연결 1개로)."""
    launcher = None
    if args.game:
        host, port = parse_endpoint(args.game.split(",")[0])
    else:
        launcher = LocalSimLauncher(1).start()
        host, port = launcher.endpoints[0]
        print("(--game 미지정: 파이썬 게임 대역으로 검사)")
    client = GameClient(host, port)
    try:
        checker = ConformanceChecker(client)
        for r in checker.run():
            print(r.line())
        print("\n결과: %s" % ("PASS — 학습 플랫폼에 연결 가능" if checker.passed else "FAIL"))
        return 0 if checker.passed else 1
    finally:
        client.close()
        if launcher:
            launcher.stop()


# ---------------------------------------------------------------------- 파서
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="balance_qa", description="BT 파라미터 최적화 밸런스 QA 플랫폼 (게임과 프로토콜로 통신)")
    p.add_argument("--game", default=None, help="접속할 게임 HOST:PORT[,HOST:PORT...]")
    p.add_argument("--game-cmd", default=None, help="게임 실행 명령 템플릿 ({port} 치환), --workers 개 실행")
    p.add_argument("--workers", type=int, default=1, help="자동 실행할 게임 인스턴스 수 (= 병렬 판 수)")
    p.add_argument("--view", type=int, default=0,
                   help="--game-cmd 인스턴스 중 앞의 N개를 화면(창) 모드로 실행 — 전투 뷰어로 학습 판 보기")
    p.add_argument("--view-cmd", default=None,
                   help="화면 모드 명령 템플릿 (기본: --game-cmd 에서 -batchmode/-nographics 제거 + 1280x720 창)")
    p.add_argument("--torch-threads", type=int, default=None, help="학습(torch CPU) 스레드 수")
    p.add_argument("--qa-specs", default=None, help="페르소나 정의 폴더 (기본 qa_specs/)")
    p.add_argument("--out", default="reports")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="게임 describe 정보 + 페르소나")
    sub.add_parser("check-game", help="게임 프로토콜 적합성 검사 (Unity 빌드 연결 전 확인)")

    e = sub.add_parser("evaluate", help="고정 파라미터 평가")
    e.add_argument("--cls", nargs="+", required=True)
    e.add_argument("--persona", nargs="+", required=True)
    e.add_argument("-n", type=int, default=200)
    e.add_argument("--params", help="파라미터 JSON (dict 또는 optimize 결과 params.json)")
    e.add_argument("--scenario")

    o = sub.add_parser("optimize", help="판당 1회 파라미터 최적화")
    o.add_argument("--cls", required=True)
    o.add_argument("--persona", required=True)
    o.add_argument("--method", choices=["cma", "random"], default="cma")
    o.add_argument("--budget", type=int, default=3000)
    o.add_argument("-k", type=int, default=10, help="후보당 판수")
    o.add_argument("--pop", type=int, default=None)
    o.add_argument("--eval-n", type=int, default=300)
    o.add_argument("--scenario")
    o.add_argument("--seed", type=int, default=0)

    pol = sub.add_parser("policy", help="결정 트리거 정책 학습 (OpenAI-ES, torch CPU)")
    pol.add_argument("--cls", required=True)
    pol.add_argument("--persona", required=True)
    pol.add_argument("--budget", type=int, default=6000)
    pol.add_argument("-k", type=int, default=8)
    pol.add_argument("--pop", type=int, default=16)
    pol.add_argument("--hidden", type=int, nargs="+", default=[16])
    pol.add_argument("--sigma", type=float, default=0.1)
    pol.add_argument("--lr", type=float, default=0.05)
    pol.add_argument("--init-params", help="정책 시작점 파라미터 JSON (예: optimize 결과)")
    pol.add_argument("--eval-n", type=int, default=300)
    pol.add_argument("--scenario")
    pol.add_argument("--seed", type=int, default=0)

    im = sub.add_parser("impala", help="결정 트리거 정책 IMPALA 학습 (액터=게임 인스턴스, V-trace, torch CPU)")
    im.add_argument("--cls", required=True)
    im.add_argument("--persona", required=True)
    im.add_argument("--budget", type=int, default=6000, help="총 판수")
    im.add_argument("--batch", type=int, default=16, help="갱신당 궤적 수")
    im.add_argument("--hidden", type=int, nargs="+", default=[64, 64])
    im.add_argument("--lr", type=float, default=3e-3)
    im.add_argument("--entropy", type=float, default=3e-3)
    im.add_argument("--gamma", type=float, default=1.0)
    im.add_argument("--concentration", type=float, default=10.0, help="초기 Beta 집중도 (클수록 탐색 좁음)")
    im.add_argument("--init-params", help="정책 시작 평균 파라미터 JSON (예: optimize 결과)")
    im.add_argument("--eval-n", type=int, default=300)
    im.add_argument("--log-every", type=int, default=10)
    im.add_argument("--scenario")
    im.add_argument("--seed", type=int, default=0)
    im.add_argument("--actors", choices=["processes", "threads", "external"], default="processes",
                    help="processes: 게임마다 로컬 액터 프로세스 / threads: 학습기 안 스레드 / external: 외부 액터 접속 대기")
    im.add_argument("--listen", default="127.0.0.1:0", help="학습기 서버 주소 (external·클라우드: 0.0.0.0:7000 등)")
    im.add_argument("--token", default=None, help="액터 접속 토큰 (external 에서 권장)")
    im.add_argument("--idle-timeout", type=float, default=300.0, help="이 시간(초) 동안 판이 안 오면 중단")

    ac = sub.add_parser("actor", help="IMPALA 액터 프로세스: 학습기에 접속해 게임(--game/--game-cmd/대역)에서 판 실행")
    ac.add_argument("--learner", required=True, help="학습기 HOST:PORT")
    ac.add_argument("--actor-id", default=None)
    ac.add_argument("--token", default=None)

    sn = sub.add_parser("sensitivity", help="OAT 민감도 분석")
    sn.add_argument("--cls", required=True)
    sn.add_argument("--persona", required=True)
    sn.add_argument("-n", type=int, default=100)
    sn.add_argument("--levels", type=int, default=5)
    sn.add_argument("--params")
    sn.add_argument("--scenario")
    return p


COMMANDS = {
    "list": cmd_list,
    "evaluate": cmd_evaluate,
    "optimize": cmd_optimize,
    "policy": cmd_policy,
    "impala": cmd_impala,
    "sensitivity": cmd_sensitivity,
}


def open_session(args: argparse.Namespace) -> QASession:
    kw = {"torch_threads": args.torch_threads}
    if args.qa_specs:
        kw["qa_specs"] = args.qa_specs
    if args.game:
        return QASession(endpoints=[parse_endpoint(e) for e in args.game.split(",") if e.strip()], **kw)
    if args.game_cmd:
        view_cmd = shlex.split(args.view_cmd, posix=False) if args.view_cmd else None
        return QASession(game_command=shlex.split(args.game_cmd, posix=False), spawn=args.workers,
                         view=args.view, view_command=view_cmd, **kw)
    return QASession(spawn_local=args.workers, view=args.view, **kw)


def run_actor(args: argparse.Namespace) -> int:
    """액터 프로세스: 게임 1개 + 학습기 접속. 게임은 --game(첫 엔드포인트) / --game-cmd(1개 실행) / 파이썬 대역(1개)."""
    import torch

    from balance_qa.game_api.launcher import CommandLauncher
    from balance_qa.rl.remote_actor import ActorConfigError, RemoteActor

    torch.set_num_threads(1)  # 액터 프로세스는 추론만 → 스레드 1개 (여러 액터가 코어를 나눠 씀)
    launcher = None
    if args.game:
        host, port = parse_endpoint(args.game.split(",")[0])
    else:
        launcher = (CommandLauncher(shlex.split(args.game_cmd, posix=False), 1) if args.game_cmd
                    else LocalSimLauncher(1)).start()
        host, port = launcher.endpoints[0]
    client = GameClient(host, port)
    try:
        stats = RemoteActor(parse_endpoint(args.learner), client, args.actor_id, args.token,
                            log=lambda m: print(m, flush=True)).run()
        print("[actor %s] 종료: 판 %d (무효 %d)" % (stats["actor_id"], stats["episodes"], stats["invalid"]), flush=True)
        return 0
    except ActorConfigError as exc:
        print("[actor] 중단: %s" % exc, file=sys.stderr, flush=True)
        return 2
    except (ConnectionError, OSError) as exc:
        print("[actor] 학습기 연결 실패/종료: %s" % exc, file=sys.stderr, flush=True)
        return 3
    finally:
        client.close()
        if launcher:
            launcher.stop()


def main(argv: Optional[List[str]] = None) -> None:
    _utf8_stdout()
    args = build_parser().parse_args(argv)
    if args.cmd == "check-game":
        sys.exit(check_game(args))
    if args.cmd == "actor":
        sys.exit(run_actor(args))
    with open_session(args) as s:
        COMMANDS[args.cmd](args, s)


if __name__ == "__main__":
    main()
