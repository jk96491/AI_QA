"""이벤트 로그 (대표 리플레이·진단 정보용)."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


class EventLog:
    """(시간, 종류, 내용) 튜플을 기록한다. 비활성화 시 비용 없음."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.events: List[Tuple[float, str, Dict[str, Any]]] = []

    def record(self, t: float, event: str, **payload: Any) -> None:
        if self.enabled:
            self.events.append((round(t, 2), event, payload))

    def filter(self, kind: str) -> List[Tuple[float, str, Dict[str, Any]]]:
        return [e for e in self.events if e[1] == kind]

    def __len__(self) -> int:
        return len(self.events)
