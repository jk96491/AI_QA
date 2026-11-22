"""멈춘 판(stalled) = 실패 처리 (프로토콜 v1.2, v1.1 호환)."""
import unittest

import numpy as np

from balance_qa.core.types import EpisodeResult
from balance_qa.reward.reward import RewardFunction
from balance_qa.rl.trajectory import SegmentRewards, Step
from balance_qa.spec.persona import Persona

TL = 600.0
PERSONA = Persona("p", "테스트", 0.5, 0.4, lambda_death=3.0, lambda_consumable=1.0)
BASE = {"seed": 1, "cleared": False, "elapsed": 200.0, "clear_time": None, "boss_hp_remaining": 0.4, "deaths": 0}


class StallTest(unittest.TestCase):
    def test_v12_stalled_is_failure_not_invalid(self):
        r = EpisodeResult.from_dict(dict(BASE, stalled=True, stall_reason="90s 동안 보스 피해 없음"))
        self.assertTrue(r.stalled)
        self.assertFalse(r.invalid)
        self.assertFalse(r.cleared)

    def test_v11_legacy_invalid_stalled_is_converted(self):
        r = EpisodeResult.from_dict(dict(BASE, invalid=True, invalid_reason="stalled: 90s 동안 보스 피해 없음"))
        self.assertTrue(r.stalled)
        self.assertFalse(r.invalid)
        self.assertEqual(r.stall_reason, "90s 동안 보스 피해 없음")

    def test_other_invalid_stays_invalid(self):
        r = EpisodeResult.from_dict(dict(BASE, invalid=True, invalid_reason="exception: boom"))
        self.assertTrue(r.invalid)
        self.assertFalse(r.stalled)

    def test_stall_penalty_equals_timeout_not_less(self):
        """일찍 멈춰도 벌점이 줄지 않는다: 멈춘 판 = 같은 남은 체력의 시간 초과 판."""
        stalled = EpisodeResult.from_dict(dict(BASE, stalled=True))
        timeout = EpisodeResult.from_dict(dict(BASE, elapsed=TL))
        early_fail = EpisodeResult.from_dict(BASE)  # 사망 초과 등으로 200초에 실패
        self.assertAlmostEqual(stalled.effective_time(TL), timeout.effective_time(TL))
        self.assertAlmostEqual(stalled.effective_time(TL), TL + 0.4 * TL)
        self.assertGreater(stalled.effective_time(TL), early_fail.effective_time(TL))

    def test_stalled_counts_in_reward_and_segments(self):
        rf = RewardFunction(PERSONA, TL)
        stalled = EpisodeResult.from_dict(dict(BASE, invalid=True, invalid_reason="stalled: x"))
        self.assertNotEqual(rf(stalled), -1e3)          # 무효 벌점이 아니라 실제 보상
        self.assertAlmostEqual(rf(stalled), -(TL + 0.4 * TL) / 60.0 - PERSONA.fail_penalty)
        self.assertAlmostEqual(rf.mean([stalled]), rf(stalled))  # 평균에서 빠지지 않음
        steps = [Step(0, np.zeros(3), np.zeros(2), 0.0, {"elapsed": 0.0, "deaths": 0, "consumables_used": 0}),
                 Step(1, np.zeros(3), np.zeros(2), 0.0, {"elapsed": 150.0, "deaths": 0, "consumables_used": 0})]
        traj = SegmentRewards(rf).build(steps, stalled, 0)
        self.assertIsNotNone(traj)                       # IMPALA 학습에 포함
        self.assertAlmostEqual(sum(traj.rewards), rf(stalled))


if __name__ == "__main__":
    unittest.main()
