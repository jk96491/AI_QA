"""OpenAI-ES (Salimans et al. 2017): 정책 신경망 가중치용 진화 전략 (PyTorch CPU).

결정 트리거가 있는 '짧은 에피소드 RL' 문제에서 정책 가중치를 학습한다.
- antithetic 샘플링(±ε), centered rank 정규화
- 추정 그래디언트를 theta.grad 에 넣고 torch.optim.Adam 으로 갱신
- 판 결과만 있으면 되므로 크레딧 할당·가치 함수가 필요 없다
"""
from __future__ import annotations

import torch

from balance_qa.backend import DTYPE, as_tensor
from balance_qa.optim.base import Optimizer


class OpenAIES(Optimizer):
    name = "openai-es"

    def __init__(
        self,
        x0,
        sigma: float = 0.05,
        lr: float = 0.03,
        popsize: int = 16,
        weight_decay: float = 0.0,
        seed: int = 0,
    ) -> None:
        x0_t = as_tensor(x0).flatten()
        super().__init__(int(x0_t.numel()), seed=seed, bounds=None)
        if popsize % 2:
            popsize += 1
        self.theta = torch.nn.Parameter(x0_t.clone())
        self.sigma = sigma
        self._popsize = popsize
        self.adam = torch.optim.Adam([self.theta], lr=lr, weight_decay=weight_decay)
        self._eps = torch.zeros(0, self.dim, dtype=DTYPE)

    @property
    def popsize(self) -> int:
        return self._popsize

    def ask(self) -> torch.Tensor:
        half = self.randn(self._popsize // 2, self.dim)
        self._eps = torch.cat([half, -half])
        return self.theta.detach() + self.sigma * self._eps

    @staticmethod
    def centered_ranks(x: torch.Tensor) -> torch.Tensor:
        ranks = torch.empty_like(x)
        ranks[torch.argsort(x)] = torch.arange(len(x), dtype=x.dtype)
        return ranks / (len(x) - 1) - 0.5

    def _tell(self, xs: torch.Tensor, losses: torch.Tensor) -> None:
        utilities = self.centered_ranks(-losses)  # 보상 = −손실
        grad_ascent = (utilities @ self._eps) / (len(utilities) * self.sigma)
        self.adam.zero_grad()
        self.theta.grad = -grad_ascent  # Adam 은 최소화 → 부호 반전
        self.adam.step()

    def recommendation(self) -> torch.Tensor:
        return self.theta.detach().clone()

    def state(self) -> dict:
        s = super().state()
        s.update({"sigma": self.sigma, "theta_norm": float(torch.linalg.norm(self.theta.detach()))})
        return s
