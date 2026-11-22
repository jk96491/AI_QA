"""게임 정의서의 BT 파라미터 정의 (타입·범위·단위·의미). describe 응답으로 학습 쪽에 공개된다."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping

PARAM_GROUPS = ("bt", "persona")


@dataclass(frozen=True)
class ParamDef:
    name: str
    low: float
    high: float
    default: float
    optimize: bool = True
    group: str = "bt"          # bt: 학습 대상 BT 값 / persona: 페르소나가 정하는 N 설정값
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

    @property
    def span(self) -> float:
        return self.high - self.low

    def contains(self, value: float, tol: float = 1e-9) -> bool:
        return self.low - tol <= value <= self.high + tol

    def to_wire(self) -> Dict[str, Any]:
        d = asdict(self)
        d["range"] = [d.pop("low"), d.pop("high")]
        return d
