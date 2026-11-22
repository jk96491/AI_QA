"""BT 파라미터 정의(게임이 describe 로 공개)와 최적화용 정규화 공간."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping

import numpy as np


@dataclass(frozen=True)
class ParamDef:
    name: str
    low: float
    high: float
    default: float
    optimize: bool = True
    group: str = "bt"     # bt: 학습 대상 / persona: 페르소나가 정하는 N 설정값
    unit: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, name: str, d: Mapping[str, Any]) -> "ParamDef":
        low, high = d["range"]
        group = str(d.get("group", "bt"))
        return cls(
            name=name,
            low=float(low),
            high=float(high),
            default=float(d["default"]),
            optimize=bool(d.get("optimize", group == "bt")),
            group=group,
            unit=str(d.get("unit", "")),
            description=str(d.get("description", "")),
        )

    @classmethod
    def from_wire(cls, d: Mapping[str, Any]) -> "ParamDef":
        """describe 응답의 classes[].params[] 항목."""
        return cls.from_dict(str(d["name"]), d)

    @property
    def span(self) -> float:
        return self.high - self.low

    def clip(self, value: float) -> float:
        return float(min(self.high, max(self.low, value)))

    def to_unit(self, value: float) -> float:
        return 0.0 if self.span == 0 else (self.clip(value) - self.low) / self.span

    def from_unit(self, u: float) -> float:
        u = float(min(1.0, max(0.0, u)))
        return self.low + u * self.span


class ParamSpace:
    """최적화 대상 파라미터를 [0, 1]^d 벡터와 상호 변환한다."""

    def __init__(self, defs: Iterable[ParamDef]) -> None:
        self.defs: List[ParamDef] = list(defs)
        self.names: List[str] = [d.name for d in self.defs]

    @property
    def dim(self) -> int:
        return len(self.defs)

    def decode(self, x: np.ndarray) -> Dict[str, float]:
        x = np.asarray(x, dtype=float)
        if x.shape != (self.dim,):
            raise ValueError("vector dim %s != space dim %d" % (x.shape, self.dim))
        return {d.name: d.from_unit(float(v)) for d, v in zip(self.defs, x)}

    def encode(self, params: Mapping[str, float]) -> np.ndarray:
        return np.array([d.to_unit(params[d.name]) for d in self.defs], dtype=float)

    def default_vector(self) -> np.ndarray:
        return np.array([d.to_unit(d.default) for d in self.defs], dtype=float)

    def subset(self, names: Iterable[str]) -> "ParamSpace":
        wanted = set(names)
        return ParamSpace(d for d in self.defs if d.name in wanted)

    def __repr__(self) -> str:
        return "ParamSpace(%s)" % ", ".join(self.names)
