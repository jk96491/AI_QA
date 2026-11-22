"""궤적(trajectory)과 구간 보상.

한 판 = 트리거 수만큼의 짧은 에피소드 (판당 최대 1 + 경계 수 스텝).
스텝 t = 트리거 t 에서 파라미터를 정하고 다음 트리거(또는 판 끝)까지 진행한 구간.

구간 보상은 판 보상 R = −(분) − λ_d·사망 − λ_c·소모품 을 트리거 누적값(totals)의 차분으로 나눈 것이라
Σ 구간 보상 = 판 보상 (RewardFunction 과 정확히 일치, 중도절단 벌점·클리어 실패 벌점은 마지막 구간에 포함).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np
import torch

from balance_qa.backend import POLICY_DTYPE
from balance_qa.core.types import EpisodeResult
from balance_qa.reward.reward import RewardFunction


@dataclass
class Step:
    index: int
    obs: np.ndarray
    action: np.ndarray          # 정규화 행동 u ∈ (0,1)^d
    behavior_logp: float        # 행동 정책(액터가 쓴 가중치)의 로그확률
    totals: dict                # 이 트리거 시점 누적값
    value: float = 0.0          # 액터 시점 V (진단용)


@dataclass
class Trajectory:
    steps: List[Step]
    rewards: List[float]
    result: EpisodeResult
    policy_version: int
    seed: int

    @property
    def length(self) -> int:
        return len(self.steps)

    @property
    def episode_return(self) -> float:
        return float(sum(self.rewards))


class SegmentRewards:
    """트리거 누적값 → 구간 보상."""

    def __init__(self, reward_fn: RewardFunction) -> None:
        self.reward_fn = reward_fn

    def __call__(self, steps: Sequence[Step], result: EpisodeResult) -> List[float]:
        p = self.reward_fn.persona
        tl = self.reward_fn.time_limit
        marks = [
            (float(s.totals.get("elapsed", 0.0)), float(s.totals.get("deaths", 0)), float(s.totals.get("consumables_used", 0)))
            for s in steps
        ]
        # 판 끝: 중도절단 시간(실패 판은 남은 보스 체력만큼 벌점) 사용
        marks.append((result.effective_time(tl), float(result.deaths), float(result.consumables_used)))
        rewards = []
        for (e0, d0, c0), (e1, d1, c1) in zip(marks[:-1], marks[1:]):
            rewards.append(-(e1 - e0) / 60.0 - p.lambda_death * (d1 - d0) - p.lambda_consumable * (c1 - c0))
        if not result.cleared:
            rewards[-1] -= p.fail_penalty
        return rewards

    def build(self, steps: Sequence[Step], result: EpisodeResult, version: int) -> Optional[Trajectory]:
        if result.invalid or not steps:
            return None
        return Trajectory(list(steps), self(steps, result), result, version, result.seed)


@dataclass
class TrajectoryBatch:
    """[B, T] 패딩 배치. mask=1 인 칸만 유효, 각 궤적의 마지막 유효 스텝은 종료(terminal)."""

    obs: torch.Tensor            # [B, T, O]
    actions: torch.Tensor        # [B, T, A]
    behavior_logp: torch.Tensor  # [B, T]
    rewards: torch.Tensor        # [B, T]
    mask: torch.Tensor           # [B, T]
    versions: torch.Tensor       # [B]
    returns: List[float] = field(default_factory=list)

    @classmethod
    def collate(cls, trajs: Sequence[Trajectory], obs_dim: int, act_dim: int) -> "TrajectoryBatch":
        b = len(trajs)
        t = max(tr.length for tr in trajs)
        obs = np.zeros((b, t, obs_dim))
        act = np.full((b, t, act_dim), 0.5)  # 패딩 행동은 로그확률이 유한한 값으로
        blp = np.zeros((b, t))
        rew = np.zeros((b, t))
        mask = np.zeros((b, t))
        for i, tr in enumerate(trajs):
            for j, st in enumerate(tr.steps):
                obs[i, j] = st.obs
                act[i, j] = st.action
                blp[i, j] = st.behavior_logp
                rew[i, j] = tr.rewards[j]
                mask[i, j] = 1.0
        f = lambda x: torch.as_tensor(x, dtype=POLICY_DTYPE)  # noqa: E731
        return cls(f(obs), f(act), f(blp), f(rew), f(mask),
                   torch.as_tensor([tr.policy_version for tr in trajs]), [tr.episode_return for tr in trajs])
