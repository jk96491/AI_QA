"""아래층 행동 블록 (고정 서브트리, 문서 6장).

블록 내부 구조는 고정이고, 파라미터는 블랙보드 값(potion_hp, kite_distance 등)으로만 참조한다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from game_sim.bt.blackboard import Blackboard
from game_sim.bt.node import Act, Condition, Node, Selector, Sequence_
from game_sim.core.types import Action
from game_sim.spec.skill_def import SkillRole


# ---------------------------------------------------------------- 공통 리프 함수
def use_best(role: SkillRole, respect_reserve: bool = False):
    def fn(bb: Blackboard) -> Optional[Action]:
        for skill in bb.skills(role):
            if not bb.usable_now(skill) or not bb.in_range(skill):
                continue
            if respect_reserve and not bb.keeps_reserve(skill):
                continue
            return Action.use(skill.name)
        return None

    return fn


def move_toward(bb: Blackboard) -> Optional[Action]:
    return Action.move_toward()


def move_away(bb: Blackboard) -> Optional[Action]:
    return Action.move_away()


def wait(bb: Blackboard) -> Optional[Action]:
    return Action.idle()


def gcd_pending_in_range(bb: Blackboard) -> bool:
    assert bb.obs is not None
    return (not bb.obs.gcd_ready) and bb.in_range(bb.spec.basic_skill)


def too_close(bb: Blackboard) -> bool:
    """원거리: 보스와 거리가 kite_distance 보다 가까우면 거리 벌리기."""
    assert bb.obs is not None
    return bb.spec.ranged and bb.obs.distance < bb.p("kite_distance", 0.0)


# ---------------------------------------------------------------- 블록
class Block(ABC):
    name: str = "block"

    @abstractmethod
    def build(self) -> Node:
        ...


class BurstBlock(Block):
    name = "burst"

    def build(self) -> Node:
        return Selector(
            self.name,
            [
                Act("use_burst", use_best(SkillRole.BURST)),
                Sequence_("wait_gcd", [Condition("gcd_pending", gcd_pending_in_range), Act("idle", wait)]),
                Act("approach", move_toward),
            ],
        )


class DpsBlock(Block):
    name = "dps"

    def build(self) -> Node:
        def far_for_charge(bb: Blackboard) -> bool:
            assert bb.obs is not None
            return bb.obs.distance > bb.p("charge_distance", 1e9)

        return Selector(
            self.name,
            [
                Sequence_("kite", [Condition("too_close", too_close), Act("move_away", move_away)]),
                Sequence_(
                    "charge",
                    [Condition("far", far_for_charge), Act("gap_close", use_best(SkillRole.GAP_CLOSE))],
                ),
                Act("use_dps", use_best(SkillRole.DPS, respect_reserve=True)),
                Act("use_basic", use_best(SkillRole.BASIC)),
                Sequence_("wait_gcd", [Condition("gcd_pending", gcd_pending_in_range), Act("idle", wait)]),
                Act("approach", move_toward),
            ],
        )


class SurvivalBlock(Block):
    name = "survival"
    SAFE_MARGIN = 4.0

    def build(self) -> Node:
        def needs_potion(bb: Blackboard) -> bool:
            assert bb.obs is not None
            return bb.obs.potion_ready and bb.obs.hp_ratio < bb.p("potion_hp")

        def boss_near(bb: Blackboard) -> bool:
            """보스 사거리 + 안전 여유 안이면 후퇴 (회복이 시작되도록 거리 확보)."""
            assert bb.obs is not None
            return bb.obs.distance < bb.obs.boss_reach + self.SAFE_MARGIN

        return Selector(
            self.name,
            [
                Sequence_("potion", [Condition("needs_potion", needs_potion), Act("drink", lambda bb: Action.potion())]),
                Act("defend", use_best(SkillRole.DEFENSE)),
                Sequence_("retreat", [Condition("boss_near", boss_near), Act("move_away", move_away)]),
                Act("poke", use_best(SkillRole.BASIC)),
                Act("idle", wait),
            ],
        )


class GimmickBlock(Block):
    """기믹 경고 시 강제 선택."""

    name = "gimmick"

    def build(self) -> Node:
        return Act("respond", lambda bb: Action.respond_gimmick())


class ApproachBlock(Block):
    """후보 블록이 하나도 없을 때의 기본 동작."""

    name = "approach"

    def build(self) -> Node:
        return Selector(self.name, [Act("approach", move_toward)])
