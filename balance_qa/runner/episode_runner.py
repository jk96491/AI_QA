"""에피소드 실행 API (문서 11·12장) — 학습 쪽 인터페이스.

실제 실행은 게임이 한다. 러너는 판 요청을 게임 인스턴스들에 나눠 보내고 결과를 모은다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Sequence

from balance_qa.control.param_source import ParamSource
from balance_qa.core.types import EpisodeResult


@dataclass
class EpisodeJob:
    class_name: str
    scenario: str
    seed: int
    source: ParamSource
    record_events: bool = False


class EpisodeRunner(ABC):
    @abstractmethod
    def run(self, jobs: Sequence[EpisodeJob]) -> List[EpisodeResult]:
        """jobs 순서대로 결과 반환. 실패한 판은 invalid=True 로 채운다."""

    @property
    @abstractmethod
    def size(self) -> int:
        """동시 실행 가능한 게임 인스턴스 수."""

    def close(self) -> None:
        pass
