"""페르소나 정의.

페르소나 = BT 설정값(`params`) + 보상 계수(λ, fail_penalty). 원문 8장과 완전히 같을 필요는 없다 (사용자 결정 2026-11-23).
- `params`: 게임 정의서의 **가중치가 아닌** 파라미터만 정할 수 있다 — 필요도 설정값(θ, φ) 뿐 아니라
  물약 체력 같은 행동 임계값도 페르소나 성격으로 둘 수 있다. 정하지 않은 값은 정의서 default(손 튜닝 값).
- 블록 가중치 w 는 페르소나가 정하지 않는다. 학습(CMA-ES·IMPALA)이 정하는 유일한 값이다.
- fail_penalty 는 페르소나 공통값 (personas.json 최상위 `fail_penalty`, 페르소나별 덮어쓰기 가능).

호환: 예전 형식의 최상위 `survival_hp_threshold`, `dps_hp_floor` 는 `params` 로 옮겨 읽는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

#: 클리어 실패 벌점(분) 기본값. 0.4.0 안정형 전사가 '안 죽고 시간 초과'로 클리어를 포기한 문제 대응 (2026-11-22 결정 A)
DEFAULT_FAIL_PENALTY = 30.0

#: 예전 personas.json 의 최상위 설정값 키 (params 로 옮겨 읽음)
LEGACY_PARAM_KEYS = ("survival_hp_threshold", "dps_hp_floor")


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    lambda_death: float           # 사망 1회 = λ 분
    lambda_consumable: float      # 소모품 1개 = λ 분
    params: Dict[str, float] = field(default_factory=dict)   # BT 설정값 (가중치 제외)
    description: str = ""
    fail_penalty: float = DEFAULT_FAIL_PENALTY  # 클리어 실패 1판 = 이 분만큼 추가 손해 (원문 8장에 없음)

    def settings(self) -> Dict[str, float]:
        """BT 블랙보드에 들어갈 페르소나 설정값."""
        return dict(self.params)

    def need_params(self) -> Dict[str, float]:
        """= settings() (이전 이름)."""
        return self.settings()

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Persona":
        d = dict(d)
        params = {str(k): float(v) for k, v in dict(d.pop("params", {}) or {}).items()}
        for key in LEGACY_PARAM_KEYS:
            if key in d:
                params.setdefault(key, float(d.pop(key)))
        known = {"id", "name", "lambda_death", "lambda_consumable", "description", "fail_penalty"}
        unknown = sorted(set(d) - known)
        if unknown:
            raise ValueError("persona %r: 알 수 없는 필드 %s (BT 설정값은 params 안에)" % (d.get("id"), unknown))
        return cls(
            id=str(d["id"]),
            name=str(d.get("name", d["id"])),
            lambda_death=float(d.get("lambda_death", 0.0)),
            lambda_consumable=float(d.get("lambda_consumable", 0.0)),
            params=params,
            description=str(d.get("description", "")),
            fail_penalty=float(d.get("fail_penalty", DEFAULT_FAIL_PENALTY)),
        )
