"""직업별 전투 BT 에이전트.

Root (Selector)
├─ [강제] 기믹 경고 중? → 기믹 대응 블록
└─ 전략 선택 노드 (S = N × w)
   ├─ 버스트 콤보 (w_burst)
   ├─ 딜 유지     (w_dps)
   └─ 생존 모드   (w_survival)
   (후보 없음 → 접근)
"""
from __future__ import annotations

from typing import Dict, Mapping

from game_sim.bt.blackboard import Blackboard
from game_sim.bt.blocks import ApproachBlock, BurstBlock, DpsBlock, GimmickBlock, SurvivalBlock
from game_sim.bt.need import BurstNeed, DpsNeed, SurvivalNeed
from game_sim.bt.node import Condition, Node, Selector, Sequence_, Status
from game_sim.bt.selector import UtilityOption, UtilitySelector
from game_sim.core.types import Action, Observation
from game_sim.spec.class_spec import ClassSpec


class _MarkBlock(Node):
    """강제 블록 진입을 블랙보드에 표시."""

    def __init__(self, block_name: str) -> None:
        super().__init__("mark_" + block_name)
        self.block_name = block_name

    def tick(self, bb: Blackboard) -> Status:
        assert bb.obs is not None
        if bb.current_block != self.block_name:
            bb.current_block = self.block_name
            bb.block_since = bb.obs.time
        return Status.SUCCESS


class BTAgent:
    def __init__(self, spec: ClassSpec) -> None:
        self.spec = spec
        self.bb = Blackboard(spec)
        self.root = self._build()

    def _build(self) -> Node:
        gimmick = GimmickBlock()
        utility = UtilitySelector(
            "strategy",
            options=[
                UtilityOption(BurstBlock.name, BurstBlock().build(), BurstNeed(), "w_burst"),
                UtilityOption(DpsBlock.name, DpsBlock().build(), DpsNeed(), "w_dps"),
                UtilityOption(SurvivalBlock.name, SurvivalBlock().build(), SurvivalNeed(), "w_survival"),
            ],
            fallback=(ApproachBlock.name, ApproachBlock().build()),
        )
        forced = Sequence_(
            "forced_gimmick",
            [
                Condition("gimmick_warning", lambda bb: bool(bb.obs and bb.obs.gimmick_warning)),
                _MarkBlock(gimmick.name),
                gimmick.build(),
            ],
        )
        return Selector("root", [forced, utility])

    # ----- 외부 인터페이스 -----
    def set_params(self, params: Mapping[str, float]) -> None:
        """트리거 사이 구간에서 쓸 파라미터 교체 (다음 트리거까지 고정)."""
        self.bb.params = dict(params)

    @property
    def params(self) -> Dict[str, float]:
        return dict(self.bb.params)

    @property
    def current_block(self) -> str:
        return self.bb.current_block

    def decide(self, obs: Observation) -> Action:
        self.bb.obs = obs
        self.bb.action = None
        self.root.tick(self.bb)
        return self.bb.action or Action.idle()
