"""IMPALA 구성요소 단위 테스트 (게임 없이)."""
import unittest

import numpy as np
import torch

from balance_qa.core.types import EpisodeResult, TriggerState
from balance_qa.reward.reward import RewardFunction
from balance_qa.rl.actor import ActorParamSource, ParameterServer, observation
from balance_qa.rl.learner import ImpalaLearner, LearnerConfig
from balance_qa.rl.model import ActorCritic
from balance_qa.rl.trajectory import SegmentRewards, Step, Trajectory, TrajectoryBatch
from balance_qa.rl.vtrace import vtrace
from balance_qa.spec.param import ParamDef, ParamSpace
from balance_qa.spec.persona import Persona

PERSONA = Persona("p", "테스트", 0.5, 0.4, lambda_death=3.0, lambda_consumable=1.0)
TL = 600.0


def result(cleared=True, elapsed=300.0, boss=0.0, deaths=1, cons=2, invalid=False):
    return EpisodeResult(seed=1, cleared=cleared, elapsed=elapsed, clear_time=elapsed if cleared else None,
                         boss_hp_remaining=boss, deaths=deaths, consumables_used=cons, invalid=invalid)


def steps_with_totals(totals):
    return [Step(i, np.zeros(3), np.full(2, 0.5), -1.0, t) for i, t in enumerate(totals)]


class VTraceTest(unittest.TestCase):
    def test_on_policy_equals_monte_carlo_returns(self):
        """ρ = 1, γ = 1 이면 v_s = 남은 보상 합 (가치 추정과 무관)."""
        rewards = torch.tensor([[-1.0, -2.0, -0.5, 0.0], [-3.0, -1.0, 0.0, 0.0]])
        mask = torch.tensor([[1.0, 1, 1, 0], [1, 1, 0, 0]])
        values = torch.randn(2, 4)
        logp = torch.randn(2, 4)
        out = vtrace(logp, logp, rewards, values, mask)
        expected = torch.tensor([[-3.5, -2.5, -0.5, 0.0], [-4.0, -1.0, 0.0, 0.0]])
        self.assertTrue(torch.allclose(out.vs, expected, atol=1e-5))
        # 이점 = r + v_{t+1} − V(x_t)
        adv0 = rewards[0, 0] + expected[0, 1] - values[0, 0]
        self.assertAlmostEqual(float(out.pg_advantages[0, 0]), float(adv0), places=5)
        self.assertTrue(torch.all(out.pg_advantages[mask == 0] == 0))

    def test_off_policy_rho_clipped(self):
        rewards = torch.tensor([[-1.0, -1.0]])
        mask = torch.ones(1, 2)
        values = torch.zeros(1, 2)
        behavior = torch.zeros(1, 2)
        target = torch.full((1, 2), 2.0)  # π/μ = e² > ρ̄ → 1 로 잘림
        out = vtrace(behavior, target, rewards, values, mask)
        self.assertTrue(torch.allclose(out.vs, torch.tensor([[-2.0, -1.0]])))
        target_low = torch.full((1, 2), -2.0)  # π/μ < 1 → 보정 줄어듦
        low = vtrace(behavior, target_low, rewards, values, mask)
        self.assertGreater(float(low.vs[0, 0]), -2.0)


class SegmentRewardTest(unittest.TestCase):
    def test_segments_sum_to_episode_reward(self):
        rf = RewardFunction(PERSONA, TL)
        steps = steps_with_totals([
            {"elapsed": 0.0, "deaths": 0, "consumables_used": 0},
            {"elapsed": 90.0, "deaths": 0, "consumables_used": 1},
            {"elapsed": 200.0, "deaths": 1, "consumables_used": 1},
        ])
        for r in (result(), result(cleared=False, elapsed=600.0, boss=0.3, deaths=4, cons=3)):
            seg = SegmentRewards(rf)(steps, r)
            self.assertEqual(len(seg), 3)
            self.assertAlmostEqual(sum(seg), rf(r), places=9)
        self.assertAlmostEqual(SegmentRewards(rf)(steps, result())[0], -90.0 / 60 - 1.0)

    def test_invalid_or_empty_gives_no_trajectory(self):
        sr = SegmentRewards(RewardFunction(PERSONA, TL))
        self.assertIsNone(sr.build(steps_with_totals([{"elapsed": 0}]), result(invalid=True), 0))
        self.assertIsNone(sr.build([], result(), 0))


class ModelTest(unittest.TestCase):
    def test_initial_mean_matches_target(self):
        m = ActorCritic(8, 3, (16,), seed=0)
        target = np.array([0.2, 0.5, 0.9])
        m.set_initial_mean(target, concentration=10.0)
        u, logp, _ = m.act(np.random.rand(8), rng=None)
        np.testing.assert_allclose(u, target, atol=0.02)
        self.assertTrue(np.isfinite(logp))

    def test_sampling_in_unit_interval_and_reproducible(self):
        m = ActorCritic(8, 3, (16,), seed=0)
        obs = np.random.rand(8)
        a = m.act(obs, np.random.default_rng(5))[0]
        b = m.act(obs, np.random.default_rng(5))[0]
        np.testing.assert_array_equal(a, b)
        self.assertTrue(np.all((a > 0) & (a < 1)))

    def test_parameter_server_versions(self):
        m = ActorCritic(4, 2, (8,))
        ps = ParameterServer()
        self.assertEqual(ps.publish(m), 0)
        v, state = ps.fetch(-1)
        self.assertEqual(v, 0)
        self.assertIsNotNone(state)
        self.assertIsNone(ps.fetch(0)[1])


class ActorSourceTest(unittest.TestCase):
    def test_records_steps_and_decodes_params(self):
        space = ParamSpace([ParamDef("w_a", 0, 1, 0.5), ParamDef("p", 0.1, 0.9, 0.5)])
        m = ActorCritic(4, 2, (8,))
        src = ActorParamSource(m, space, {"fixed": 1.0}, [0.5, 0.25], rng=np.random.default_rng(0))
        st = TriggerState(1, {"a": 0.2, "b": 0.4, "c": 1.0}, ["a", "b", "c"], {"elapsed": 30.0})
        out = src.on_trigger(st)
        self.assertEqual(set(out), {"w_a", "p"})
        self.assertTrue(0.1 <= out["p"] <= 0.9)
        self.assertEqual(len(src.steps), 1)
        np.testing.assert_allclose(src.steps[0].obs, observation(st, 2))
        self.assertEqual(src.base_params(), {"fixed": 1.0})


class LearnerTest(unittest.TestCase):
    def _traj(self, model, n_steps, rng, version=0):
        steps = []
        for i in range(n_steps):
            obs = rng.random(4)
            u, logp, v = model.act(obs, rng)
            steps.append(Step(i, obs, u, logp, {}, v))
        return Trajectory(steps, [-1.0] * n_steps, result(), version, 1)

    def test_collate_padding_and_update_runs(self):
        rng = np.random.default_rng(0)
        model = ActorCritic(4, 2, (8,))
        trajs = [self._traj(model, n, rng) for n in (4, 2, 3)]
        batch = TrajectoryBatch.collate(trajs, 4, 2)
        self.assertEqual(tuple(batch.obs.shape), (3, 4, 4))
        self.assertEqual(batch.mask.sum().item(), 9)
        before = model.flat()
        stats = ImpalaLearner(model, LearnerConfig()).update(batch, current_version=1)
        self.assertFalse(torch.allclose(before, model.flat()))
        self.assertAlmostEqual(stats["rho_mean"], 1.0, places=4)  # 같은 가중치 → on-policy
        self.assertEqual(stats["rho_clip_frac"], 0.0)
        self.assertAlmostEqual(stats["policy_lag"], 1.0)

    def test_learner_improves_simple_bandit(self):
        """행동 u 가 1 에 가까울수록 보상이 큰 1-스텝 문제에서 평균 행동이 올라간다."""
        rng = np.random.default_rng(0)
        model = ActorCritic(2, 1, (16,), seed=0)
        model.set_initial_mean([0.3])
        learner = ImpalaLearner(model, LearnerConfig(lr=1e-2, entropy_coef=0.0))
        start = model.act(np.zeros(2))[0][0]
        for _ in range(150):
            trajs = []
            for _ in range(16):
                u, logp, v = model.act(np.zeros(2), rng)
                trajs.append(Trajectory([Step(0, np.zeros(2), u, logp, {}, v)], [float(u[0])], result(), 0, 1))
            learner.update(TrajectoryBatch.collate(trajs, 2, 1), 0)
        self.assertGreater(model.act(np.zeros(2))[0][0], start + 0.3)


if __name__ == "__main__":
    unittest.main()
