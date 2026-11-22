"""IMPALA 용 Actor-Critic (PyTorch CPU).

- 입력: 트리거 관측 (게임 state_features + 트리거 진행도)
- 정책: 각 BT 파라미터(정규화 [0,1])마다 독립 Beta(α, β) — 범위가 정해진 연속 행동에 자연스럽고
        경계 밖 샘플이 없다 (클리핑·tanh 보정 불필요)
- 가치: 상태 가치 V(x) — V-trace 타깃과 기준선
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import torch
from torch import nn
from torch.distributions import Beta
from torch.nn.utils import parameters_to_vector

from balance_qa.backend import DEVICE, POLICY_DTYPE, as_tensor, generator

U_EPS = 1e-4  # Beta 로그확률 수치 안정용 (행동을 (ε, 1−ε) 로 제한)


def _inv_softplus(y: np.ndarray) -> np.ndarray:
    return np.log(np.expm1(np.maximum(y, 1e-6)))


class ActorCritic(nn.Module):
    def __init__(self, obs_dim: int, act_dim: int, hidden: Sequence[int] = (64, 64), seed: int = 0) -> None:
        super().__init__()
        self.obs_dim = obs_dim
        self.act_dim = act_dim
        self.hidden = tuple(int(h) for h in hidden)
        layers = []
        prev = obs_dim
        for h in self.hidden:
            layers += [nn.Linear(prev, h), nn.Tanh()]
            prev = h
        self.torso = nn.Sequential(*layers)
        self.pi_head = nn.Linear(prev, 2 * act_dim)   # (α 원값, β 원값)
        self.v_head = nn.Linear(prev, 1)
        self.to(device=DEVICE, dtype=POLICY_DTYPE)
        self._init_weights(seed)

    def _init_weights(self, seed: int) -> None:
        g = generator(seed)
        with torch.no_grad():
            for m in self.modules():
                if isinstance(m, nn.Linear):
                    std = 1.0 / math.sqrt(m.in_features)
                    if m is self.pi_head:
                        std *= 0.01  # 초기 정책 = bias 로 정한 분포 (상태 무관)
                    m.weight.normal_(0.0, std, generator=g)
                    m.bias.zero_()

    # ------------------------------------------------------------------ 순전파
    def forward(self, obs: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        h = self.torso(obs)
        raw_a, raw_b = self.pi_head(h).chunk(2, dim=-1)
        alpha = nn.functional.softplus(raw_a) + 1.0   # α, β > 1 → 단봉 분포
        beta = nn.functional.softplus(raw_b) + 1.0
        value = self.v_head(h).squeeze(-1)
        return alpha, beta, value

    def distribution(self, obs: torch.Tensor) -> Tuple[Beta, torch.Tensor]:
        alpha, beta, value = self.forward(obs)
        return Beta(alpha, beta), value

    @staticmethod
    def log_prob(dist: Beta, actions: torch.Tensor) -> torch.Tensor:
        """행동 벡터 전체의 로그확률 (차원 합)."""
        return dist.log_prob(actions.clamp(U_EPS, 1.0 - U_EPS)).sum(-1)

    # ------------------------------------------------------------------ 초기화
    def set_initial_mean(self, target_unit, concentration: float = 10.0) -> None:
        """초기 정책 평균을 target(정규화 파라미터, 예: 정의서 default) 에 맞춘다.

        Beta 평균 = α/(α+β), α+β ≈ concentration (클수록 초기 탐색이 좁음).
        """
        m = np.clip(np.asarray(target_unit, dtype=float), 0.02, 0.98)
        alpha0 = np.maximum(m * concentration, 1.05)
        beta0 = np.maximum((1.0 - m) * concentration, 1.05)
        bias = np.concatenate([_inv_softplus(alpha0 - 1.0), _inv_softplus(beta0 - 1.0)])
        with torch.no_grad():
            self.pi_head.bias.copy_(as_tensor(bias, POLICY_DTYPE))

    # ------------------------------------------------------------------ 액터용 추론
    def act(self, obs: np.ndarray, rng: Optional[np.random.Generator] = None) -> Tuple[np.ndarray, float, float]:
        """(행동 u∈(0,1)^d, 행동 로그확률, V) — rng 가 없으면 결정론적(Beta 평균)."""
        with torch.no_grad():
            alpha, beta, value = self.forward(as_tensor(obs, POLICY_DTYPE))
            a = alpha.numpy().astype(float)
            b = beta.numpy().astype(float)
            if rng is None:
                u = a / (a + b)
            else:
                u = rng.beta(a, b)
            u = np.clip(u, U_EPS, 1.0 - U_EPS)
            logp = float(self.log_prob(Beta(alpha, beta), as_tensor(u, POLICY_DTYPE)))
        return u, logp, float(value)

    # ------------------------------------------------------------------ 가중치 교환 (파라미터 서버)
    def snapshot(self) -> Dict[str, torch.Tensor]:
        return {k: v.detach().clone() for k, v in self.state_dict().items()}

    def flat(self) -> torch.Tensor:
        return parameters_to_vector(self.parameters()).detach().clone()

    def clone_architecture(self) -> "ActorCritic":
        return ActorCritic(self.obs_dim, self.act_dim, self.hidden, seed=0)

    def __repr__(self) -> str:
        n = sum(p.numel() for p in self.parameters())
        return "ActorCritic(%d-%s-[Beta×%d | V], params=%d, torch-cpu)" % (
            self.obs_dim, "-".join(map(str, self.hidden)), self.act_dim, n)
