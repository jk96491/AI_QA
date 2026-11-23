"""SDK 핵심 규칙: 학습 대상 = 블록 가중치뿐. 페르소나는 가중치가 아닌 설정값만 정한다."""
import unittest

from balance_qa.spec.game_info import ClassInfo
from balance_qa.spec.loader import PersonaRepository
from balance_qa.spec.persona import Persona
from game_sim.server.session import GameSession
from game_sim.spec.loader import SpecRepository


class GameSimDeclarationTest(unittest.TestCase):
    """선언 규칙 자체는 SDK 레포의 테스트가 검사한다. 여기서는 game_sim 이 규칙대로 선언하는지만."""

    def test_game_sim_declares_three_weights(self):
        d = GameSession(SpecRepository()).description()
        for c in d["classes"]:
            self.assertEqual([b["weight"] for b in c["blocks"]], ["w_burst", "w_dps", "w_survival"])
            self.assertEqual(sorted(p["name"] for p in c["params"] if p["optimize"]), ["w_burst", "w_dps", "w_survival"])


class LearnerRuleTest(unittest.TestCase):
    def setUp(self):
        wire = GameSession(SpecRepository()).description()
        self.info = ClassInfo.from_wire(next(c for c in wire["classes"] if c["name"] == "warrior"))

    def test_learnable_space_is_weights_only(self):
        self.assertTrue(self.info.blocks_declared)
        self.assertEqual(self.info.learnable_space().names, ["w_burst", "w_dps", "w_survival"])
        self.assertEqual(self.info.learnable_space(["w_dps"]).names, ["w_dps"])
        with self.assertRaises(ValueError):
            self.info.learnable_space(["potion_hp"])

    def test_v12_game_falls_back_to_weight_unit(self):
        wire = GameSession(SpecRepository()).description()["classes"][0]
        wire = dict(wire)
        del wire["blocks"]
        info = ClassInfo.from_wire(wire)
        self.assertFalse(info.blocks_declared)
        self.assertEqual(info.learnable_space().names, ["w_burst", "w_dps", "w_survival"])

    def test_persona_may_set_settings_but_not_weights(self):
        ok = Persona("p", "p", 1.0, 0.0, params={"survival_hp_threshold": 0.8, "potion_hp": 0.6})
        self.assertEqual(PersonaRepository.check_against(ok, self.info), [])
        bad = Persona("p", "p", 1.0, 0.0, params={"w_burst": 0.9})
        self.assertTrue(PersonaRepository.check_against(bad, self.info))

    def test_legacy_persona_format(self):
        p = Persona.from_dict({"id": "a", "name": "a", "survival_hp_threshold": 0.5, "dps_hp_floor": 0.4,
                               "lambda_death": 1.0, "lambda_consumable": 0.0})
        self.assertEqual(p.settings(), {"survival_hp_threshold": 0.5, "dps_hp_floor": 0.4})


if __name__ == "__main__":
    unittest.main()
