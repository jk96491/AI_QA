"""ActorSpec: 액터가 판을 돌리는 데 필요한 모든 설정 (학습기 → 액터로 전송).

액터 프로세스는 이 설정만으로 정책 모델·파라미터 공간·보상 함수를 재구성한다.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Tuple

from balance_qa.reward.reward import RewardFunction
from balance_qa.rl.model import ActorCritic
from balance_qa.spec.param import ParamDef, ParamSpace
from balance_qa.spec.persona import Persona


@dataclass
class ActorSpec:
    class_name: str
    scenario: str
    params: List[ParamDef]            # 정책 출력 파라미터 정의 (순서 = 행동 차원)
    fixed: Dict[str, float]           # run_episode.params (판 시작 파라미터)
    thresholds: Tuple[float, ...]     # 트리거 경계
    obs_dim: int
    act_dim: int
    hidden: Tuple[int, ...]
    persona: Dict[str, Any]
    time_limit: float
    state_features: Tuple[str, ...]
    sample_seed: int = 0
    game: str = ""
    game_version: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    # ----- 재구성 -----
    def space(self) -> ParamSpace:
        return ParamSpace(self.params)

    def reward_fn(self) -> RewardFunction:
        return RewardFunction(Persona.from_dict(self.persona), self.time_limit)

    def new_model(self) -> ActorCritic:
        return ActorCritic(self.obs_dim, self.act_dim, self.hidden, seed=0)

    # ----- 직렬화 -----
    def to_wire(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["thresholds"] = list(self.thresholds)
        d["hidden"] = list(self.hidden)
        d["state_features"] = list(self.state_features)
        return d

    @classmethod
    def from_wire(cls, d: Mapping[str, Any]) -> "ActorSpec":
        kw = dict(d)
        kw["params"] = [ParamDef(**p) for p in d["params"]]
        kw["thresholds"] = tuple(float(t) for t in d["thresholds"])
        kw["hidden"] = tuple(int(h) for h in d["hidden"])
        kw["state_features"] = tuple(d["state_features"])
        return cls(**kw)
