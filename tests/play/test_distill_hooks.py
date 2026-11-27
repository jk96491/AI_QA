"""QaArena 증류 훅(play_agent.distill_prep·distill_reward)과 평가 스위트 파일 — SDK 에 넘기는 게임 쪽 부분."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from btqa_play.suite import conditions, load_suite
from play_agent.distill_prep import situation, situation_key
from play_agent.distill_reward import reward

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "play_agent" / "specs" / "qa_arena.eval.json"


def _user(entities, modal=None, ui=(), prog=(0, 3), last=None):
    obs = {"player": {"zone": "forest"},
           "quests": [{"id": "q_tut_02", "title": "약초", "state": "active",
                       "objectives": [{"text": "약초 3개 채집", "progress": list(prog), "hint_targets": ["herb_01", "herb_02"]}]}],
           "entities": [{"id": i, "distance": d} for i, d in entities], "screen": {"modal": modal, "ui": list(ui)}}
    return json.dumps({"last_action": last, "observation": obs}, ensure_ascii=False)


class SituationKeyTest(unittest.TestCase):
    def test_same_scene_different_text_same_key(self):
        a = _user([("herb_01", 12.5), ("portal_village", 30.0)])
        b = _user([("herb_01", 9.1), ("portal_village", 28.0)])          # 거리 숫자만 다름 = 같은 장면
        self.assertNotEqual(a, b)
        self.assertEqual(situation_key(a), situation_key(b))

    def test_key_splits_what_decides_the_action(self):
        far = situation_key(_user([("herb_01", 12.5)]))
        near = situation_key(_user([("herb_01", 2.0)]))
        dialog = situation_key(_user([("herb_01", 12.5)], ui=[{"id": "ui.dialog.choice.0", "role": "button", "text": "예"}]))
        failed = situation_key(_user([("herb_01", 12.5)], last={"tool": "interact", "status": "failed", "reason": "out_of_range"}))
        prog = situation_key(_user([("herb_01", 12.5)], prog=(1, 3)))
        self.assertEqual(len({far, near, dialog, failed, prog}), 5)

    def test_situation_prefix_still_reads_input(self):
        self.assertIn("약초 3개 채집 0/3", situation(_user([("herb_01", 2.0)])))


class RewardTest(unittest.TestCase):
    def test_progress_beats_plain_success_and_failure_is_negative(self):
        obs = json.loads(_user([("herb_01", 2.0)]))["observation"]
        prog = {"status": "done", "observation": {"events": [[0, "quest_progress", {}]]}}
        plain = {"status": "done", "observation": {"events": []}}
        self.assertEqual(reward(obs, "interact", {"target": "herb_01"}, prog), 1.0)
        self.assertEqual(reward(obs, "interact", {"target": "herb_01"}, plain), 0.5)    # 목표 대상에게 성공
        self.assertEqual(reward(obs, "wait", {}, plain), 0.0)
        self.assertEqual(reward(obs, "interact", {"target": "herb_01"}, {"status": "failed"}), -1.0)

    def test_same_modal_click_is_not_rewarded(self):
        """r10 보상 해킹: 창이 그대로인 성공 클릭에 점수를 주면 같은 버튼을 반복한다."""
        obs = {"quests": [], "entities": [], "screen": {"modal": "inventory"}}
        same = {"status": "done", "observation": {"screen": {"modal": "inventory"}, "events": []}}
        closed = {"status": "done", "observation": {"screen": {"modal": None}, "events": []}}
        self.assertEqual(reward(obs, "ui_click", {"ui_id": "x"}, same), 0.0)
        self.assertEqual(reward(obs, "ui_click", {"ui_id": "x"}, closed), 0.2)


class EvalSuiteFileTest(unittest.TestCase):
    def test_suite_is_valid_and_train_seeds_are_apart(self):
        s = load_suite(SUITE)
        from btqa_play.evaluate import parse_seeds
        ev = {(c.get("class"), x) for c in conditions(s) for x in parse_seeds(c["seeds"])}
        tr = {(c.get("class"), x) for c in conditions(s, groups=["train"]) for x in parse_seeds(c["seeds"])}
        self.assertFalse(ev & tr, "학습 seed 와 평가 seed 가 겹친다")
        self.assertEqual(set(s["adopt"]["improve_any"]), {"robust", "unseen"})

    def test_loadouts_in_suite_exist(self):
        if not (ROOT / "reports").exists():   # reports/ 는 git 제외 — 새 clone 에서는 확인할 것이 없다
            self.skipTest("reports/ 없음")
        for c in conditions(load_suite(SUITE), include_train=True):
            lo = (c.get("prepare") or {}).get("loadout")
            for p in ([lo] if isinstance(lo, str) else lo or []):
                self.assertTrue((ROOT / p / "params.json").exists() or (ROOT / p / "policy.json").exists(), p)


if __name__ == "__main__":
    unittest.main()


from play_agent.distill_rules import correct  # noqa: E402


def _rule_input(entities, modal=None, ui=(), last=None, quests=None, inventory=()):
    obs = {"player": {"zone": "village"}, "inventory": list(inventory),
           "quests": quests if quests is not None else [{"id": "q_tut_04", "state": "active", "objectives": [
               {"text": "상인에게 작은 물약 2개 구매", "progress": [0, 2], "hint_targets": ["npc_merchant"]}]}],
           "entities": [dict(id=i, distance=d, role=r, actions=a, label=i) for i, d, r, a in entities],
           "screen": {"modal": modal, "ui": [dict(id=u, role="button", text=t) for u, t in ui]}}
    return json.dumps({"last_action": last, "observation": obs}, ensure_ascii=False)


HUD = [("ui.hud.inventory", "인벤토리"), ("ui.hud.quests", "퀘스트")]
MERCHANT_FAR = [("npc_merchant", 12.0, "npc", ["talk"]), ("npc_elder", 2.1, "npc", ["talk"])]
MERCHANT_NEAR = [("npc_merchant", 2.1, "npc", ["talk"])]


class RuleTeacherTest(unittest.TestCase):
    def test_r1_far_interact_becomes_move(self):
        fx = correct(_rule_input(MERCHANT_FAR, ui=HUD), {"tool": "interact", "input": {"target": "npc_merchant", "verb": "talk"}})
        self.assertEqual((fx["tool"], fx["input"]["target"], fx["rule"]), ("move_to", "npc_merchant", "R1_range"))

    def test_r0_goal_in_reach_beats_detour(self):
        fx = correct(_rule_input(MERCHANT_NEAR, ui=HUD), {"tool": "ui_click", "input": {"ui_id": "ui.hud.inventory"}})
        self.assertEqual((fx["tool"], fx["input"]), ("interact", {"target": "npc_merchant", "verb": "talk"}))

    def test_r9_list_target_becomes_nearest_goal_or_defers(self):
        herbs = [{"id": "q_tut_02", "state": "active", "objectives": [
            {"text": "약초 3개 채집", "progress": [0, 3], "hint_targets": ["herb_01", "herb_02", "herb_03"]}]}]
        forest = [("herb_02", 6.0, "item", ["pickup"]), ("herb_01", 9.0, "item", ["pickup"])]
        bad = {"tool": "move_to", "input": {"target": "herb_01,herb_02,herb_03"}}
        fx = correct(_rule_input(forest, ui=HUD, quests=herbs), bad)
        self.assertEqual((fx["tool"], fx["input"]["target"], fx["rule"]), ("move_to", "herb_02", "R9_unknown_target"))
        self.assertIn("defer", correct(_rule_input(MERCHANT_FAR, ui=HUD, quests=herbs), bad))
        self.assertIsNone(correct(_rule_input(forest, ui=HUD, quests=herbs), {"tool": "move_to", "input": {"target": "herb_02"}}))

    def test_only_exit_when_goal_is_elsewhere(self):
        herbs = [{"id": "q_tut_02", "state": "active", "objectives": [
            {"text": "약초 3개 채집", "progress": [0, 3], "hint_targets": ["herb_01", "herb_02"]}]}]
        village = [("npc_elder", 2.1, "npc", ["talk"]), ("portal_forest", 32.0, "portal", ["enter"])]
        fx = correct(_rule_input(village, ui=HUD, quests=herbs), {"tool": "move_to", "input": {"target": None, "pos": None}})
        self.assertEqual((fx["input"]["target"], fx["rule"]), ("portal_forest", "R5_only_exit"))
        two = village + [("portal_cave", 20.0, "portal", ["enter"])]
        self.assertIn("defer", correct(_rule_input(two, ui=HUD, quests=herbs), {"tool": "move_to", "input": {"target": None}}))

    def test_r10_finish_only_after_repeated_talk_with_no_quests(self):
        guard = [("npc_guard", 2.2, "npc", ["talk"])]
        talk = {"tool": "interact", "input": {"target": "npc_guard", "verb": "talk"}, "status": "done"}
        choice = {"tool": "ui_click", "input": {"ui_id": "ui.dialog.choice.0"}, "status": "done"}
        d = json.loads(_rule_input(guard, ui=HUD, last=choice, quests=[]))
        d["recent_actions"] = [talk, choice, choice, talk]
        fx = correct(json.dumps(d, ensure_ascii=False), {"tool": "ui_click", "input": {"ui_id": "ui.dialog.choice.1"}})
        self.assertEqual((fx["tool"], fx["rule"]), ("finish", "R10_done_finish"))
        d["recent_actions"] = []   # 판 시작: 퀘스트 없음이 정상
        d["last_action"] = None
        self.assertIsNone(correct(json.dumps(d, ensure_ascii=False), {"tool": "interact", "input": {"target": "npc_guard", "verb": "talk"}}))

    def test_r2_repeat_in_inventory_closes_but_shop_repeat_is_fine(self):
        inv = [("ui.inventory.assign", "퀵슬롯 1에 등록"), ("ui.inventory.close", "닫기")]
        last = {"tool": "ui_click", "input": {"ui_id": "ui.inventory.assign"}, "status": "done"}
        fx = correct(_rule_input(MERCHANT_FAR, "inventory", inv, last), {"tool": "ui_click", "input": {"ui_id": "ui.inventory.assign"}})
        self.assertEqual(fx["input"]["ui_id"], "ui.inventory.close")
        shop = [("ui.shop.buy.potion_small", "구매"), ("ui.shop.close", "닫기")]
        last = {"tool": "ui_click", "input": {"ui_id": "ui.shop.buy.potion_small"}, "status": "done"}
        self.assertIsNone(correct(_rule_input(MERCHANT_NEAR, "shop", shop, last), {"tool": "ui_click", "input": {"ui_id": "ui.shop.buy.potion_small"}}))

    def test_r7_modal_blocks_move_uses_objective_button(self):
        shop = [("ui.shop.buy.potion_small", "구매"), ("ui.shop.close", "닫기")]
        fx = correct(_rule_input(MERCHANT_NEAR, "shop", shop), {"tool": "move_to", "input": {"target": "npc_merchant"}})
        self.assertEqual(fx["input"]["ui_id"], "ui.shop.buy.potion_small")

    def test_r3_early_finish_and_allowed_give_up(self):
        q = [{"id": "q_tut_05", "state": "active", "objectives": [{"text": "늑대왕 처치", "progress": [0, 1], "hint_targets": ["wolf_king"]}]}]
        wolf = [("wolf_king", 55.0, "enemy", ["engage"])]
        fin = {"tool": "finish", "input": {"success": True}}
        self.assertEqual(correct(_rule_input(wolf, quests=q), fin)["tool"], "engage")
        lost = {"tool": "engage", "input": {"target": "wolf_king"}, "status": "done", "combats": [{"cleared": False}]}
        self.assertIsNone(correct(_rule_input(wolf, quests=q, last=lost), fin))                 # 지고 물약 없음 → 포기 허용
        self.assertEqual(correct(_rule_input(wolf, quests=q, last=lost, inventory=[{"id": "potion_small", "count": 1}]), fin)["tool"],
                         "engage")

    def test_defer_when_rules_cannot_decide(self):
        q = [{"id": "q_x", "state": "active", "objectives": [{"text": "무언가", "progress": [0, 1], "hint_targets": ["npc_far_away"]}]}]
        fx = correct(_rule_input([], quests=q, ui=HUD), {"tool": "move_to", "input": {"target": None, "pos": None}})
        self.assertIn("defer", fx)

    def test_no_false_positives_on_good_actions(self):
        self.assertIsNone(correct(_rule_input(MERCHANT_FAR, ui=HUD), {"tool": "move_to", "input": {"target": "npc_merchant"}}))
        self.assertIsNone(correct(_rule_input(MERCHANT_NEAR, ui=HUD), {"tool": "interact", "input": {"target": "npc_merchant", "verb": "talk"}}))


from play_agent.distill_prep import repetition  # noqa: E402


def _hist_input(seq, last):
    d = json.loads(_rule_input(MERCHANT_FAR, ui=HUD, last=last))
    return json.dumps(dict(recent_actions=seq, **d), ensure_ascii=False)


A = {"tool": "move_to", "input": {"target": "herb_03"}, "status": "done"}
B = {"tool": "interact", "input": {"target": "portal_village", "verb": "enter"}, "status": "failed", "reason": "out_of_range"}


class HistoryReadingTest(unittest.TestCase):
    def test_repetition_text(self):
        self.assertEqual(repetition(json.loads(_rule_input(MERCHANT_FAR, last=A))), "")            # 옛 형식 = 읽을 것 없음
        self.assertIn("번갈아", repetition(json.loads(_hist_input([A, B, A], B))))
        self.assertIn("같은 행동 3번째", repetition(json.loads(_hist_input([B, A, A], A))))
        k1 = situation_key(_hist_input([B, A, A], A))
        k2 = situation_key(_hist_input([], A))
        self.assertNotEqual(k1, k2)                                                               # 반복 중인 장면은 다른 상황

    def test_r8_defers_on_continuing_loop(self):
        fx = correct(_hist_input([A, B, A], B), {"tool": "move_to", "input": {"target": "herb_03"}})
        self.assertIn("defer", fx)
        self.assertIsNone(correct(_hist_input([], A), {"tool": "move_to", "input": {"target": "npc_merchant"}}))
