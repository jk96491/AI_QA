"""문서 7·8장 예시 수치 재현 (E0)."""
import unittest

from game_sim.bt.need import BurstNeed, DpsNeed, SurvivalNeed, survival_switch_point

STABLE_W = (0.6, 0.5, 0.9)      # 버스트, 딜, 생존
AGGRESSIVE_W = (0.9, 0.7, 0.6)


class NeedFormulaTest(unittest.TestCase):
    def test_doc_timeline_stable(self):
        """7장 표: 안정형 θ 80%, φ 70%, w=(0.6, 0.5, 0.9)."""
        wb, wd, ws = STABLE_W
        cases = [
            # (hp, burst_ready, 기대 버스트 S, 딜 S, 생존 S)
            (1.00, False, None, 0.25, 0.0),
            (1.00, True, 0.48, 0.25, 0.0),
            (0.80, False, None, 0.25, 0.0),
            (0.25, False, None, 0.09, 0.62),
            (0.60, True, 0.48, 0.21, 0.23),
        ]
        for hp, ready, b, d, s in cases:
            burst = BurstNeed.compute(ready)
            self.assertEqual(burst is None, b is None)
            if b is not None:
                self.assertAlmostEqual(burst * wb, b, places=2)
            self.assertAlmostEqual(DpsNeed.compute(hp, 0.7) * wd, d, delta=0.005)
            self.assertAlmostEqual(SurvivalNeed.compute(hp, 0.8) * ws, s, delta=0.005)

    def test_doc_needs_at_12s(self):
        self.assertAlmostEqual(SurvivalNeed.compute(0.25, 0.8), 0.69, delta=0.005)
        self.assertAlmostEqual(SurvivalNeed.compute(0.25, 0.3), 0.17, delta=0.005)
        self.assertAlmostEqual(DpsNeed.compute(0.25, 0.7), 0.18, delta=0.005)
        self.assertAlmostEqual(DpsNeed.compute(0.25, 0.2), 0.50, delta=0.005)

    def test_switch_points(self):
        """8장 표: 생존 전환 시점 안정형 61%, 공격형 16%."""
        self.assertAlmostEqual(survival_switch_point(0.8, 0.7, STABLE_W[1], STABLE_W[2]), 0.61, delta=0.005)
        self.assertAlmostEqual(survival_switch_point(0.3, 0.2, AGGRESSIVE_W[1], AGGRESSIVE_W[2]), 0.16, delta=0.005)


if __name__ == "__main__":
    unittest.main()
