"""시드 풀: 학습용과 평가용을 겹치지 않게 분리한다 (winner's curse 방지)."""
from __future__ import annotations

from typing import List


class SeedPool:
    def __init__(self, base: int, size: int, name: str = "") -> None:
        self.base = base
        self.size = size
        self.name = name

    def batch(self, index: int, k: int) -> List[int]:
        """index 번째 배치의 시드 k 개. 같은 index 는 항상 같은 시드 (공통 난수)."""
        start = (index * k) % self.size
        return [self.base + (start + i) % self.size for i in range(k)]

    def first(self, n: int) -> List[int]:
        return self.batch(0, n)

    def __contains__(self, seed: int) -> bool:
        return self.base <= seed < self.base + self.size

    def __repr__(self) -> str:
        return "SeedPool(%s: %d..%d)" % (self.name, self.base, self.base + self.size - 1)


TRAIN_SEEDS = SeedPool(0, 500_000, "train")
EVAL_SEEDS = SeedPool(1_000_000, 500_000, "eval")
