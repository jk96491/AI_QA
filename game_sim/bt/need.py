"""필요도 N 함수 (문서 7장, 개발팀 정의 식).

점수 S = N × w.  N 은 상태에 따라 매 결정마다 변하고, w 는 구간(또는 판) 내내 고정.
N 이 None 이면 그 블록은 후보에서 제외.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from game_sim.spec.skill_def import SkillRole

if TYPE_CHECKING:
    from game_sim.bt.blackboard import Blackboard


class NeedFunction(ABC):
    @abstractmethod
    def value(self, bb: "Blackboard") -> Optional[float]:
        ...


class BurstNeed(NeedFunction):
    """쿨 준비 시 0.8, 아니면 후보 제외."""

    BASE = 0.8

    @staticmethod
    def compute(burst_ready: bool) -> Optional[float]:
        return BurstNeed.BASE if burst_ready else None

    def value(self, bb: "Blackboard") -> Optional[float]:
        return self.compute(bb.any_available(SkillRole.BURST))


class DpsNeed(NeedFunction):
    """체력이 φ 아래면 딜 의지 감소: 0.5 × min(1, hp/φ). 적이 사거리 밖이면 제외."""

    BASE = 0.5

    @staticmethod
    def compute(hp: float, phi: float) -> float:
        return DpsNeed.BASE * min(1.0, hp / phi)

    def value(self, bb: "Blackboard") -> Optional[float]:
        assert bb.obs is not None
        if not bb.in_range(bb.spec.basic_skill):
            return None
        return self.compute(bb.obs.hp_ratio, bb.p("dps_hp_floor"))


class SurvivalNeed(NeedFunction):
    """체력이 θ 아래로 내려가면 상승: max(0, (θ − hp)/θ)."""

    @staticmethod
    def compute(hp: float, theta: float) -> float:
        return max(0.0, (theta - hp) / theta)

    def value(self, bb: "Blackboard") -> Optional[float]:
        assert bb.obs is not None
        return self.compute(bb.obs.hp_ratio, bb.p("survival_hp_threshold"))


def survival_switch_point(theta: float, phi: float, w_dps: float, w_survival: float, tol: float = 1e-6) -> float:
    """생존 S 가 딜 유지 S 를 넘는 체력 비율 (버스트 쿨 X 가정).

    문서 8장 예시: 안정형(θ .8, φ .7, w_dps .5, w_surv .9) → 약 0.61,
                  공격형(θ .3, φ .2, w_dps .7, w_surv .6) → 약 0.16.
    """

    def diff(hp: float) -> float:
        return w_survival * SurvivalNeed.compute(hp, theta) - w_dps * DpsNeed.compute(hp, phi)

    lo, hi = 1e-6, 1.0
    if diff(lo) <= 0:
        return 0.0
    if diff(hi) > 0:
        return 1.0
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if diff(mid) > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
