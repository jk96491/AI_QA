"""IMPALA 오케스트레이터 (액터 N개 + 학습기 1개, 비동기).

    액터 (스레드 / 로컬 프로세스 / 원격 머신)  ── 각자 게임 인스턴스 1개 ──▶ 판 실행
        │  Trajectory  (ActorBackend 가 운반)
        ▼
    ActorContext.out 큐 ──▶ 학습기: batch_size 개 모이면 V-trace 갱신 → ParameterServer 게시
        ▲                                                                  │
        └──────────────── 액터는 판 시작마다 최신 가중치 버전 확인 ◀───────┘

- 액터 위치는 ActorBackend 로 바꾼다 (rl/backends.py). 학습기 코드는 같다.
- 액터가 학습기보다 뒤처진 정도(policy lag)는 V-trace 중요도 비율로 보정한다.
- 예산(판수)은 학습기가 '받은' 판 기준. 액터가 중간에 죽어도 다른 액터가 채운다.
- 비동기라 같은 설정이어도 실행마다 학습 경로가 조금씩 다르다 (평가는 결정론적).
"""
from __future__ import annotations

import queue
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from balance_qa.core.types import GameError
from balance_qa.optim.trainer import GenerationRecord, TrainingResult
from balance_qa.reward.reward import RewardFunction
from balance_qa.rl.actor import ActorParamSource, InvalidEpisode, ParameterServer
from balance_qa.rl.backends import ActorBackend, ActorContext
from balance_qa.rl.learner import ImpalaLearner, LearnerConfig
from balance_qa.rl.model import ActorCritic
from balance_qa.rl.spec import ActorSpec
from balance_qa.rl.trajectory import Trajectory, TrajectoryBatch
from balance_qa.runner.seed_pool import TRAIN_SEEDS, SeedPool
from balance_qa.spec.param import ParamSpace


@dataclass
class ImpalaConfig:
    budget: int = 6000               # 총 판수 (모든 액터 합, 학습기가 받은 기준)
    batch_size: int = 16             # 갱신당 궤적 수
    hidden: Tuple[int, ...] = (64, 64)
    concentration: float = 10.0      # 초기 Beta 집중도 (클수록 초기 탐색이 좁음)
    queue_size: int = 256
    log_every: int = 10              # 갱신 몇 번마다 기록
    idle_timeout: float = 300.0      # 이 시간 동안 판이 하나도 안 오면 중단 (external 대기 포함)
    seed: int = 0
    learner: LearnerConfig = field(default_factory=LearnerConfig)


@dataclass
class ImpalaResult:
    model: ActorCritic
    training: TrainingResult
    episodes_used: int
    invalid_episodes: int
    updates: int
    backend: Dict[str, object] = field(default_factory=dict)
    invalid_reasons: Dict[str, int] = field(default_factory=dict)


class ImpalaTrainer:
    def __init__(
        self,
        backend: ActorBackend,
        class_name: str,
        scenario: str,
        reward_fn: RewardFunction,
        space: ParamSpace,
        fixed: Mapping[str, float],
        thresholds: Sequence[float],
        state_features: Sequence[str],
        config: Optional[ImpalaConfig] = None,
        init_params: Optional[Mapping[str, float]] = None,
        seeds: SeedPool = TRAIN_SEEDS,
        game: Tuple[str, str] = ("", ""),
        on_log: Optional[Callable[[GenerationRecord], None]] = None,
    ) -> None:
        self.backend = backend
        self.class_name = class_name
        self.scenario = scenario
        self.reward_fn = reward_fn
        self.space = space
        self.fixed = dict(fixed)
        self.thresholds = tuple(sorted(thresholds, reverse=True))
        self.state_features = tuple(state_features)
        self.cfg = config or ImpalaConfig()
        self.seeds = seeds
        self.on_log = on_log
        self.obs_dim = len(self.state_features) + 1  # + 트리거 진행도
        self.model = ActorCritic(self.obs_dim, space.dim, self.cfg.hidden, seed=self.cfg.seed)
        start = {d.name: d.default for d in space.defs}
        start.update({k: v for k, v in (init_params or self.fixed).items() if k in start})
        self.model.set_initial_mean(space.encode(start), self.cfg.concentration)
        self.spec = ActorSpec(
            class_name=class_name, scenario=scenario, params=list(space.defs), fixed=self.fixed,
            thresholds=self.thresholds, obs_dim=self.obs_dim, act_dim=space.dim, hidden=tuple(self.cfg.hidden),
            persona=_persona_dict(reward_fn), time_limit=reward_fn.time_limit, state_features=self.state_features,
            sample_seed=self.cfg.seed, game=game[0], game_version=game[1],
        )

    def eval_source(self) -> ActorParamSource:
        """평가용: 결정론적(Beta 평균) 정책."""
        return ActorParamSource(self.model, self.space, self.fixed, self.thresholds, rng=None, record=False,
                                state_features=self.state_features)

    def train(self) -> ImpalaResult:
        cfg = self.cfg
        learner = ImpalaLearner(self.model, cfg.learner)
        params = ParameterServer()
        params.publish(self.model)
        ctx = ActorContext(self.spec, params, self.seeds, cfg.queue_size)

        t0 = time.time()
        received = invalid = 0
        buffer: List[Trajectory] = []
        window_returns: List[float] = []
        window_invalid = window_total = 0
        window_stats: List[Dict[str, float]] = []
        history: List[GenerationRecord] = []
        best_so_far = float("-inf")
        error: Optional[BaseException] = None
        last_item = time.time()
        invalid_reasons: Counter = Counter()

        self.backend.start(ctx)
        try:
            while received < cfg.budget:
                try:
                    item = ctx.out.get(timeout=1.0)
                except queue.Empty:
                    if not self.backend.alive():
                        error = RuntimeError("액터가 모두 종료됨 (받은 판 %d/%d)%s" % (
                            received, cfg.budget, _failures(self.backend)))
                        break
                    if time.time() - last_item > cfg.idle_timeout:
                        error = TimeoutError("%.0f초 동안 액터 결과 없음 (받은 판 %d/%d, 모드 %s)%s" % (
                            cfg.idle_timeout, received, cfg.budget, self.backend.name, _failures(self.backend)))
                        break
                    continue
                last_item = time.time()
                if isinstance(item, GameError):
                    error = item
                    break
                received += 1
                window_total += 1
                if isinstance(item, InvalidEpisode):
                    invalid += 1
                    window_invalid += 1
                    invalid_reasons[_reason_key(item.reason)] += 1
                    continue
                buffer.append(item)
                window_returns.append(item.episode_return)
                if len(buffer) < cfg.batch_size:
                    continue

                batch = TrajectoryBatch.collate(buffer, self.obs_dim, self.space.dim)
                buffer = []
                stats = learner.update(batch, params.version)
                stats["actors"] = float(self.backend.n_actors)
                window_stats.append(stats)
                params.publish(self.model)

                if learner.updates % cfg.log_every == 0:
                    rec = self._record(learner.updates, received, window_returns, window_invalid, window_total,
                                       window_stats, t0, best_so_far)
                    best_so_far = rec.best_reward_so_far
                    history.append(rec)
                    if self.on_log:
                        self.on_log(rec)
                    window_returns, window_stats = [], []
                    window_invalid = window_total = 0
        finally:
            ctx.stop.set()           # 새 작업 발급 중지, 액터 put 은 즉시 반환
            backend_info = self.backend.describe()
            self.backend.stop()
            while not ctx.out.empty():
                ctx.out.get_nowait()
        if error is not None:
            raise error
        if window_stats:
            history.append(self._record(learner.updates, received, window_returns, window_invalid, window_total,
                                        window_stats, t0, best_so_far))

        training = TrainingResult(
            optimizer="impala",
            recommendation=self.model.flat(),
            best_x=self.model.flat(),
            episodes_used=received,
            generations=len(history),
            converged=False,
            history=history,
        )
        return ImpalaResult(self.model, training, received, invalid, learner.updates, backend_info,
                            dict(invalid_reasons))

    @staticmethod
    def _record(updates, received, returns, n_invalid, n_total, stats, t0, best_so_far) -> GenerationRecord:
        mean_r = float(np.mean(returns)) if returns else float("nan")
        best_r = float(np.max(returns)) if returns else float("nan")
        agg = {k: float(np.mean([s[k] for s in stats])) for k in stats[0]} if stats else {}
        agg["updates"] = float(updates)
        return GenerationRecord(
            generation=updates,
            episodes_used=received,
            gen_mean_reward=mean_r,
            gen_best_reward=best_r,
            best_reward_so_far=max(best_so_far, best_r) if returns else best_so_far,
            invalid_ratio=n_invalid / max(1, n_total),
            elapsed_sec=round(time.time() - t0, 2),
            optimizer=agg,
        )


def _reason_key(reason: str) -> str:
    """무효 사유 집계 키: 'actor X: connection: ...' → 'connection: ...' 앞부분."""
    text = reason.split(": ", 1)[1] if reason.startswith("actor ") and ": " in reason else reason
    return text[:80]


def _persona_dict(reward_fn: RewardFunction) -> Dict[str, object]:
    import dataclasses

    return dataclasses.asdict(reward_fn.persona)


def _failures(backend: ActorBackend) -> str:
    fails = getattr(backend, "failures", lambda: [])()
    return ("\n" + "\n".join(fails)) if fails else ""
