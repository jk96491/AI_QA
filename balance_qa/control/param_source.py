"""BT 파라미터 공급자 (학습 쪽). 게임에 보낼 숫자를 정한다.

- StaticParamSource : run_episode.params 로 1번 보내고 끝 (판당 1회 결정)
- PolicyParamSource : run_episode 에 트리거를 요청하고, trigger 메시지마다 정책이 파라미터로 응답 (9장)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, Mapping, Sequence, Tuple

from balance_qa.core.types import TriggerState
from balance_qa.spec.param import ParamSpace

if TYPE_CHECKING:  # torch 는 정책을 쓸 때만 로드
    from balance_qa.policy.mlp import MLPPolicy


class ParamSource(ABC):
    #: 보스 체력 비율 트리거 (내림차순). 비어 있으면 판당 1회 결정.
    trigger_thresholds: Tuple[float, ...] = ()

    @abstractmethod
    def base_params(self) -> Dict[str, float]:
        """run_episode.params (판 시작 파라미터)."""

    def on_trigger(self, state: TriggerState) -> Dict[str, float]:
        """trigger_response.params (부분 덮어쓰기). 기본: 변경 없음."""
        return {}

    def describe(self) -> Dict[str, object]:
        return {"type": type(self).__name__}


class StaticParamSource(ParamSource):
    def __init__(self, params: Mapping[str, float]) -> None:
        self.params: Dict[str, float] = dict(params)

    def base_params(self) -> Dict[str, float]:
        return dict(self.params)

    def describe(self) -> Dict[str, object]:
        return {"type": "static", "params": dict(self.params)}


class PolicyParamSource(ParamSource):
    def __init__(
        self,
        policy: "MLPPolicy",
        space: ParamSpace,
        fixed: Mapping[str, float],
        thresholds: Sequence[float],
    ) -> None:
        self.policy = policy
        self.space = space
        self.fixed = dict(fixed)
        self.trigger_thresholds = tuple(sorted(thresholds, reverse=True))

    def base_params(self) -> Dict[str, float]:
        return dict(self.fixed)

    def on_trigger(self, state: TriggerState) -> Dict[str, float]:
        u = self.policy.act(state.to_vector())
        return self.space.decode(u)

    def describe(self) -> Dict[str, object]:
        return {
            "type": "policy",
            "policy": repr(self.policy),
            "outputs": self.space.names,
            "thresholds": list(self.trigger_thresholds),
        }
