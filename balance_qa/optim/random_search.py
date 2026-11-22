"""무작위 탐색 (기준선, PyTorch)."""
from __future__ import annotations

from typing import Optional

import torch

from balance_qa.backend import DTYPE, as_tensor
from balance_qa.optim.base import Optimizer


class RandomSearch(Optimizer):
    name = "random"

    def __init__(self, dim: int, popsize: int = 12, seed: int = 0, x0=None) -> None:
        super().__init__(dim, seed=seed, bounds=(0.0, 1.0))
        self._popsize = popsize
        self.x0: Optional[torch.Tensor] = None if x0 is None else as_tensor(x0)

    @property
    def popsize(self) -> int:
        return self._popsize

    def ask(self) -> torch.Tensor:
        xs = torch.rand(self._popsize, self.dim, generator=self.gen, dtype=DTYPE)
        if self.generation == 0 and self.x0 is not None:
            xs[0] = self.x0
        return xs

    def _tell(self, xs: torch.Tensor, losses: torch.Tensor) -> None:
        pass

    def recommendation(self) -> torch.Tensor:
        assert self.best_x is not None, "tell() 을 먼저 호출해야 함"
        return self.best_x.clone()
