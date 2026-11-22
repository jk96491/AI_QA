"""후보 텐서 → ParamSource 변환기.

같은 학습 루프(Trainer)로 '판당 1회 파라미터'와 '트리거 정책'을 모두 학습하기 위한 어댑터.
최적화기는 torch 텐서를, 시뮬레이터 쪽(ParamSpace·BT)은 numpy/float 를 쓰므로 경계에서 변환한다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Mapping, Optional, Sequence

import torch

from balance_qa.backend import as_tensor, to_numpy
from balance_qa.control.param_source import ParamSource, PolicyParamSource, StaticParamSource
from balance_qa.policy.mlp import MLPPolicy
from balance_qa.spec.param import ParamSpace


class CandidateDecoder(ABC):
    @property
    @abstractmethod
    def dim(self) -> int:
        ...

    @abstractmethod
    def x0(self) -> torch.Tensor:
        """탐색 시작점."""

    @abstractmethod
    def decode(self, x: torch.Tensor) -> ParamSource:
        ...

    @property
    def bounded(self) -> bool:
        return True


class StaticDecoder(CandidateDecoder):
    """x ∈ [0,1]^d → 고정 파라미터 (판당 1회 결정)."""

    def __init__(self, space: ParamSpace, fixed: Mapping[str, float]) -> None:
        self.space = space
        self.fixed = dict(fixed)

    @property
    def dim(self) -> int:
        return self.space.dim

    def x0(self) -> torch.Tensor:
        start = {d.name: d.default for d in self.space.defs}
        start.update({k: v for k, v in self.fixed.items() if k in start})
        return as_tensor(self.space.encode(start))

    def params(self, x: torch.Tensor) -> Dict[str, float]:
        out = dict(self.fixed)
        out.update(self.space.decode(to_numpy(x)))
        return out

    def decode(self, x: torch.Tensor) -> ParamSource:
        return StaticParamSource(self.params(x))


class PolicyDecoder(CandidateDecoder):
    """x = MLP 가중치 → 트리거마다 파라미터를 내는 정책."""

    def __init__(
        self,
        space: ParamSpace,
        fixed: Mapping[str, float],
        thresholds: Sequence[float],
        n_features: int,
        hidden: Sequence[int] = (16,),
        seed: int = 0,
        init_params: Optional[Mapping[str, float]] = None,
    ) -> None:
        self.space = space
        self.fixed = dict(fixed)
        self.thresholds = tuple(thresholds)
        # 정책 입력 = 게임 describe 의 triggers.state_features (게임이 0~1 정규화해서 보냄)
        self.template = MLPPolicy(n_features, space.dim, hidden, seed=seed)
        start = {d.name: d.default for d in space.defs}
        if init_params:
            start.update({k: v for k, v in init_params.items() if k in start})
        self.template.set_output_bias(space.encode(start))

    @property
    def dim(self) -> int:
        return self.template.n_params

    @property
    def bounded(self) -> bool:
        return False

    def x0(self) -> torch.Tensor:
        return self.template.get_flat()

    def decode(self, x: torch.Tensor) -> ParamSource:
        return PolicyParamSource(self.template.with_flat(x), self.space, self.fixed, self.thresholds)
