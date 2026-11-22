"""위층 전략 선택 노드 (점수 기반 선택, 문서 6·7장)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from game_sim.bt.blackboard import Blackboard
from game_sim.bt.need import NeedFunction
from game_sim.bt.node import Node, Status


@dataclass
class UtilityOption:
    name: str
    node: Node
    need: NeedFunction
    weight_key: str


class UtilitySelector(Node):
    """실행 가능한 블록 중 S = N × w 가 가장 큰 블록을 실행.

    - N 이 None(후보 제외) 이거나 S 가 0 인 블록은 후보가 아님

    - min_commit 초 동안은 현재 블록이 후보에 남아 있으면 유지 (떨림 방지)
    - 선택된 블록이 실패하면 fallback 블록 실행
    """

    def __init__(self, name: str, options: List[UtilityOption], fallback: Tuple[str, Node]) -> None:
        super().__init__(name)
        self.options = options
        self.fallback_name, self.fallback = fallback

    def score(self, bb: Blackboard) -> List[Tuple[float, UtilityOption]]:
        scored: List[Tuple[float, UtilityOption]] = []
        bb.scores = {}
        for opt in self.options:
            n = opt.need.value(bb)
            if n is None:
                continue
            s = n * bb.p(opt.weight_key)
            bb.scores[opt.name] = s
            if s <= 1e-9:
                # 필요도(또는 가중치) 0 인 블록은 '필요 없음' → 후보 제외
                continue
            scored.append((s, opt))
        # 점수 내림차순, 동점이면 정의 순서 유지 (결정론)
        scored.sort(key=lambda t: -t[0])
        return scored

    def _choose(self, bb: Blackboard, scored: List[Tuple[float, UtilityOption]]) -> Optional[UtilityOption]:
        if not scored:
            return None
        assert bb.obs is not None
        best = scored[0][1]
        min_commit = bb.p("min_commit", 0.0)
        if bb.current_block != best.name and bb.obs.time - bb.block_since < min_commit:
            for _, opt in scored:
                if opt.name == bb.current_block:
                    return opt
        return best

    def _switch(self, bb: Blackboard, name: str) -> None:
        assert bb.obs is not None
        if bb.current_block != name:
            bb.current_block = name
            bb.block_since = bb.obs.time

    def tick(self, bb: Blackboard) -> Status:
        chosen = self._choose(bb, self.score(bb))
        if chosen is not None:
            self._switch(bb, chosen.name)
            status = chosen.node.tick(bb)
            if status != Status.FAILURE:
                return status
        self._switch(bb, self.fallback_name)
        return self.fallback.tick(bb)
