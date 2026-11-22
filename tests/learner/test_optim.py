"""최적화기·정책(PyTorch CPU)·통계 테스트."""
import pickle
import unittest

import numpy as np
import torch

from balance_qa.analysis.stats import Stats
from balance_qa.backend import DEVICE, DTYPE
from balance_qa.optim.cma_es import CMAES
from balance_qa.optim.openai_es import OpenAIES
from balance_qa.optim.random_search import RandomSearch
from balance_qa.policy.mlp import MLPPolicy
from balance_qa.spec.param import ParamDef, ParamSpace


def run(opt, f, gens):
    for _ in range(gens):
        xs = opt.ask()
        opt.tell(xs, torch.stack([f(x) for x in xs]))
    return opt.recommendation()


class OptimizerTest(unittest.TestCase):
    TARGET = torch.tensor([0.2, 0.7, 0.5, 0.9], dtype=DTYPE)

    def f(self, x):
        return torch.sum((x - self.TARGET) ** 2)

    def test_tensors_are_cpu_float64(self):
        opt = CMAES(torch.full((4,), 0.5), seed=0)
        xs = opt.ask()
        self.assertEqual(xs.device, DEVICE)
        self.assertEqual(xs.dtype, DTYPE)
        self.assertEqual(tuple(xs.shape), (opt.popsize, 4))

    def test_cmaes_converges_in_bounds(self):
        x = run(CMAES(torch.full((4,), 0.5), sigma0=0.3, seed=1), self.f, 60)
        self.assertLess(float(self.f(x)), 1e-4)
        self.assertTrue(bool(torch.all((x >= 0) & (x <= 1))))

    def test_cmaes_handles_boundary_optimum(self):
        target = torch.tensor([0.0, 1.0, 0.5], dtype=DTYPE)
        x = run(CMAES(torch.full((3,), 0.5), seed=2), lambda v: torch.sum((v - target) ** 2), 80)
        self.assertLess(float(torch.sum((x - target) ** 2)), 1e-3)

    def test_cmaes_seed_reproducible(self):
        a = run(CMAES(torch.full((4,), 0.5), seed=5), self.f, 5)
        b = run(CMAES(torch.full((4,), 0.5), seed=5), self.f, 5)
        self.assertTrue(torch.equal(a, b))

    def test_cmaes_beats_random(self):
        cma = run(CMAES(torch.full((4,), 0.5), seed=3), self.f, 30)
        rnd = run(RandomSearch(4, popsize=8, seed=3), self.f, 30)
        self.assertLess(float(self.f(cma)), float(self.f(rnd)))

    def test_openai_es_improves_with_torch_adam(self):
        start = torch.zeros(4, dtype=DTYPE)
        opt = OpenAIES(start, sigma=0.1, lr=0.05, popsize=20, seed=0)
        self.assertIsInstance(opt.adam, torch.optim.Adam)
        x = run(opt, self.f, 150)
        self.assertLess(float(self.f(x)), float(self.f(start)) * 0.1)


class PolicyTest(unittest.TestCase):
    def test_is_torch_module_on_cpu(self):
        pol = MLPPolicy(7, 3, (8,), seed=0)
        self.assertIsInstance(pol, torch.nn.Module)
        self.assertTrue(all(p.device == DEVICE for p in pol.parameters()))
        self.assertEqual(pol.n_params, 7 * 8 + 8 + 8 * 3 + 3)

    def test_output_bias_sets_initial_output(self):
        pol = MLPPolicy(7, 3, (8,), seed=0)
        target = np.array([0.2, 0.5, 0.8])
        pol.set_output_bias(target)
        np.testing.assert_allclose(pol.act(np.zeros(7)), target, atol=0.05)

    def test_flat_roundtrip(self):
        pol = MLPPolicy(7, 3, (8,), seed=0)
        theta = torch.arange(pol.n_params, dtype=DTYPE) / pol.n_params
        clone = pol.with_flat(theta)
        self.assertTrue(torch.allclose(clone.get_flat(), theta, atol=1e-6))
        self.assertFalse(torch.allclose(pol.get_flat(), theta))

    def test_pickle_preserves_weights(self):
        """워커 전송: 텐서 공유 메모리 없이 평탄 가중치로 복원."""
        pol = MLPPolicy(7, 3, (8,), seed=3)
        back = pickle.loads(pickle.dumps(pol))
        x = np.linspace(0, 1, 7)
        np.testing.assert_allclose(back.act(x), pol.act(x))


class SpaceAndStatsTest(unittest.TestCase):
    def test_param_space_roundtrip(self):
        space = ParamSpace([ParamDef("a", 0, 10, 5), ParamDef("b", -1, 1, 0)])
        p = {"a": 2.5, "b": 0.5}
        self.assertEqual(space.decode(space.encode(p)), p)
        self.assertEqual(space.decode(np.array([2.0, -1.0])), {"a": 10.0, "b": -1.0})

    def test_required_n_matches_design_doc(self):
        self.assertEqual(Stats.required_n(0.10, 0.03), 175)

    def test_wilson_bounds(self):
        iv = Stats.wilson(50, 100)
        self.assertLess(iv.low, 0.5)
        self.assertGreater(iv.high, 0.5)


if __name__ == "__main__":
    unittest.main()
