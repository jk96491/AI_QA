"""학습 플랫폼 쪽 타입. 게임과는 프로토콜 JSON 으로만 주고받는다 (docs/PROTOCOL.md)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

EPS = 1e-9


class GameError(RuntimeError):
    """게임이 error 메시지로 응답했을 때."""

    def __init__(self, code: str, message: str, episode_id: Optional[str] = None) -> None:
        super().__init__("[%s] %s" % (code, message))
        self.code = code
        self.message = message
        self.episode_id = episode_id


@dataclass
class TriggerState:
    """결정 트리거 시점에 게임이 보낸 상태 (trigger.state). 키 순서는 describe 의 state_features.

    totals: 판 시작부터의 누적값 (프로토콜 v1.1 trigger.totals) — 구간 보상 계산용. 구버전 게임이면 빈 dict.
    """

    index: int
    state: Dict[str, float]
    features: Sequence[str]
    totals: Dict[str, float] = field(default_factory=dict)

    def to_vector(self) -> np.ndarray:
        return np.array([float(self.state.get(k, 0.0)) for k in self.features], dtype=float)


@dataclass
class EpisodeResult:
    """판 하나의 결과 (episode_result.result). 게임이 보내지 않은 선택 필드는 기본값."""

    seed: int
    cleared: bool
    elapsed: float
    clear_time: Optional[float]
    boss_hp_remaining: float
    deaths: int
    consumables_used: int = 0
    damage_dealt: float = 0.0
    damage_taken: float = 0.0
    segment_times: List[float] = field(default_factory=list)
    block_time: Dict[str, float] = field(default_factory=dict)
    gimmick_success: int = 0
    gimmick_fail: int = 0
    triggers_fired: int = 0
    invalid_actions: int = 0
    stalled: bool = False               # v1.2: 진전 없이 멈춘 판 = 정책 실패 (학습·평가에 벌점으로 포함)
    stall_reason: Optional[str] = None
    invalid: bool = False               # 환경 오류 (통신 실패·게임 내부 오류) — 학습·평가에서 제외
    invalid_reason: Optional[str] = None
    events: Optional[List[Any]] = field(default=None, repr=False)

    REQUIRED = ("seed", "cleared", "elapsed", "clear_time", "boss_hp_remaining", "deaths")
    #: v1.1 게임은 멈춘 판을 invalid + 이 접두어 사유로 보낸다 → stalled 로 해석
    LEGACY_STALL_PREFIX = "stalled"

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "EpisodeResult":
        missing = [k for k in cls.REQUIRED if k not in d]
        if missing:
            raise ValueError("episode_result.result 필수 필드 누락: %s" % missing)
        names = {f.name for f in fields(cls)}
        r = cls(**{k: v for k, v in d.items() if k in names})
        r._normalize_legacy_stall()
        return r

    def _normalize_legacy_stall(self) -> None:
        reason = (self.invalid_reason or "").strip()
        if self.invalid and not self.stalled and reason.lower().startswith(self.LEGACY_STALL_PREFIX):
            self.stalled = True
            self.stall_reason = reason.split(":", 1)[1].strip() if ":" in reason else reason
            self.invalid = False
            self.invalid_reason = None
        if self.stalled:
            self.cleared = False
            self.clear_time = None

    @classmethod
    def failed(cls, seed: int, reason: str) -> "EpisodeResult":
        """통신 실패 등으로 결과를 받지 못한 판 (무효 판)."""
        return cls(seed=seed, cleared=False, elapsed=0.0, clear_time=None, boss_hp_remaining=1.0,
                   deaths=0, invalid=True, invalid_reason=reason)

    def effective_time(self, time_limit: float) -> float:
        """중도절단 처리된 소요 시간.

        - 클리어하지 못한 판: '경과 시간 + 남은 보스 체력 비율 × 제한 시간'
        - 멈춘 판(stalled): 그대로 두면 시간 초과가 될 판이므로 '제한 시간 + 남은 보스 체력 비율 × 제한 시간'
          (멈춘 시점으로 계산하면 일찍 멈출수록 벌점이 줄어 '멈추기'를 배우게 된다)
        """
        if self.cleared and self.clear_time is not None:
            return float(self.clear_time)
        elapsed = max(float(self.elapsed), time_limit) if self.stalled else float(self.elapsed)
        return elapsed + float(self.boss_hp_remaining) * time_limit

    def to_dict(self, include_events: bool = False) -> Dict[str, Any]:
        d = asdict(self)
        if not include_events:
            d.pop("events", None)
        return d
