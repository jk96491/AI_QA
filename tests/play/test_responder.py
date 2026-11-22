"""CombatResponder(numpy 순전파) == 학습 쪽 ActorParamSource(torch, Beta 평균).

테스트는 양쪽을 다 import 할 수 있다 (play_agent 자체는 torch·balance_qa 를 import 하지 않는다).
"""
from __future__ import annotations

import json
import unittest

import numpy as np
import torch

from balance_qa.core.types import TriggerState
from balance_qa.rl.actor import ActorParamSource
from balance_qa.rl.model import ActorCritic
from balance_qa.spec.param import ParamDef, ParamSpace
from play_agent.responder import CombatResponder, ImpalaPolicy, PolicyFileError

FEATURES = ["hp_ratio", "boss_hp_ratio", "potions_ratio", "resource_ratio", "burst_ready", "time_ratio", "deaths_ratio"]
OUTPUTS = [ParamDef("w_burst", 0.0, 1.0, 0.5), ParamDef("w_dps", 0.0, 1.0, 0.8), ParamDef("w_survival", 0.0, 1.0, 0.7),
           ParamDef("potion_hp", 0.1, 0.9, 0.4), ParamDef("resource_reserve", 0.0, 0.6, 0.15)]


def trained_like_model(seed: int = 3) -> ActorCritic:
    """초기화 직후가 아니라 상태에 따라 출력이 달라지는 모델 (가중치를 크게 흔든다)."""
    m = ActorCritic(len(FEATURES) + 1, len(OUTPUTS), (64, 64), seed=seed)
    g = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        for p in m.parameters():
            p.add_(torch.randn(p.shape, generator=g, dtype=p.dtype) * 0.5)
    return m


def policy_json(src: ActorParamSource) -> dict:
    # session.save_params 와 같은 모양 (source = describe(), policy_theta = flat())
    return json.loads(json.dumps({"class": "warrior", "persona": "stable", "method": "impala", "scenario": "forest_wolf_king",
                                  "source": src.describe(), "policy_theta": src.model.flat().tolist(),
                                  "game": {"name": "qa_arena", "version": "0.6.2", "protocol": "1.2"}}))


class ImpalaPolicyTest(unittest.TestCase):
    def setUp(self):
        self.model = trained_like_model()
        self.space = ParamSpace(OUTPUTS)
        self.fixed = {"w_burst": 0.5, "survival_hp_threshold": 0.8}
        self.src = ActorParamSource(self.model, self.space, self.fixed, [0.75, 0.5, 0.25], rng=None, record=False,
                                    state_features=FEATURES)
        self.pol = ImpalaPolicy.from_dict(policy_json(self.src))

    def test_policy_json_carries_reload_info(self):
        d = self.src.describe()
        for k in ("output_ranges", "fixed", "state_features", "obs_dim", "hidden", "u_eps"):
            self.assertIn(k, d)
        self.assertEqual(d["fixed"], self.fixed)
        self.assertEqual(self.pol.fixed, self.fixed)
        self.assertEqual(self.pol.thresholds, [0.75, 0.5, 0.25])

    def test_numpy_forward_matches_torch(self):
        rng = np.random.default_rng(0)
        for i in range(200):
            state = {k: float(v) for k, v in zip(FEATURES, rng.random(len(FEATURES)))}
            index = int(rng.integers(0, 4))
            want = self.src.on_trigger(TriggerState(index, state, FEATURES))
            got = self.pol.params({"type": "trigger", "index": index, "state": state, "encounter_id": "enc_1"})
            self.assertEqual(list(got), list(want))
            for k in want:
                self.assertAlmostEqual(got[k], want[k], delta=1e-5, msg="%s #%d" % (k, i))

    def test_outputs_depend_on_state(self):
        a = self.pol.params({"index": 0, "state": {k: 1.0 for k in FEATURES}})
        b = self.pol.params({"index": 3, "state": {k: 0.0 for k in FEATURES}})
        self.assertNotEqual(a, b)

    def test_old_policy_file_is_rejected_with_reason(self):
        d = policy_json(self.src)
        for k in ("output_ranges", "fixed", "state_features"):
            d["source"].pop(k)
        with self.assertRaises(PolicyFileError) as cm:
            ImpalaPolicy.from_dict(d, label="old")
        self.assertIn("다시", str(cm.exception))

    def test_theta_length_checked(self):
        d = policy_json(self.src)
        d["policy_theta"] = d["policy_theta"][:-3]
        with self.assertRaises(PolicyFileError):
            ImpalaPolicy.from_dict(d)


class CombatResponderTest(unittest.TestCase):
    def test_picks_policy_per_encounter(self):
        src = ActorParamSource(trained_like_model(), ParamSpace(OUTPUTS), {}, [0.75, 0.5, 0.25], rng=None, record=False,
                               state_features=FEATURES)
        pol = ImpalaPolicy.from_dict(policy_json(src))
        r = CombatResponder({("warrior", "forest_wolf_king"): pol})
        trig = {"index": 0, "state": {k: 0.5 for k in FEATURES}}
        r.on_combat_started({"class": "warrior", "scenario": "forest_wolf_king", "encounter_id": "enc_1"})
        self.assertEqual(r(trig), pol.params(trig))
        r.on_combat_started({"class": "warrior", "scenario": "base", "encounter_id": "enc_2"})
        self.assertIsNone(r(trig))   # 정책 없는 조우 = 로드아웃 params 그대로


if __name__ == "__main__":
    unittest.main()
