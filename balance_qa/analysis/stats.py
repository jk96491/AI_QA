"""통계 유틸리티 (scipy 없이 numpy 만 사용)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Tuple

import numpy as np

Z_975 = 1.959963984540054
Z_80 = 0.8416212335729143


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float

    def fmt(self, digits: int = 1, scale: float = 1.0) -> str:
        f = "%%.%df" % digits
        return (f + " [" + f + ", " + f + "]") % (self.estimate * scale, self.low * scale, self.high * scale)

    def as_dict(self) -> dict:
        return {"estimate": self.estimate, "low": self.low, "high": self.high}


class Stats:
    @staticmethod
    def bootstrap_mean(values: Sequence[float], n_boot: int = 2000, alpha: float = 0.05, seed: int = 0) -> Interval:
        x = np.asarray(values, dtype=float)
        if x.size == 0:
            return Interval(float("nan"), float("nan"), float("nan"))
        if x.size == 1:
            return Interval(float(x[0]), float(x[0]), float(x[0]))
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, x.size, size=(n_boot, x.size))
        means = x[idx].mean(axis=1)
        lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
        return Interval(float(x.mean()), float(lo), float(hi))

    @staticmethod
    def wilson(successes: int, n: int, z: float = Z_975) -> Interval:
        if n == 0:
            return Interval(float("nan"), float("nan"), float("nan"))
        p = successes / n
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
        return Interval(p, max(0.0, center - half), min(1.0, center + half))

    @staticmethod
    def welch(a: Sequence[float], b: Sequence[float]) -> Tuple[float, float, float]:
        """Welch t 검정. (t, df, 양측 p) — p 는 정규 근사 (표본이 충분히 클 때 유효)."""
        x, y = np.asarray(a, float), np.asarray(b, float)
        va, vb = x.var(ddof=1) / x.size, y.var(ddof=1) / y.size
        se = math.sqrt(va + vb)
        if se == 0:
            return 0.0, float("inf"), 1.0
        t = (x.mean() - y.mean()) / se
        df = (va + vb) ** 2 / (va ** 2 / (x.size - 1) + vb ** 2 / (y.size - 1))
        p = math.erfc(abs(t) / math.sqrt(2))
        return float(t), float(df), float(p)

    @staticmethod
    def cohen_d(a: Sequence[float], b: Sequence[float]) -> float:
        x, y = np.asarray(a, float), np.asarray(b, float)
        pooled = math.sqrt(((x.size - 1) * x.var(ddof=1) + (y.size - 1) * y.var(ddof=1)) / (x.size + y.size - 2))
        return 0.0 if pooled == 0 else float((x.mean() - y.mean()) / pooled)

    @staticmethod
    def cv(values: Sequence[float]) -> float:
        x = np.asarray(values, float)
        return float(x.std(ddof=1) / x.mean()) if x.size > 1 and x.mean() != 0 else float("nan")

    @staticmethod
    def required_n(cv: float, delta: float, z_alpha: float = Z_975, z_beta: float = Z_80) -> int:
        """두 조건 평균의 상대 차이 delta 를 검출하는 데 필요한 조건당 판수.

        n ≈ 2 (z_α/2 + z_β)² CV² / δ²   (예: CV 0.10, δ 0.03 → 175)
        """
        if delta <= 0:
            raise ValueError("delta > 0")
        return int(math.ceil(2 * (z_alpha + z_beta) ** 2 * cv * cv / (delta * delta)))
