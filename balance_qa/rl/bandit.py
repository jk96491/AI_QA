"""IMPALA 컨텍스트 밴딧 — 판 시작에 한 번, 상황(컨텍스트)을 보고 블록 가중치를 고른다 (docs/BANDIT_IMPALA_DESIGN.md).

    컨텍스트 c = (직업, 시나리오, 판 시작 상태)  ──π(w | c)──►  블록 가중치 w  ──판 1회──►  보상 R

- 판 하나 = 길이 1 궤적 (Step 1개, 보상 = 판 전체 보상). 학습기(V-trace)·모델·배치는 트리거 구간 모드와 같은 코드를 쓴다.
- 판 시작 상태는 프로토콜 v1.4 `run_episode.initial_state` 로 보낸다 (게임이 describe.initial_state 로 선언한 키만).
- 트리거를 쓰지 않는다: 학습 쪽이 컨텍스트를 이미 알기 때문에 가중치를 run_episode.params 로 바로 보낸다.

확장 지점: ContextSampler (학습 판 분포). 지금 구현 MixedContextSampler (full 시작 p_full + 범위 균등/이산 단계).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from balance_qa.control.param_source import ParamSource
from balance_qa.core.types import TriggerState
from balance_qa.rl.model import U_EPS, ActorCritic
from balance_qa.rl.trajectory import Step
from balance_qa.spec.param import ParamSpace

Combo = Tuple[str, str]   # (class, scenario)


@dataclass(frozen=True)
class ContextCell:
    """컨텍스트 하나. initial_state None = 판 시작 가득 (v1.3 과 같은 판)."""

    class_name: str
    scenario: str
    initial_state: Optional[Tuple[Tuple[str, float], ...]] = None

    @classmethod
    def make(cls, class_name: str, scenario: str, state: Optional[Mapping[str, float]] = None) -> "ContextCell":
        st = tuple(sorted((k, float(v)) for k, v in state.items())) if state else None
        return cls(class_name, scenario, st)

    def state_dict(self) -> Optional[Dict[str, float]]:
        return dict(self.initial_state) if self.initial_state else None

    @property
    def label(self) -> str:
        st = ",".join("%s=%.2f" % kv for kv in self.initial_state) if self.initial_state else "full"
        return "%s/%s[%s]" % (self.class_name, self.scenario, st)


@dataclass(frozen=True)
class StateRange:
    name: str
    low: float
    high: float
    default: float
    levels: Optional[Tuple[float, ...]] = None   # 주면 이 값들 중에서만 고른다 (예: 물약 0, 1/3, 2/3, 1)

    def to_wire(self) -> Dict[str, Any]:
        return {"name": self.name, "low": self.low, "high": self.high, "default": self.default,
                "levels": list(self.levels) if self.levels is not None else None}

    @classmethod
    def from_wire(cls, d: Mapping[str, Any]) -> "StateRange":
        lv = d.get("levels")
        return cls(str(d["name"]), float(d["low"]), float(d["high"]), float(d["default"]),
                   tuple(float(x) for x in lv) if lv is not None else None)


class ContextEncoder:
    """컨텍스트 → 정책 입력 벡터: [직업 원-핫] + [시나리오 원-핫] + [시작 상태 값 (state 순서, 없으면 default)]."""

    def __init__(self, classes: Sequence[str], scenarios: Sequence[str], states: Sequence[StateRange]) -> None:
        self.classes = list(classes)
        self.scenarios = list(scenarios)
        self.states = list(states)

    @property
    def dim(self) -> int:
        return len(self.classes) + len(self.scenarios) + len(self.states)

    def encode(self, class_name: str, scenario: str, state: Optional[Mapping[str, float]] = None) -> np.ndarray:
        if class_name not in self.classes or scenario not in self.scenarios:
            raise KeyError("컨텍스트 밖: %s/%s (학습한 직업 %s, 시나리오 %s)" % (class_name, scenario, self.classes, self.scenarios))
        x = np.zeros(self.dim)
        x[self.classes.index(class_name)] = 1.0
        x[len(self.classes) + self.scenarios.index(scenario)] = 1.0
        st = state or {}
        off = len(self.classes) + len(self.scenarios)
        for i, s in enumerate(self.states):
            x[off + i] = float(st.get(s.name, s.default))
        return x

    def encode_cell(self, cell: ContextCell) -> np.ndarray:
        return self.encode(cell.class_name, cell.scenario, cell.state_dict())

    def to_wire(self) -> Dict[str, Any]:
        return {"classes": self.classes, "scenarios": self.scenarios, "states": [s.to_wire() for s in self.states],
                "layout": "class_onehot + scenario_onehot + states"}

    @classmethod
    def from_wire(cls, d: Mapping[str, Any]) -> "ContextEncoder":
        return cls(d["classes"], d["scenarios"], [StateRange.from_wire(s) for s in d["states"]])


class ContextSampler(ABC):
    """학습 판 분포 (확장 지점). 같은 rng → 같은 컨텍스트."""

    @abstractmethod
    def sample(self, rng: np.random.Generator) -> ContextCell:
        ...

    @abstractmethod
    def to_wire(self) -> Dict[str, Any]:
        ...

    @staticmethod
    def from_wire(d: Mapping[str, Any]) -> "ContextSampler":
        if d.get("type") == "mixed":
            return MixedContextSampler.from_wire(d)
        raise ValueError("모르는 ContextSampler %r" % d.get("type"))


class MixedContextSampler(ContextSampler):
    """조합 균등 × 시작 상태 혼합: 확률 p_full 로 가득 찬 시작(initial_state 없음), 아니면 키마다 범위 균등(또는 levels 중 하나)."""

    def __init__(self, combos: Sequence[Combo], states: Sequence[StateRange], p_full: float = 0.4) -> None:
        if not combos:
            raise ValueError("combos 가 비어 있음")
        if not 0.0 <= p_full <= 1.0:
            raise ValueError("p_full 은 0~1")
        self.combos = [tuple(c) for c in combos]
        self.states = list(states)
        self.p_full = float(p_full)

    def sample(self, rng: np.random.Generator) -> ContextCell:
        cls, sc = self.combos[int(rng.integers(len(self.combos)))]
        if not self.states or rng.random() < self.p_full:
            return ContextCell(cls, sc, None)
        st = {}
        for s in self.states:
            if s.levels:
                st[s.name] = float(s.levels[int(rng.integers(len(s.levels)))])
            else:
                st[s.name] = float(rng.uniform(s.low, s.high))
        return ContextCell.make(cls, sc, st)

    def to_wire(self) -> Dict[str, Any]:
        return {"type": "mixed", "combos": [list(c) for c in self.combos], "states": [s.to_wire() for s in self.states],
                "p_full": self.p_full}

    @classmethod
    def from_wire(cls, d: Mapping[str, Any]) -> "MixedContextSampler":
        return cls([tuple(c) for c in d["combos"]], [StateRange.from_wire(s) for s in d["states"]], float(d["p_full"]))


@dataclass
class BanditSetup:
    """학습기 → 액터로 보내는 밴딧 설정 (ActorSpec.extra["bandit"])."""

    encoder: ContextEncoder
    sampler: ContextSampler
    fixed_by_class: Dict[str, Dict[str, float]]    # 직업별 판 파라미터 (default + 페르소나, 가중치는 정책이 덮어씀)

    def to_wire(self) -> Dict[str, Any]:
        return {"encoder": self.encoder.to_wire(), "sampler": self.sampler.to_wire(),
                "fixed_by_class": {k: dict(v) for k, v in self.fixed_by_class.items()}}

    @classmethod
    def from_wire(cls, d: Mapping[str, Any]) -> "BanditSetup":
        return cls(ContextEncoder.from_wire(d["encoder"]), ContextSampler.from_wire(d["sampler"]),
                   {k: {n: float(x) for n, x in v.items()} for k, v in d["fixed_by_class"].items()})

    def cells_grid(self, levels: Optional[Mapping[str, Sequence[float]]] = None, include_full: bool = True) -> List[ContextCell]:
        """평가 격자: 조합 × (full + 상태 키별 levels 의 곱)."""
        combos = getattr(self.sampler, "combos", None) or [(c, s) for c in self.encoder.classes for s in self.encoder.scenarios]
        states = self.encoder.states
        grids: List[Dict[str, float]] = [{}]
        for s in states:
            vals = list((levels or {}).get(s.name) or s.levels or (s.low, s.high))
            grids = [dict(g, **{s.name: float(v)}) for g in grids for v in vals]
        out: List[ContextCell] = []
        for cls, sc in combos:
            if include_full:
                out.append(ContextCell(cls, sc, None))
            if states:
                out += [ContextCell.make(cls, sc, g) for g in grids]
        return out


class BanditParamSource(ParamSource):
    """컨텍스트 하나에 대해 정책으로 가중치를 정해 run_episode.params 로 보낸다 (트리거 없음).

    rng 가 있으면 샘플링(학습 행동 정책, Step 기록), 없으면 Beta 평균(평가·결정론적).
    """

    trigger_thresholds: Tuple[float, ...] = ()

    def __init__(self, model: ActorCritic, space: ParamSpace, setup: BanditSetup, cell: ContextCell,
                 rng: Optional[np.random.Generator] = None) -> None:
        self.model = model
        self.space = space
        self.setup = setup
        self.cell = cell
        self.obs = setup.encoder.encode_cell(cell)
        u, logp, value = model.act(self.obs, rng)
        self.step = Step(0, self.obs, u, logp, {}, value)   # totals {} → 보상 = 판 전체 보상
        self.weights = space.decode(u)
        if cell.class_name not in setup.fixed_by_class:
            raise KeyError("fixed_by_class 에 %s 없음" % cell.class_name)
        self.params = dict(setup.fixed_by_class[cell.class_name], **self.weights)

    def base_params(self) -> Dict[str, float]:
        return dict(self.params)

    def on_trigger(self, state: TriggerState) -> Dict[str, float]:   # 트리거를 요청하지 않으므로 오지 않는다
        return {}

    def describe(self) -> Dict[str, object]:
        """policy.json 의 source — play_agent BanditPolicy(numpy) 가 다시 쓰는 데 필요한 것 전부."""
        return bandit_policy_source(self.model, self.space, self.setup)


def bandit_policy_source(model: ActorCritic, space: ParamSpace, setup: BanditSetup) -> Dict[str, object]:
    """policy_theta 순서는 트리거 구간 모드와 같다 (torso → pi_head → v_head, weight 행 우선 다음 bias)."""
    return {
        "type": "impala-bandit",
        "mode": "mean",
        "model": repr(model),
        "outputs": space.names,
        "output_ranges": [[p.low, p.high] for p in space.defs],
        "obs_dim": model.obs_dim,
        "hidden": list(model.hidden),
        "activation": "tanh",
        "u_eps": U_EPS,
        "context": setup.encoder.to_wire(),
        "sampler": setup.sampler.to_wire(),
        "fixed_by_class": {k: dict(v) for k, v in setup.fixed_by_class.items()},
        "decision": "판 시작 1회 (run_episode.params). 플레이 모드: 트리거 index 0 에 답하고 이후는 {} (그대로)",
    }
