"""최적화기 공통 인터페이스 (PyTorch, CPU, 손실 최소화 기준)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence, Tuple, Union

import torch

from balance_qa.backend import DTYPE, as_tensor, generator

TensorLike = Union[torch.Tensor, Sequence[float]]


class Optimizer(ABC):
    """블랙박스 최적화기. 손실(= −보상)을 최소화한다.

    - ask()            : 평가할 후보 텐서 (popsize, dim), float64, CPU
    - tell(xs, losses) : 평가 결과 반영
    - recommendation() : 최종 추천 벡터. 노이즈가 있는 환경이라 '가장 운 좋았던 후보'가 아니라
                         분포 평균(CMA-ES·ES) 을 기본으로 쓴다 (winner's curse 완화)
    """

    name = "optimizer"

    def __init__(self, dim: int, seed: int = 0, bounds: Optional[Tuple[float, float]] = (0.0, 1.0)) -> None:
        self.dim = dim
        self.gen = generator(seed)
        self.bounds = bounds
        self.generation = 0
        self.best_x: Optional[torch.Tensor] = None
        self.best_loss = float("inf")

    @property
    @abstractmethod
    def popsize(self) -> int:
        ...

    @abstractmethod
    def ask(self) -> torch.Tensor:
        ...

    @abstractmethod
    def _tell(self, xs: torch.Tensor, losses: torch.Tensor) -> None:
        ...

    @abstractmethod
    def recommendation(self) -> torch.Tensor:
        ...

    def tell(self, xs: TensorLike, losses: TensorLike) -> None:
        xs_t = torch.stack([as_tensor(x) for x in xs]) if not isinstance(xs, torch.Tensor) else as_tensor(xs)
        loss_t = as_tensor(losses)
        i = int(torch.argmin(loss_t))
        if float(loss_t[i]) < self.best_loss:
            self.best_loss = float(loss_t[i])
            self.best_x = xs_t[i].clone()
        self._tell(xs_t, loss_t)
        self.generation += 1

    def clip(self, x: torch.Tensor) -> torch.Tensor:
        if self.bounds is None:
            return x
        return torch.clamp(x, self.bounds[0], self.bounds[1])

    def randn(self, *shape: int) -> torch.Tensor:
        return torch.randn(*shape, generator=self.gen, dtype=DTYPE)

    def state(self) -> dict:
        return {"name": self.name, "generation": self.generation, "best_loss": self.best_loss}
