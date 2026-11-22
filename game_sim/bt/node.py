"""BT 기본 노드."""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Callable, List, Optional, Sequence

from game_sim.core.types import Action

if TYPE_CHECKING:
    from game_sim.bt.blackboard import Blackboard


class Status(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"


class Node(ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def tick(self, bb: "Blackboard") -> Status:
        ...

    def __repr__(self) -> str:
        return "%s(%s)" % (type(self).__name__, self.name)


class Composite(Node):
    def __init__(self, name: str, children: Sequence[Node]) -> None:
        super().__init__(name)
        self.children: List[Node] = list(children)


class Sequence_(Composite):
    """자식이 모두 성공해야 성공. (`Sequence` 는 typing 과 충돌해 밑줄)"""

    def tick(self, bb: "Blackboard") -> Status:
        for child in self.children:
            status = child.tick(bb)
            if status != Status.SUCCESS:
                return status
        return Status.SUCCESS


class Selector(Composite):
    """처음으로 실패하지 않은 자식의 결과를 반환 (고정 우선순위)."""

    def tick(self, bb: "Blackboard") -> Status:
        for child in self.children:
            status = child.tick(bb)
            if status != Status.FAILURE:
                return status
        return Status.FAILURE


class Condition(Node):
    def __init__(self, name: str, predicate: Callable[["Blackboard"], bool]) -> None:
        super().__init__(name)
        self.predicate = predicate

    def tick(self, bb: "Blackboard") -> Status:
        return Status.SUCCESS if self.predicate(bb) else Status.FAILURE


class Act(Node):
    """행동을 고르는 리프. 함수가 None 을 반환하면 실패."""

    def __init__(self, name: str, fn: Callable[["Blackboard"], Optional[Action]]) -> None:
        super().__init__(name)
        self.fn = fn

    def tick(self, bb: "Blackboard") -> Status:
        action = self.fn(bb)
        if action is None:
            return Status.FAILURE
        bb.action = action
        return Status.SUCCESS
