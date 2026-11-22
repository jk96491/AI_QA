"""페르소나 정의 (문서 8장 정의 채택).

페르소나 = 필요도 N 설정값(θ, φ) + 보상 계수(λ).
가중치 w 는 페르소나가 아니라 최적화가 정한다.
fail_penalty 는 페르소나 공통값 (personas.json 최상위 `fail_penalty`, 페르소나별 덮어쓰기 가능).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

#: 클리어 실패 벌점(분) 기본값. 0.4.0 안정형 전사가 '안 죽고 시간 초과'로 클리어를 포기한 문제 대응 (2026-11-22 결정 A)
DEFAULT_FAIL_PENALTY = 30.0


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    survival_hp_threshold: float  # θ: 생존 필요도가 오르기 시작하는 체력 비율
    dps_hp_floor: float           # φ: 이 체력 아래에서 딜 의지가 줄어듦
    lambda_death: float           # 사망 1회 = λ 분
    lambda_consumable: float      # 소모품 1개 = λ 분
    description: str = ""
    fail_penalty: float = DEFAULT_FAIL_PENALTY  # 클리어 실패 1판 = 이 분만큼 추가 손해 (원문 8장에 없음)

    def need_params(self) -> Dict[str, float]:
        """BT 블랙보드에 들어갈 페르소나 설정값."""
        return {
            "survival_hp_threshold": self.survival_hp_threshold,
            "dps_hp_floor": self.dps_hp_floor,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Persona":
        return cls(**d)
