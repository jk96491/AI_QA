"""학습기 ↔ 액터 전송 형식과 설정 직렬화 (게임 없이)."""
import json
import unittest

import numpy as np

from balance_qa.core.types import EpisodeResult
from balance_qa.reward.reward import RewardFunction
from balance_qa.rl import wire
from balance_qa.rl.actor import ParameterServer
from balance_qa.rl.backends import ActorContext
from balance_qa.rl.model import ActorCritic
from balance_qa.rl.spec import ActorSpec
from balance_qa.rl.trajectory import Step, Trajectory
from balance_qa.runner.seed_pool import SeedPool
from balance_qa.spec.param import ParamDef
from balance_qa.spec.persona import Persona


def make_spec():
    persona = Persona("stable", "안정형", 10.0, 0.0, params={"survival_hp_threshold": 0.8, "dps_hp_floor": 0.7})
    return ActorSpec(
        class_name="warrior", scenario="base",
        params=[ParamDef("w_burst", 0.0, 1.0, 0.6), ParamDef("potion_hp", 0.1, 0.9, 0.5, group="bt", unit="hp")],
        fixed={"w_burst": 0.6, "survival_hp_threshold": 0.8}, thresholds=(0.75, 0.5), obs_dim=8, act_dim=2,
        hidden=(16,), persona=__import__("dataclasses").asdict(persona), time_limit=600.0,
        state_features=("a", "b", "c", "d", "e", "f", "g"), sample_seed=3, game="g", game_version="1",
    )


class WireTest(unittest.TestCase):
    def test_floats_roundtrip(self):
        x = np.array([0.1, -2.5, 3.25, 1e-3])
        np.testing.assert_allclose(wire.unpack_floats(wire.pack_floats(x)), x, rtol=1e-6)
        self.assertIsNone(wire.unpack_floats(None))

    def test_trajectory_roundtrip_through_json(self):
        res = EpisodeResult(seed=9, cleared=True, elapsed=300.0, clear_time=300.0, boss_hp_remaining=0.0, deaths=1)
        steps = [Step(i, np.random.rand(8), np.random.rand(2), -1.5 - i, {"elapsed": 10.0 * i}, 0.3) for i in range(3)]
        t = Trajectory(steps, [-1.0, -2.0, -0.5], res, 4, 9)
        line = wire.encode({"type": "episode", "trajectory": wire.trajectory_to_wire(t)})
        back = wire.trajectory_from_wire(wire.decode(line)["trajectory"])
        self.assertEqual((back.seed, back.policy_version, back.rewards), (9, 4, [-1.0, -2.0, -0.5]))
        self.assertEqual(back.result.to_dict(), res.to_dict())
        for a, b in zip(steps, back.steps):
            np.testing.assert_allclose(a.obs, b.obs, rtol=1e-6)
            np.testing.assert_allclose(a.action, b.action, rtol=1e-6)
            self.assertAlmostEqual(a.behavior_logp, b.behavior_logp)
            self.assertEqual(a.totals, b.totals)

    def test_spec_roundtrip_and_rebuild(self):
        spec = make_spec()
        back = ActorSpec.from_wire(json.loads(json.dumps(spec.to_wire())))
        self.assertEqual(back.to_wire(), spec.to_wire())
        self.assertEqual(back.space().names, ["w_burst", "potion_hp"])
        self.assertIsInstance(back.reward_fn(), RewardFunction)
        self.assertEqual(back.new_model().obs_dim, 8)

    def test_flat_weights_transfer_reproduces_policy(self):
        """학습기 ParameterServer.fetch_flat → 전송 → 액터 load_flat 하면 같은 정책."""
        spec = make_spec()
        learner_model = ActorCritic(8, 2, (16,), seed=7)
        ps = ParameterServer()
        ps.publish(learner_model)
        version, flat = ps.fetch_flat(-1)
        received = wire.unpack_floats(wire.pack_floats(flat))

        from balance_qa.rl.actor import ActorCore

        core = ActorCore(client=None, spec=spec)  # 게임 없이 가중치만 확인
        core.load_flat(version, received)
        obs = np.random.rand(8)
        np.testing.assert_allclose(core.model.act(obs)[0], learner_model.act(obs)[0], atol=1e-6)
        self.assertEqual(ps.fetch_flat(version)[1], None)


class ContextTest(unittest.TestCase):
    def test_seeds_stop_and_nonblocking_put(self):
        ctx = ActorContext(make_spec(), ParameterServer(), SeedPool(100, 1000), queue_size=1)
        self.assertEqual([ctx.next_seed(), ctx.next_seed()], [100, 101])
        self.assertTrue(ctx.put("a"))
        ctx.stop.set()
        self.assertIsNone(ctx.next_seed())
        self.assertFalse(ctx.put("b"))  # 큐가 가득 차 있어도 정지 후에는 바로 반환


if __name__ == "__main__":
    unittest.main()
