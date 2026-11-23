"""QASession: 게임 연결 · 페르소나 · 평가기 · 학습기를 묶은 상위 인터페이스.

게임은 프로토콜로만 연결된다 (docs/PROTOCOL.md).

    # 파이썬 게임 대역을 4개 띄워서 사용 (개발용)
    with QASession(spawn_local=4) as s: ...

    # 이미 떠 있는 게임(Unity 빌드 등)에 접속
    with QASession(endpoints=[("127.0.0.1", 7777), ("127.0.0.1", 7778)]) as s: ...

    # 명령 템플릿으로 게임을 띄워서 사용
    with QASession(game_command=["MyGame.exe", "-batchmode", "-qaPort", "{port}"], spawn=4) as s: ...

    # 그중 1개는 화면(창) 모드로 — 전투 뷰어로 학습 판을 본다 (나머지는 헤드리스)
    with QASession(game_command=[...], spawn=4, view=1) as s: s.view_clients[0] ...
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from balance_qa.analysis.evaluator import EvaluationSummary, Evaluator
from balance_qa.backend import configure_threads
from balance_qa.control.param_source import ParamSource, StaticParamSource
from balance_qa.game_api.client import GameClient
from balance_qa.game_api.launcher import CommandLauncher, LocalSimLauncher, view_command_from
from balance_qa.game_api.pool import GamePool
from balance_qa.optim.base import Optimizer
from balance_qa.optim.cma_es import CMAES
from balance_qa.optim.decoder import PolicyDecoder, StaticDecoder
from balance_qa.optim.openai_es import OpenAIES
from balance_qa.optim.random_search import RandomSearch
from balance_qa.optim.trainer import GenerationRecord, Trainer, TrainerConfig, TrainingResult
from balance_qa.reward.reward import RewardFunction
from balance_qa.rl.backends import ActorBackend, RemoteActorBackend, ThreadActorBackend
from balance_qa.rl.impala import ImpalaConfig, ImpalaTrainer
from balance_qa.rl.learner import LearnerConfig
from balance_qa.rl.model import ActorCritic
from balance_qa.runner.seed_pool import EVAL_SEEDS, TRAIN_SEEDS
from balance_qa.spec.game_info import ClassInfo, GameDescription
from balance_qa.spec.loader import QA_SPECS_DIR, PersonaRepository, SpecError
from balance_qa.spec.persona import Persona

# 학습 대상 = 게임이 선언한 블록 가중치뿐 (SDK 규칙). CMA-ES·ES 정책·IMPALA 모두 info.learnable_space() 만 쓴다.
# 가중치가 아닌 BT 값은 정의서 default 또는 페르소나 params 로 고정된다.


@dataclass
class OptimizationOutcome:
    class_name: str
    persona_id: str
    method: str
    scenario: str
    source: ParamSource
    training: TrainingResult
    evaluation: EvaluationSummary
    model: Optional[ActorCritic] = None   # IMPALA 일 때 학습된 Actor-Critic

    @property
    def params(self) -> Optional[Dict[str, float]]:
        return self.source.params if isinstance(self.source, StaticParamSource) else None

    def save_params(self, path: Union[str, Path], game: Optional[GameDescription] = None) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "class": self.class_name,
            "persona": self.persona_id,
            "method": self.method,
            "scenario": self.scenario,
            "source": self.source.describe(),
        }
        if game is not None:
            payload["game"] = {"name": game.game, "version": game.game_version, "protocol": game.protocol_version}
            payload["trigger_type"] = game.trigger_type
            info = game.classes.get(self.class_name)
            if info is not None:
                payload["learned"] = info.weight_names   # 학습한 값 = 블록 가중치뿐 (나머지는 default·페르소나 고정값)
        if not isinstance(self.source, StaticParamSource):
            payload["policy_theta"] = self.training.recommendation.tolist()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def print_impala_progress(rec: GenerationRecord) -> None:
    o = rec.optimizer
    print(
        "  upd %4d | 판 %6d | 평균 return %8.3f | 최고 %8.3f | V %7.3f | ent %6.2f | ρ %.2f(clip %.0f%%) | lag %.1f | 무효 %4.1f%% | %5.1fs"
        % (rec.generation, rec.episodes_used, rec.gen_mean_reward, rec.gen_best_reward, o.get("value_mean", 0.0),
           o.get("entropy", 0.0), o.get("rho_mean", 0.0), 100 * o.get("rho_clip_frac", 0.0), o.get("policy_lag", 0.0),
           100 * rec.invalid_ratio, rec.elapsed_sec),
        flush=True,
    )


def print_progress(rec: GenerationRecord) -> None:
    print(
        "  gen %3d | 판 %6d | 세대평균 %8.3f | 세대최고 %8.3f | 무효 %4.1f%% | %5.1fs"
        % (rec.generation, rec.episodes_used, rec.gen_mean_reward, rec.gen_best_reward,
           100 * rec.invalid_ratio, rec.elapsed_sec),
        flush=True,
    )


class QASession:
    def __init__(
        self,
        endpoints: Optional[Sequence[Tuple[str, int]]] = None,
        spawn_local: int = 0,
        game_command: Optional[Sequence[str]] = None,
        spawn: int = 1,
        view: int = 0,
        view_command: Optional[Sequence[str]] = None,
        view_size: Optional[Tuple[int, int]] = None,
        qa_specs: Union[str, Path] = QA_SPECS_DIR,
        torch_threads: Optional[int] = None,
        timeout: float = 120.0,
    ) -> None:
        configure_threads(torch_threads)  # 학습(최적화기) 쪽 torch CPU 스레드 수
        self.launcher: Optional[CommandLauncher] = None
        if endpoints:
            eps = list(endpoints)
        elif game_command:
            if view and not view_command:
                view_command = view_command_from(game_command, view_size)
            self.launcher = CommandLauncher(game_command, spawn, view=view, view_command=view_command).start()
            eps = self.launcher.endpoints
        else:
            if view:
                print("[알림] 파이썬 게임 대역(game_sim)은 화면이 없어 --view 를 무시합니다. Unity 빌드는 --game-cmd 로 실행하세요.")
            self.launcher = LocalSimLauncher(max(1, spawn_local)).start()
            eps = self.launcher.endpoints
        try:
            self.pool = GamePool(eps, timeout=timeout)
        except Exception:
            if self.launcher:
                self.launcher.stop()
            raise
        self.game: GameDescription = self.pool.describe()
        self.personas = PersonaRepository(qa_specs)
        self.evaluator = Evaluator(self.pool)

    @property
    def view_clients(self) -> List["GameClient"]:
        """화면 모드로 띄운 게임 연결 (pool.clients 의 앞쪽). 없으면 빈 목록."""
        n = len(self.launcher.view_endpoints) if self.launcher is not None else 0
        return self.pool.clients[:n]

    def __enter__(self) -> "QASession":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.pool.close()
        if self.launcher:
            self.launcher.stop()
            self.launcher = None

    # ------------------------------------------------------------------ 조회
    def class_names(self) -> List[str]:
        return sorted(self.game.classes)

    def class_info(self, name: str) -> ClassInfo:
        return self.game.class_info(name)

    def persona(self, pid: str) -> Persona:
        return self.personas.get(pid)

    def scenario(self, name: Optional[str]) -> str:
        sc = name or "base"
        self.game.check_scenario(sc)
        return sc

    def reward_fn(self, pid: str) -> RewardFunction:
        return RewardFunction(self.persona(pid), self.game.time_limit)

    def base_params(self, cls: str, pid: str, overrides: Optional[Mapping[str, float]] = None) -> Dict[str, float]:
        """게임 정의서 default(손 튜닝 값) + 페르소나 설정값 + 덮어쓰기."""
        info = self.class_info(cls)
        persona = self.persona(pid)
        problems = PersonaRepository.check_against(persona, info)
        if problems:
            raise SpecError("persona/%s vs game/%s" % (pid, cls), problems)
        params = info.default_params()
        params.update(persona.settings())
        if overrides:
            params.update({k: v for k, v in overrides.items() if k in info.params})
        return params

    # ------------------------------------------------------------------ 평가
    def evaluate(
        self,
        cls: str,
        pid: str,
        params: Optional[Mapping[str, float]] = None,
        n: int = 200,
        scenario: Optional[str] = None,
        label: Optional[str] = None,
        source: Optional[ParamSource] = None,
        seed_offset: int = 0,
    ) -> EvaluationSummary:
        src = source or StaticParamSource(self.base_params(cls, pid, params))
        return self.evaluator.evaluate(
            label or "%s/%s" % (cls, pid), cls, self.scenario(scenario), src,
            EVAL_SEEDS.batch(seed_offset, n), self.reward_fn(pid),
        )

    # ------------------------------------------------------------------ 학습 공통
    def _trainer(self, cls: str, pid: str, scenario: str, cfg: TrainerConfig, verbose: bool) -> Trainer:
        return Trainer(self.pool, cls, scenario, self.reward_fn(pid), cfg, TRAIN_SEEDS,
                       on_generation=print_progress if verbose else None)

    # ------------------------------------------------------------------ 판당 1회 파라미터 최적화
    @staticmethod
    def make_static_optimizer(method: str, decoder: StaticDecoder, popsize: Optional[int], seed: int,
                              sigma0: float = 0.25) -> Optimizer:
        if method == "cma":
            return CMAES(decoder.x0(), sigma0=sigma0, popsize=popsize, seed=seed)
        if method == "random":
            return RandomSearch(decoder.dim, popsize=popsize or 12, seed=seed, x0=decoder.x0())
        raise ValueError("unknown method %r (cma | random)" % method)

    def optimize(
        self,
        cls: str,
        pid: str,
        method: str = "cma",
        budget: int = 3000,
        k: int = 10,
        popsize: Optional[int] = None,
        scenario: Optional[str] = None,
        seed: int = 0,
        eval_n: int = 300,
        params_to_optimize: Optional[Sequence[str]] = None,
        fixed_overrides: Optional[Mapping[str, float]] = None,
        verbose: bool = True,
    ) -> OptimizationOutcome:
        sc = self.scenario(scenario)
        space = self.class_info(cls).learnable_space(params_to_optimize or None)
        decoder = StaticDecoder(space, self.base_params(cls, pid, fixed_overrides))
        optimizer = self.make_static_optimizer(method, decoder, popsize, seed)
        if verbose:
            print("[optimize] %s/%s %s dim=%d pop=%d budget=%d k=%d games=%d"
                  % (cls, pid, method, space.dim, optimizer.popsize, budget, k, self.pool.size))
        result = self._trainer(cls, pid, sc, TrainerConfig(budget=budget, episodes_per_candidate=k), verbose).train(optimizer, decoder)
        source = decoder.decode(result.recommendation)
        summary = self.evaluate(cls, pid, n=eval_n, scenario=sc, label="%s/%s %s" % (cls, pid, method), source=source)
        return OptimizationOutcome(cls, pid, method, sc, source, result, summary)

    # ------------------------------------------------------------------ 결정 트리거 정책 학습 (9장)
    def train_policy(
        self,
        cls: str,
        pid: str,
        budget: int = 6000,
        k: int = 8,
        popsize: int = 16,
        hidden: Sequence[int] = (16,),
        sigma: float = 0.1,
        lr: float = 0.05,
        thresholds: Optional[Sequence[float]] = None,
        outputs: Optional[Sequence[str]] = None,
        init_params: Optional[Mapping[str, float]] = None,
        scenario: Optional[str] = None,
        seed: int = 0,
        eval_n: int = 300,
        verbose: bool = True,
    ) -> OptimizationOutcome:
        sc = self.scenario(scenario)
        info = self.class_info(cls)
        space = info.learnable_space(outputs)   # 출력 = 블록 가중치 (outputs 는 그 부분집합만)
        fixed = self.base_params(cls, pid, init_params)
        decoder = PolicyDecoder(
            space, fixed,
            thresholds if thresholds is not None else self.game.trigger_supported,
            n_features=len(self.game.state_features),
            hidden=hidden, seed=seed, init_params=fixed,
        )
        optimizer = OpenAIES(decoder.x0(), sigma=sigma, lr=lr, popsize=popsize, seed=seed)
        if verbose:
            print("[policy] %s/%s %r outputs=%s triggers=%s budget=%d games=%d"
                  % (cls, pid, decoder.template, list(space.names), list(decoder.thresholds), budget, self.pool.size))
        cfg = TrainerConfig(budget=budget, episodes_per_candidate=k, patience=1000)
        result = self._trainer(cls, pid, sc, cfg, verbose).train(optimizer, decoder)
        source = decoder.decode(result.recommendation)
        summary = self.evaluate(cls, pid, n=eval_n, scenario=sc, label="%s/%s policy" % (cls, pid), source=source)
        return OptimizationOutcome(cls, pid, "policy-es", sc, source, result, summary)

    # ------------------------------------------------------------------ IMPALA (비동기 액터-학습기 + V-trace)
    def train_impala(
        self,
        cls: str,
        pid: str,
        budget: int = 6000,
        batch_size: int = 16,
        hidden: Sequence[int] = (64, 64),
        lr: float = 3e-3,
        entropy_coef: float = 3e-3,
        gamma: float = 1.0,
        concentration: float = 10.0,
        thresholds: Optional[Sequence[float]] = None,
        outputs: Optional[Sequence[str]] = None,
        init_params: Optional[Mapping[str, float]] = None,
        scenario: Optional[str] = None,
        seed: int = 0,
        eval_n: int = 300,
        log_every: int = 10,
        actors: str = "processes",
        listen: Tuple[str, int] = ("127.0.0.1", 0),
        token: Optional[str] = None,
        idle_timeout: float = 300.0,
        verbose: bool = True,
    ) -> OptimizationOutcome:
        """결정 트리거 정책을 IMPALA 로 학습.

        actors:
          "processes" — 세션의 게임 인스턴스마다 로컬 액터 프로세스 1개 (기본, 로컬 다중 액터)
          "threads"   — 학습기 프로세스 안 스레드 액터 (가벼운 실행·테스트)
          "external"  — listen 주소에서 외부 액터 접속 대기 (`python -m balance_qa actor ...`, 클라우드용).
                        세션의 게임은 평가에만 쓰인다.
        """
        if not self.game.supports_segment_rewards:
            raise RuntimeError(
                "게임이 trigger.totals(%s) 를 보내지 않음 — 프로토콜 v1.1 필요 (docs/PROTOCOL.md 4.4)"
                % (GameDescription.REQUIRED_TOTALS,))
        sc = self.scenario(scenario)
        info = self.class_info(cls)
        space = info.learnable_space(outputs)   # 출력 = 블록 가중치 (outputs 는 그 부분집합만)
        fixed = self.base_params(cls, pid, init_params)
        cfg = ImpalaConfig(
            budget=budget, batch_size=batch_size, hidden=tuple(hidden), concentration=concentration,
            log_every=log_every, seed=seed, idle_timeout=idle_timeout,
            learner=LearnerConfig(lr=lr, gamma=gamma, entropy_coef=entropy_coef),
        )

        def announce(addr: Tuple[str, int]) -> None:
            if verbose and actors == "external":
                print("  학습기 대기 중: %s:%d — 액터 실행: python -m balance_qa --game <게임> actor --learner <이 주소>%s"
                      % (addr[0], addr[1], " --token <토큰>" if token else ""), flush=True)

        suspended = False
        if actors == "threads":
            backend: ActorBackend = ThreadActorBackend(self.pool.clients)
        elif actors == "processes":
            backend = RemoteActorBackend(listen, game_endpoints=self.pool.endpoints, token=token, on_listen=announce)
        elif actors == "external":
            backend = RemoteActorBackend(listen, game_endpoints=None, token=token, on_listen=announce)
        else:
            raise ValueError("actors 는 processes | threads | external")

        trainer = ImpalaTrainer(
            backend, cls, sc, self.reward_fn(pid), space, fixed,
            thresholds if thresholds is not None else self.game.trigger_supported,
            state_features=self.game.state_features, config=cfg, init_params=fixed,
            game=(self.game.game, self.game.game_version),
            on_log=print_impala_progress if verbose else None,
        )
        if verbose:
            print("[impala] %s/%s %r outputs=%s triggers=%s budget=%d batch=%d actors=%s(%d)"
                  % (cls, pid, trainer.model, list(space.names), list(trainer.thresholds), budget, batch_size,
                     actors, backend.n_actors))
        if actors == "processes":
            self.pool.suspend()  # 게임 연결을 액터 프로세스에 넘김
            suspended = True
        try:
            result = trainer.train()
        finally:
            if suspended:
                self.pool.resume()
        if verbose:
            by_actor = result.backend.get("episodes_by_actor")
            print("  완료: 판 %d (무효 %d), 갱신 %d%s" % (
                result.episodes_used, result.invalid_episodes, result.updates,
                (", 액터별 %s" % by_actor) if by_actor else ""))
            if result.invalid_reasons:
                print("  무효 사유: %s" % result.invalid_reasons)
        summary = self.evaluate(cls, pid, n=eval_n, scenario=sc, label="%s/%s impala" % (cls, pid),
                                source=trainer.eval_source())
        return OptimizationOutcome(cls, pid, "impala", sc, trainer.eval_source(), result.training, summary,
                                   result.model)
