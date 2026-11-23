"""보상: 클리어 실패 벌점 (2026-11-22 결정 A)."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from balance_qa.core.types import EpisodeResult
from balance_qa.reward.reward import RewardFunction
from balance_qa.rl.trajectory import SegmentRewards, Step
from balance_qa.spec.loader import PersonaRepository, SpecError
from balance_qa.spec.persona import DEFAULT_FAIL_PENALTY, Persona

TL = 600.0
STABLE = Persona("stable", "안정형", lambda_death=10.0, lambda_consumable=0.0, params={"survival_hp_threshold": 0.8, "dps_hp_floor": 0.7})


def res(cleared, elapsed, boss, deaths):
    return EpisodeResult(seed=1, cleared=cleared, elapsed=elapsed, clear_time=elapsed if cleared else None,
                         boss_hp_remaining=boss, deaths=deaths, consumables_used=0)


class FailPenaltyTest(unittest.TestCase):
    def test_only_failed_episodes_pay(self):
        rf = RewardFunction(STABLE, TL)
        self.assertEqual(rf.breakdown(res(True, 420.0, 0.0, 1)).fail_term, 0.0)
        fail = rf.breakdown(res(False, TL, 0.4, 0))
        self.assertEqual(fail.fail_term, -DEFAULT_FAIL_PENALTY)
        self.assertAlmostEqual(fail.total, -(TL + 0.4 * TL) / 60.0 - DEFAULT_FAIL_PENALTY)
        self.assertIn("fail", fail.as_dict())

    def test_clear_with_two_deaths_beats_deathless_timeout(self):
        """0.4.0 에서 학습이 택한 '안 죽고 시간 초과' 가 '2번 죽고 클리어' 보다 나빠야 한다."""
        rf = RewardFunction(STABLE, TL)
        self.assertGreater(rf(res(True, 450.0, 0.0, 2)), rf(res(False, TL, 0.4, 0)))

    def test_zero_penalty_restores_original_formula(self):
        p = Persona("x", "x", 3.0, 1.0, params={"survival_hp_threshold": 0.5, "dps_hp_floor": 0.4}, fail_penalty=0.0)
        self.assertAlmostEqual(RewardFunction(p, TL)(res(False, TL, 0.5, 1)), -(TL + 0.5 * TL) / 60.0 - 3.0)

    def test_segments_put_penalty_on_last_step(self):
        rf = RewardFunction(STABLE, TL)
        steps = [Step(i, np.zeros(3), np.full(2, 0.5), -1.0, t) for i, t in enumerate([
            {"elapsed": 0.0, "deaths": 0, "consumables_used": 0},
            {"elapsed": 200.0, "deaths": 0, "consumables_used": 0},
        ])]
        r = res(False, TL, 0.3, 1)
        seg = SegmentRewards(rf)(steps, r)
        self.assertAlmostEqual(seg[0], -200.0 / 60.0)
        self.assertAlmostEqual(sum(seg), rf(r), places=9)


class LoaderTest(unittest.TestCase):
    def _repo(self, data):
        d = tempfile.mkdtemp()
        Path(d, "personas.json").write_text(json.dumps(data), encoding="utf-8")
        return PersonaRepository(d)

    def test_common_value_and_override(self):
        base = {"id": "a", "name": "a", "survival_hp_threshold": 0.5, "dps_hp_floor": 0.4,
                "lambda_death": 1.0, "lambda_consumable": 0.0}
        repo = self._repo({"fail_penalty": 12.0, "personas": [base, dict(base, id="b", fail_penalty=5.0)]})
        self.assertEqual(repo.get("a").fail_penalty, 12.0)
        self.assertEqual(repo.get("b").fail_penalty, 5.0)
        with self.assertRaises(SpecError):
            self._repo({"fail_penalty": -1.0, "personas": [base]}).all()

    def test_shipped_personas_share_penalty(self):
        values = {p.fail_penalty for p in PersonaRepository().all().values()}
        self.assertEqual(len(values), 1)


if __name__ == "__main__":
    unittest.main()
