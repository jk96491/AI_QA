"""학습 루프: ask → 에피소드 실행 → 보상 → tell.

- 같은 세대의 후보들은 같은 학습 시드로 평가 (공통 난수 → 후보 간 비교 노이즈 감소)
- 평가 예산(총 판수)을 고정해 직업 간 '최적화 편차'를 통제
- 수렴 판정: patience 세대 동안 세대 평균 보상 개선이 tol 미만이면 정지
- 학습 루프 안에는 LLM 이 없다 (문서 10장 운영 원칙)
- 후보·보상은 torch 텐서(CPU, float64)로 다룬다
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional

import torch

from balance_qa.backend import DTYPE
from balance_qa.control.param_source import ParamSource
from balance_qa.optim.base import Optimizer
from balance_qa.optim.decoder import CandidateDecoder
from balance_qa.reward.reward import RewardFunction
from balance_qa.runner.episode_runner import EpisodeJob, EpisodeRunner
from balance_qa.runner.seed_pool import TRAIN_SEEDS, SeedPool


@dataclass
class TrainerConfig:
    budget: int = 4000                # 총 평가 판수
    episodes_per_candidate: int = 10  # 후보당 판수 (k)
    max_generations: int = 1000
    patience: int = 8
    tol: float = 1e-3
    log_every: int = 1


@dataclass
class GenerationRecord:
    generation: int
    episodes_used: int
    gen_mean_reward: float
    gen_best_reward: float
    best_reward_so_far: float
    invalid_ratio: float
    elapsed_sec: float
    optimizer: Dict[str, float] = field(default_factory=dict)


@dataclass
class TrainingResult:
    optimizer: str
    recommendation: torch.Tensor
    best_x: torch.Tensor
    episodes_used: int
    generations: int
    converged: bool
    history: List[GenerationRecord]

    def history_dicts(self) -> List[dict]:
        return [asdict(h) for h in self.history]


class Trainer:
    def __init__(
        self,
        runner: EpisodeRunner,
        class_name: str,
        scenario: str,
        reward_fn: RewardFunction,
        config: Optional[TrainerConfig] = None,
        seeds: SeedPool = TRAIN_SEEDS,
        on_generation: Optional[Callable[[GenerationRecord], None]] = None,
        initial_state_fn: Optional[Callable[[int], Optional[Dict[str, float]]]] = None,
    ) -> None:
        """initial_state_fn(seed) → 그 판의 시작 상태 (v1.4). 없으면 가득. 컨텍스트 밴딧 기준선(CMA-셀별·CMA-전역)용."""
        self.initial_state_fn = initial_state_fn
        self.runner = runner
        self.class_name = class_name
        self.scenario = scenario
        self.reward_fn = reward_fn
        self.cfg = config or TrainerConfig()
        self.seeds = seeds
        self.on_generation = on_generation

    def _jobs(self, sources: List[ParamSource], seeds: List[int]) -> List[EpisodeJob]:
        return [
            EpisodeJob(self.class_name, self.scenario, seed, src,
                       initial_state=self.initial_state_fn(seed) if self.initial_state_fn else None)
            for src in sources
            for seed in seeds
        ]

    def train(self, optimizer: Optimizer, decoder: CandidateDecoder) -> TrainingResult:
        cfg = self.cfg
        k = cfg.episodes_per_candidate
        used = 0
        history: List[GenerationRecord] = []
        best_so_far = float("-inf")
        best_gen_mean = float("-inf")
        stale = 0
        converged = False
        t0 = time.time()

        for gen in range(cfg.max_generations):
            if used + optimizer.popsize * k > cfg.budget:
                break
            xs = optimizer.ask()
            seeds = self.seeds.batch(gen, k)
            results = self.runner.run(self._jobs([decoder.decode(x) for x in xs], seeds))
            used += len(results)

            rewards = []
            n_invalid = 0
            for i in range(len(xs)):
                chunk = results[i * k: (i + 1) * k]
                n_invalid += sum(r.invalid for r in chunk)
                rewards.append(self.reward_fn.mean(chunk))
            rewards_t = torch.tensor(rewards, dtype=DTYPE)
            optimizer.tell(xs, -rewards_t)

            gen_mean = float(rewards_t.mean())
            best_so_far = max(best_so_far, float(rewards_t.max()))
            rec = GenerationRecord(
                generation=gen,
                episodes_used=used,
                gen_mean_reward=gen_mean,
                gen_best_reward=float(rewards_t.max()),
                best_reward_so_far=best_so_far,
                invalid_ratio=n_invalid / max(1, len(results)),
                elapsed_sec=round(time.time() - t0, 2),
                optimizer={k_: v for k_, v in optimizer.state().items() if isinstance(v, (int, float))},
            )
            history.append(rec)
            if self.on_generation and gen % cfg.log_every == 0:
                self.on_generation(rec)

            if gen_mean > best_gen_mean + cfg.tol:
                best_gen_mean = gen_mean
                stale = 0
            else:
                stale += 1
                if stale >= cfg.patience:
                    converged = True
                    break

        return TrainingResult(
            optimizer=optimizer.name,
            recommendation=optimizer.recommendation(),
            best_x=optimizer.best_x if optimizer.best_x is not None else optimizer.recommendation(),
            episodes_used=used,
            generations=len(history),
            converged=converged,
            history=history,
        )
