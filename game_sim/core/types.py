"""게임 내부 타입 (BT·시뮬레이터 전용). 학습 쪽과 공유하지 않는다 — 경계는 docs/PROTOCOL.md."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

EPS = 1e-9


class ActionKind(Enum):
    IDLE = "idle"
    SKILL = "skill"
    MOVE_TOWARD = "move_toward"
    MOVE_AWAY = "move_away"
    POTION = "potion"
    RESPOND_GIMMICK = "respond_gimmick"


@dataclass(frozen=True)
class Action:
    """BT가 한 번의 결정(300ms)마다 내놓는 행동."""

    kind: ActionKind
    skill: Optional[str] = None

    @classmethod
    def idle(cls) -> "Action":
        return cls(ActionKind.IDLE)

    @classmethod
    def use(cls, skill_name: str) -> "Action":
        return cls(ActionKind.SKILL, skill_name)

    @classmethod
    def move_toward(cls) -> "Action":
        return cls(ActionKind.MOVE_TOWARD)

    @classmethod
    def move_away(cls) -> "Action":
        return cls(ActionKind.MOVE_AWAY)

    @classmethod
    def potion(cls) -> "Action":
        return cls(ActionKind.POTION)

    @classmethod
    def respond_gimmick(cls) -> "Action":
        return cls(ActionKind.RESPOND_GIMMICK)


@dataclass
class Observation:
    """BT가 보는 현재 상태 (게임 내부)."""

    time: float
    hp_ratio: float
    resource: float
    resource_ratio: float
    max_resource: float
    distance: float
    boss_reach: float
    boss_hp_ratio: float
    gcd_ready: bool
    # 쿨타임·자원 기준 사용 가능 여부 (GCD 무시)
    skill_available: Dict[str, bool]
    potions_left: int
    potion_ready: bool
    gimmick_warning: bool

    @property
    def in_boss_reach(self) -> bool:
        return self.distance <= self.boss_reach + EPS


#: 결정 트리거 시 학습 쪽에 보내는 상태 키 (모두 0~1 정규화). describe 응답에 그대로 노출된다.
TRIGGER_STATE_FEATURES = (
    "hp_ratio",
    "boss_hp_ratio",
    "potions_ratio",
    "resource_ratio",
    "burst_ready",
    "time_ratio",
    "deaths_ratio",
)


#: 트리거 메시지의 누적값 키 (프로토콜 v1.1). 이름·단위는 episode_result 와 같다.
TRIGGER_TOTALS_FIELDS = ("elapsed", "deaths", "consumables_used", "boss_hp_remaining")


@dataclass
class EpisodeResult:
    """판 하나의 결과. to_dict() 가 프로토콜 episode_result.result 로 그대로 나간다."""

    seed: int
    cleared: bool
    elapsed: float
    clear_time: Optional[float]
    boss_hp_remaining: float
    deaths: int
    consumables_used: int
    damage_dealt: float
    damage_taken: float
    segment_times: List[float]
    block_time: Dict[str, float]
    gimmick_success: int
    gimmick_fail: int
    triggers_fired: int
    invalid_actions: int
    stalled: bool = False               # v1.2: 진전 없이 멈춤 → 실패 판 (cleared=False, invalid 아님)
    stall_reason: Optional[str] = None
    invalid: bool = False               # 환경 오류로 결과를 쓸 수 없는 판 (게임 대역에서는 쓰지 않음)
    invalid_reason: Optional[str] = None
    events: Optional[List[Any]] = field(default=None, repr=False)

    def to_dict(self, include_events: bool = False) -> Dict[str, Any]:
        d = asdict(self)
        if not include_events or d.get("events") is None:
            d.pop("events", None)
        return d
