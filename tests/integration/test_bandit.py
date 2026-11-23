"""컨텍스트 밴딧 (docs/BANDIT_IMPALA_DESIGN.md) + 프로토콜 v1.4 initial_state.

게임 대역 서버(스레드) ↔ 학습 플랫폼 ↔ play_agent(numpy) — 테스트에서만 함께 import 한다.
"""
import unittest

import numpy as np

from balance_qa.control.param_source import StaticParamSource
from balance_qa.game_api.client import EpisodeRequest, GameClient
from balance_qa.rl.bandit import BanditSetup, ContextCell, ContextEncoder, MixedContextSampler, StateRange
from balance_qa.session import QASession
from game_sim.server.server import GameServer
from play_agent.loadout import LoadoutBuilder

STATES = [StateRange("hp_ratio", 0.05, 1.0, 1.0), StateRange("potions_ratio", 0.0, 1.0, 1.0, (0.0, 1 / 3, 2 / 3, 1.0))]


class BanditPartsTest(unittest.TestCase):
    def test_encoder_layout_and_defaults(self):
        enc = ContextEncoder(["mage", "warrior"], ["base", "forest_wolf_king"], STATES)
        self.assertEqual(enc.dim, 6)
        x = enc.encode("warrior", "forest_wolf_king", {"potions_ratio": 0.0})
        self.assertEqual(x.tolist(), [0, 1, 0, 1, 1.0, 0.0])          # hp 생략 → default 1.0
        with self.assertRaises(KeyError):
            enc.encode("archer", "base")

    def test_sampler_deterministic_mix_and_wire(self):
        s = MixedContextSampler([("warrior", "base"), ("mage", "base")], STATES, p_full=0.4)
        a = [s.sample(np.random.default_rng([0, i])) for i in range(200)]
        b = [s.sample(np.random.default_rng([0, i])) for i in range(200)]
        self.assertEqual(a, b)
        full = sum(c.initial_state is None for c in a) / len(a)
        self.assertTrue(0.25 < full < 0.55, full)
        pots = {dict(c.initial_state)["potions_ratio"] for c in a if c.initial_state}
        self.assertTrue(pots <= {0.0, 1 / 3, 2 / 3, 1.0})              # levels 만
        setup = BanditSetup(ContextEncoder(["mage", "warrior"], ["base"], STATES), s, {"warrior": {}, "mage": {}})
        again = BanditSetup.from_wire(setup.to_wire())
        self.assertEqual(again.to_wire(), setup.to_wire())
        grid = setup.cells_grid({"hp_ratio": [1.0, 0.4], "potions_ratio": [0.0, 1.0]})
        self.assertEqual(len(grid), 2 * (1 + 4))                       # 조합 × (full + 2×2)


class InitialStateProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = GameServer(port=0)
        cls.server.start_in_thread()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_game_sim_initial_state(self):
        c = GameClient(*self.server.address).connect()
        try:
            c.hello()
            d = c.describe()
            self.assertEqual([s.name for s in d.initial_state], ["hp_ratio", "potions_ratio"])
            src = StaticParamSource({})
            base = c.run_episode(EpisodeRequest("warrior", 7), src).to_dict()
            same = c.run_episode(EpisodeRequest("warrior", 7, initial_state={"hp_ratio": 1.0, "potions_ratio": 1.0}), src).to_dict()
            self.assertEqual(base, same)                                # default = 생략
            none = c.run_episode(EpisodeRequest("mage", 7, initial_state={"potions_ratio": 0.0}), src)
            self.assertEqual(none.consumables_used, 0)                  # 물약 0개로 시작
            with self.assertRaises(ValueError):                         # 선언 안 된 키는 보내기 전에 막는다
                c.run_episode(EpisodeRequest("warrior", 7, initial_state={"mana_ratio": 0.5}), src)
        finally:
            c.close()


class BanditTrainingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servers = [GameServer(port=0) for _ in range(2)]
        for s in cls.servers:
            s.start_in_thread()

    @classmethod
    def tearDownClass(cls):
        for s in cls.servers:
            s.stop()

    def test_train_save_and_play_agent_matches_torch(self):
        import json
        import tempfile
        from pathlib import Path

        with QASession(endpoints=[s.address for s in self.servers]) as s:
            out = s.train_bandit([("warrior", "base"), ("mage", "base")], "stable", budget=64, batch_size=16,
                                 actors="threads", levels={"potions_ratio": [0, 1 / 3, 2 / 3, 1]}, eval_n=4,
                                 eval_levels={"hp_ratio": [1.0], "potions_ratio": [0.0]}, log_every=1, verbose=False)
            self.assertEqual(out.outcome.method, "impala-bandit")
            self.assertEqual(out.trainer.model.obs_dim, 2 + 1 + 2)       # 직업 2 + 시나리오 1 + 상태 2
            self.assertEqual(len(out.cells), 2 * 2)                       # 조합 2 × (full + 1)
            with tempfile.TemporaryDirectory() as d:
                path = out.outcome.save_params(Path(d) / "reports" / "r1" / "policy.json", s.game)
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["source"]["type"], "impala-bandit")
                self.assertEqual(payload["combos"], [["warrior", "base"], ["mage", "base"]])
                lb = LoadoutBuilder()
                lb.add_file(path)
            self.assertEqual(sorted(lb.entries), [("mage", "base"), ("warrior", "base")])
            for cell in (ContextCell("warrior", "base"), ContextCell.make("mage", "base", {"potions_ratio": 0.0}),
                         ContextCell.make("warrior", "base", {"hp_ratio": 0.4, "potions_ratio": 1 / 3})):
                torch_w = out.trainer.bandit_source(cell).weights
                b = lb.entries[(cell.class_name, cell.scenario)].policy
                np_w = b.params({"index": 0, "state": cell.state_dict() or {}})
                for k, v in torch_w.items():
                    self.assertAlmostEqual(np_w[k], v, places=5, msg="%s %s" % (cell.label, k))
                self.assertEqual(b.params({"index": 1, "state": {}}), {})   # index 0 에만 답한다
