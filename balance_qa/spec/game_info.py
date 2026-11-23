"""게임이 describe 로 알려준 정보 (학습 쪽이 아는 게임 정보의 전부).

학습 쪽은 직업의 스킬·스탯을 모른다. 파라미터 이름·범위·기본값과 트리거·결과 형식만 안다.

**학습 대상 = 블록 가중치뿐** (SDK 규칙, 2026-11-23). 게임이 v1.3 `classes[].blocks` 로 선언한 가중치만
`learnable_space()` 에 들어간다. 가중치가 아닌 BT 값은 정의서 default 또는 페르소나가 정한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from balance_qa.spec.param import ParamDef, ParamSpace


WEIGHT_UNIT = "weight"


@dataclass(frozen=True)
class BlockInfo:
    """전략 선택 노드의 블록 (S = N × weight)."""

    name: str
    weight: str
    description: str = ""


@dataclass(frozen=True)
class ClassInfo:
    name: str
    display_name: str
    ranged: bool
    params: Dict[str, ParamDef]
    spec_version: str = ""
    blocks: Tuple[BlockInfo, ...] = ()
    #: 게임이 blocks 를 직접 선언했는지 (v1.3). False 면 unit == "weight" 인 bt 파라미터로 추정한 것
    blocks_declared: bool = False

    @classmethod
    def from_wire(cls, d: Mapping[str, Any]) -> "ClassInfo":
        params = [ParamDef.from_wire(p) for p in d["params"]]
        if "blocks" in d:
            blocks = tuple(BlockInfo(str(b["name"]), str(b["weight"]), str(b.get("description", ""))) for b in d["blocks"])
            declared = True
        else:  # v1.2 이하 게임: 가중치 단위 파라미터를 블록 가중치로 간주
            blocks = tuple(BlockInfo(p.name, p.name) for p in params if p.group == "bt" and p.unit == WEIGHT_UNIT)
            declared = False
        return cls(
            name=str(d["name"]),
            display_name=str(d.get("display_name", d["name"])),
            ranged=bool(d.get("ranged", False)),
            params={p.name: p for p in params},
            spec_version=str(d.get("spec_version", "")),
            blocks=blocks,
            blocks_declared=declared,
        )

    # ------------------------------------------------------------------ 학습 대상 (가중치만)
    @property
    def weight_names(self) -> List[str]:
        return [b.weight for b in self.blocks if b.weight in self.params]

    def is_weight(self, name: str) -> bool:
        return name in self.weight_names

    def learnable_space(self, names: Optional[Sequence[str]] = None) -> ParamSpace:
        """학습 대상 공간 = 블록 가중치 (블록 순서). names 를 주면 그 부분집합 — 가중치가 아니면 ValueError."""
        weights = self.weight_names
        if not weights:
            raise ValueError("%s: 게임이 블록 가중치를 선언하지 않아 학습할 것이 없음 (docs/PROTOCOL.md 4.2 blocks)" % self.name)
        if names is not None:
            bad = [n for n in names if n not in weights]
            if bad:
                raise ValueError("%s: %s 는 블록 가중치가 아니라 학습할 수 없음 (가중치: %s)"
                                 % (self.name, bad, ", ".join(weights)))
            weights = [w for w in weights if w in set(names)]
        return ParamSpace(self.params[w] for w in weights)

    def optimizable_space(self) -> ParamSpace:
        """= learnable_space() (이전 이름)."""
        return self.learnable_space()

    def bt_space(self) -> ParamSpace:
        """group bt 전체 (가중치 + 기획 설정값). 학습이 아니라 민감도 측정용."""
        return ParamSpace(p for p in self.params.values() if p.group == "bt")

    def default_params(self) -> Dict[str, float]:
        """게임 정의서 default = 개발팀 손 튜닝 값 (기준선)."""
        return {k: p.default for k, p in self.params.items()}

    def full_space(self) -> ParamSpace:
        return ParamSpace(self.params.values())

    def persona_param_names(self) -> List[str]:
        return [p.name for p in self.params.values() if p.group == "persona"]


@dataclass(frozen=True)
class GameDescription:
    protocol_version: str
    game: str
    game_version: str
    time_limit: float
    max_deaths: int
    classes: Dict[str, ClassInfo]
    scenarios: Tuple[str, ...]
    trigger_type: str
    trigger_supported: Tuple[float, ...]
    state_features: Tuple[str, ...]
    decision_interval: float = 0.0
    totals_fields: Tuple[str, ...] = ()   # v1.1: trigger.totals 키 (비어 있으면 구간 보상 불가)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    REQUIRED = ("protocol_version", "game", "time_limit", "max_deaths", "classes", "scenarios", "triggers")

    @classmethod
    def from_wire(cls, d: Mapping[str, Any]) -> "GameDescription":
        missing = [k for k in cls.REQUIRED if k not in d]
        if missing:
            raise ValueError("description 필수 필드 누락: %s" % missing)
        trig = d["triggers"]
        return cls(
            protocol_version=str(d["protocol_version"]),
            game=str(d["game"]),
            game_version=str(d.get("game_version", "")),
            time_limit=float(d["time_limit"]),
            max_deaths=int(d["max_deaths"]),
            classes={c["name"]: ClassInfo.from_wire(c) for c in d["classes"]},
            scenarios=tuple(s["name"] if isinstance(s, dict) else str(s) for s in d["scenarios"]),
            trigger_type=str(trig.get("type", "boss_hp_below")),
            trigger_supported=tuple(float(t) for t in trig.get("supported", [])),
            state_features=tuple(str(f) for f in trig.get("state_features", [])),
            decision_interval=float(d.get("decision_interval", 0.0)),
            totals_fields=tuple(str(f) for f in trig.get("totals", [])),
            raw=dict(d),
        )

    #: 구간 보상(IMPALA)에 필요한 누적값 키
    REQUIRED_TOTALS = ("elapsed", "deaths", "consumables_used")

    @property
    def supports_segment_rewards(self) -> bool:
        return all(k in self.totals_fields for k in self.REQUIRED_TOTALS)

    def class_info(self, name: str) -> ClassInfo:
        if name not in self.classes:
            raise KeyError("게임에 class %r 없음 (가능: %s)" % (name, ", ".join(self.classes)))
        return self.classes[name]

    def check_scenario(self, scenario: str) -> None:
        if scenario not in self.scenarios:
            raise KeyError("게임에 scenario %r 없음 (가능: %s)" % (scenario, ", ".join(self.scenarios)))
