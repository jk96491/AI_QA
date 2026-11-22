"""페르소나별 보상 함수.

R = −(소요 분) − λ_death · 사망 − λ_consumable · 소모품 − F_fail · [클리어 실패]

- 식은 하나이고 λ 만 페르소나별로 다르다 (문서 8장).
- F_fail(분)은 원문 8장에 없는 항 (2026-11-22 결정 A). 없으면 λ_death 가 큰 페르소나가
  '여러 번 죽고 깨기'보다 '안 죽고 시간 초과'를 택한다. 멈춘 판(stalled)도 실패라 포함.
- 소요 시간은 중도절단 처리된 effective_time 을 쓴다 (실패 판도 진행도만큼 신호가 남음).
- 단위가 '분'이라 "사망 1회 = λ 분 손해"로 해석 가능.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence

import numpy as np

from balance_qa.core.types import EpisodeResult
from balance_qa.spec.persona import Persona

INVALID_PENALTY = -1e3


@dataclass(frozen=True)
class RewardBreakdown:
    time_term: float
    death_term: float
    consumable_term: float
    fail_term: float = 0.0

    @property
    def total(self) -> float:
        return self.time_term + self.death_term + self.consumable_term + self.fail_term

    def as_dict(self) -> Dict[str, float]:
        return {
            "time": self.time_term,
            "death": self.death_term,
            "consumable": self.consumable_term,
            "fail": self.fail_term,
            "total": self.total,
        }


class RewardFunction:
    def __init__(self, persona: Persona, time_limit: float) -> None:
        self.persona = persona
        self.time_limit = time_limit

    def breakdown(self, r: EpisodeResult) -> RewardBreakdown:
        minutes = r.effective_time(self.time_limit) / 60.0
        return RewardBreakdown(
            time_term=-minutes,
            death_term=-self.persona.lambda_death * r.deaths,
            consumable_term=-self.persona.lambda_consumable * r.consumables_used,
            fail_term=0.0 if r.cleared else -self.persona.fail_penalty,
        )

    def __call__(self, r: EpisodeResult) -> float:
        if r.invalid:
            return INVALID_PENALTY
        return self.breakdown(r).total

    def mean(self, results: Sequence[EpisodeResult]) -> float:
        """무효 판은 제외한 평균. 전부 무효면 벌점."""
        valid = [self(r) for r in results if not r.invalid]
        return float(np.mean(valid)) if valid else INVALID_PENALTY

    def mean_breakdown(self, results: Sequence[EpisodeResult]) -> Dict[str, float]:
        valid = [self.breakdown(r).as_dict() for r in results if not r.invalid]
        if not valid:
            return {}
        return {k: float(np.mean([v[k] for v in valid])) for k in valid[0]}
