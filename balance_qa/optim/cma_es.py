"""CMA-ES (Hansen 2016 튜토리얼 기반 최소 구현, PyTorch CPU / float64).

판당 1회 결정(트리거 없음)일 때 BT 파라미터 벡터를 [0, 1]^d 에서 직접 최적화한다.
경계 처리: 후보를 잘라서(clip) 평가하고, 잘린 점으로 분포를 갱신한다 (repair).
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import torch

from balance_qa.backend import DTYPE, as_tensor
from balance_qa.optim.base import Optimizer


class CMAES(Optimizer):
    name = "cma-es"

    def __init__(
        self,
        x0,
        sigma0: float = 0.25,
        popsize: Optional[int] = None,
        seed: int = 0,
        bounds: Optional[Tuple[float, float]] = (0.0, 1.0),
    ) -> None:
        x0_t = as_tensor(x0).flatten()
        n = int(x0_t.numel())
        super().__init__(n, seed=seed, bounds=bounds)
        self.mean = x0_t.clone()
        self.sigma = float(sigma0)

        self.lam = int(popsize or 4 + int(3 * math.log(n)))
        self.mu = self.lam // 2
        w = math.log(self.mu + 0.5) - torch.log(torch.arange(1, self.mu + 1, dtype=DTYPE))
        self.weights = w / w.sum()
        self.mueff = float(1.0 / torch.sum(self.weights ** 2))

        self.cc = (4 + self.mueff / n) / (n + 4 + 2 * self.mueff / n)
        self.cs = (self.mueff + 2) / (n + self.mueff + 5)
        self.c1 = 2 / ((n + 1.3) ** 2 + self.mueff)
        self.cmu = min(1 - self.c1, 2 * (self.mueff - 2 + 1 / self.mueff) / ((n + 2) ** 2 + self.mueff))
        self.damps = 1 + 2 * max(0.0, math.sqrt((self.mueff - 1) / (n + 1)) - 1) + self.cs
        self.chi_n = math.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n * n))

        self.pc = torch.zeros(n, dtype=DTYPE)
        self.ps = torch.zeros(n, dtype=DTYPE)
        self.C = torch.eye(n, dtype=DTYPE)
        self.B = torch.eye(n, dtype=DTYPE)
        self.D = torch.ones(n, dtype=DTYPE)
        self.inv_sqrt_C = torch.eye(n, dtype=DTYPE)

    @property
    def popsize(self) -> int:
        return self.lam

    def _eigen(self) -> None:
        self.C = torch.triu(self.C) + torch.triu(self.C, 1).T
        d2, self.B = torch.linalg.eigh(self.C)
        self.D = torch.sqrt(torch.clamp(d2, min=1e-20))
        self.inv_sqrt_C = self.B @ torch.diag(1.0 / self.D) @ self.B.T

    def ask(self) -> torch.Tensor:
        self._eigen()
        z = self.randn(self.lam, self.dim)
        y = (z * self.D) @ self.B.T
        return self.clip(self.mean + self.sigma * y)

    def _tell(self, xs: torch.Tensor, losses: torch.Tensor) -> None:
        n = self.dim
        order = torch.argsort(losses)
        old = self.mean.clone()
        y_sel = (xs[order[: self.mu]] - old) / self.sigma
        y_w = self.weights @ y_sel
        self.mean = old + self.sigma * y_w

        self.ps = (1 - self.cs) * self.ps + math.sqrt(self.cs * (2 - self.cs) * self.mueff) * (self.inv_sqrt_C @ y_w)
        ps_norm = float(torch.linalg.norm(self.ps))
        hsig = float(
            ps_norm / math.sqrt(1 - (1 - self.cs) ** (2 * (self.generation + 1))) / self.chi_n < 1.4 + 2 / (n + 1)
        )
        self.pc = (1 - self.cc) * self.pc + hsig * math.sqrt(self.cc * (2 - self.cc) * self.mueff) * y_w

        rank_mu = (y_sel.T * self.weights) @ y_sel
        self.C = (
            (1 - self.c1 - self.cmu) * self.C
            + self.c1 * (torch.outer(self.pc, self.pc) + (1 - hsig) * self.cc * (2 - self.cc) * self.C)
            + self.cmu * rank_mu
        )
        self.sigma *= math.exp((self.cs / self.damps) * (ps_norm / self.chi_n - 1))
        if self.bounds is not None:
            self.sigma = min(self.sigma, (self.bounds[1] - self.bounds[0]))

    def recommendation(self) -> torch.Tensor:
        return self.clip(self.mean.clone())

    def state(self) -> dict:
        s = super().state()
        s.update({"sigma": self.sigma, "cond": float(self.D.max() / self.D.min())})
        return s
