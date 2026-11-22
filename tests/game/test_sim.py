"""게임 대역 단독 테스트: 시뮬레이터·BT·게임 데이터 (balance_qa 없이)."""
import dataclasses
import unittest

from game_sim.bt.agent import BTAgent
from game_sim.core.types import TRIGGER_STATE_FEATURES, TRIGGER_TOTALS_FIELDS, Observation
from game_sim.sim.engine import CombatSim
from game_sim.spec.class_spec import ParamError
from game_sim.spec.loader import SpecRepository, SpecValidator

REPO = SpecRepository()
STABLE = {"survival_hp_threshold": 0.8, "dps_hp_floor": 0.7}
AGGRESSIVE = {"survival_hp_threshold": 0.3, "dps_hp_floor": 0.2}


def params(cls, persona=None, **overrides):
    p = REPO.load_class(cls).default_params()
    p.update(persona or STABLE)
    p.update(overrides)
    return p


class SpecTest(unittest.TestCase):
    def test_all_data_valid(self):
        REPO.validate_all()
        self.assertEqual(REPO.class_names(), ["archer", "mage", "warrior"])

    def test_validator_rejects_bad_default(self):
        spec = REPO.load_class("warrior")
        bad = dict(spec.params)
        bad["w_dps"] = dataclasses.replace(bad["w_dps"], default=2.0)
        problems = SpecValidator().validate_class(dataclasses.replace(spec, params=bad))
        self.assertTrue(any("w_dps" in p for p in problems))

    def test_scenario_applies(self):
        self.assertAlmostEqual(REPO.boss_for("patch_boss_hp_up5").max_hp, REPO.boss_for("base").max_hp * 1.05)

    def test_persona_params_declared_not_optimized(self):
        spec = REPO.load_class("mage")
        for name in ("survival_hp_threshold", "dps_hp_floor"):
            self.assertEqual(spec.params[name].group, "persona")
            self.assertFalse(spec.params[name].optimize)

    def test_resolve_params_errors(self):
        spec = REPO.load_class("warrior")
        with self.assertRaises(ParamError) as cm:
            spec.resolve_params({}, {"nope": 1})
        self.assertEqual(cm.exception.code, "unknown_param")
        with self.assertRaises(ParamError) as cm:
            spec.resolve_params({}, {"w_dps": 5})
        self.assertEqual(cm.exception.code, "param_out_of_range")


class SimTest(unittest.TestCase):
    def run_sim(self, cls, seed, p=None, **kw):
        return CombatSim(REPO.load_class(cls), REPO.load_boss(), p if p is not None else params(cls), seed, **kw).run()

    def test_deterministic(self):
        self.assertEqual(self.run_sim("mage", 7).to_dict(), self.run_sim("mage", 7).to_dict())

    def test_different_seeds_differ(self):
        self.assertGreater(len({self.run_sim("archer", s).elapsed for s in range(5)}), 1)

    def test_all_classes_clear_with_defaults(self):
        for cls in REPO.class_names():
            r = self.run_sim(cls, 1)
            self.assertFalse(r.invalid, r.invalid_reason)
            self.assertTrue(r.cleared, cls)
            self.assertEqual(len(r.segment_times), 4)

    def test_empty_params_means_defaults(self):
        spec = REPO.load_class("warrior")
        a = self.run_sim("warrior", 3, {})
        b = self.run_sim("warrior", 3, spec.default_params())
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_zero_weights_still_progress(self):
        r = self.run_sim("warrior", 1, params("warrior", w_burst=0, w_dps=0, w_survival=0))
        self.assertIn("approach", r.block_time)

    def test_triggers_call_handler_in_order(self):
        seen = []

        def on_trigger(index, state, totals):
            seen.append((index, state, totals))
            return {"w_survival": 0.5}

        r = self.run_sim("warrior", 2, triggers=[0.75, 0.5, 0.25], on_trigger=on_trigger)
        self.assertEqual([i for i, _, _ in seen], [0, 1, 2, 3])
        self.assertEqual(r.triggers_fired, 4)
        for _, state, totals in seen:
            self.assertEqual(tuple(state), TRIGGER_STATE_FEATURES)
            self.assertEqual(tuple(totals), TRIGGER_TOTALS_FIELDS)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in state.values()))
        elapsed = [t["elapsed"] for _, _, t in seen]
        self.assertEqual(elapsed, sorted(elapsed))
        self.assertEqual(seen[0][2]["elapsed"], 0.0)
        self.assertLessEqual(seen[-1][2]["elapsed"], r.elapsed)

    def test_stall_reported_as_stalled_failure(self):
        """보스 피해 없이 stall_seconds 가 지나면 stalled=True (invalid 아님, v1.2)."""
        from game_sim.sim.config import SimConfig

        r = self.run_sim("mage", 1, config=SimConfig(stall_seconds=0.6))
        self.assertTrue(r.stalled)
        self.assertFalse(r.invalid)
        self.assertFalse(r.cleared)
        self.assertIsNone(r.clear_time)
        self.assertIn("stalled", r.to_dict())

    def test_no_handler_no_triggers(self):
        r = self.run_sim("warrior", 2, triggers=[0.5])
        self.assertEqual(r.triggers_fired, 0)


class AgentTest(unittest.TestCase):
    def _obs(self, **kw):
        spec = REPO.load_class("warrior")
        base = dict(
            time=10.0, hp_ratio=1.0, resource=100.0, resource_ratio=1.0, max_resource=100.0,
            distance=2.0, boss_reach=3.0, boss_hp_ratio=0.9, gcd_ready=True,
            skill_available={s.name: True for s in spec.skills}, potions_left=3, potion_ready=True,
            gimmick_warning=False,
        )
        base.update(kw)
        return Observation(**base)

    def _no_burst(self):
        return {s.name: s.name != "bladestorm" for s in REPO.load_class("warrior").skills}

    def test_gimmick_forced(self):
        agent = BTAgent(REPO.load_class("warrior"))
        agent.set_params(params("warrior"))
        agent.decide(self._obs(gimmick_warning=True))
        self.assertEqual(agent.current_block, "gimmick")

    def test_low_hp_selects_survival_for_stable(self):
        agent = BTAgent(REPO.load_class("warrior"))
        agent.set_params(params("warrior", STABLE, min_commit=0.0))
        agent.decide(self._obs(hp_ratio=0.25, skill_available=self._no_burst()))
        self.assertEqual(agent.current_block, "survival")

    def test_low_hp_keeps_dps_for_aggressive(self):
        agent = BTAgent(REPO.load_class("warrior"))
        agent.set_params(params("warrior", AGGRESSIVE, w_dps=0.7, w_survival=0.6, min_commit=0.0))
        agent.decide(self._obs(hp_ratio=0.25, skill_available=self._no_burst()))
        self.assertEqual(agent.current_block, "dps")


if __name__ == "__main__":
    unittest.main()
