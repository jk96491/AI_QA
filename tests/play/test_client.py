"""PlayClient · LoadoutBuilder · LlmPilot — 가짜 게임 서버 / 가짜 API 로 (네트워크·LLM 없음)."""
from __future__ import annotations

import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from play_agent.client import PlayClient, PlayError
from play_agent.loadout import LoadoutBuilder
from play_agent.pilot import LlmPilot, PilotConfig
from play_agent.tools import build_tools

OBS = {"type": "observation", "seq": 1, "player": {"zone": "village", "gold": 20, "quickslots": [None, None]},
       "quests": [{"id": "q_tut_01", "state": "active", "objectives": [{"progress": [0, 1]}]}], "inventory": [], "entities": [],
       "screen": {"modal": None, "ui": []}, "events": []}


class FakeGame:
    """요청 1개마다 handler(msg, send) 를 부르는 1연결 TCP 서버."""

    def __init__(self, handler):
        self.handler = handler
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.received = []
        self.t = threading.Thread(target=self._serve, daemon=True)
        self.t.start()

    def _serve(self):
        conn, _ = self.srv.accept()
        f = conn.makefile("rwb")

        def send(m):
            f.write((json.dumps(m, ensure_ascii=False) + "\n").encode("utf-8"))
            f.flush()

        for line in f:
            m = json.loads(line.decode("utf-8"))
            self.received.append(m)
            if m.get("type") == "bye":
                break
            self.handler(m, send)
        conn.close()
        self.srv.close()


def play_handler(accept_versions=("0.1",), bad_trigger=False):
    def h(m, send):
        t = m["type"]
        if t == "hello":
            if m.get("protocol_version") in accept_versions:
                send({"type": "hello_ok", "protocol": "play", "protocol_version": m["protocol_version"], "game": "fake", "game_version": "0.6.2"})
            else:
                send({"type": "error", "code": "protocol_version", "message": "need 0.1"})
        elif t == "play_describe":
            send({"type": "play_description", "game": "fake", "game_version": "0.6.2", "classes": ["warrior"],
                  "scenarios": [{"name": "base", "boss": "default"}, {"name": "forest_wolf_king", "boss": "forest_wolf_king"}],
                  "actions": [{"name": "move_to", "args": {}}, {"name": "interact", "args": {"verb": "talk|pickup"}}],
                  "combat": {"trigger_state_features": ["hp_ratio"]}, "quests": []})
        elif t == "act":
            if m["args"].get("pos") == [0, 0, 32]:
                send({"type": "combat_started", "seq": m["seq"], "encounter_id": "enc_1", "class": "warrior", "scenario": "forest_wolf_king"})
                send({"type": "trigger", "seq": m["seq"], "encounter_id": "enc_1", "index": 0, "state": {"hp_ratio": 1.0}, "totals": {}})
                # trigger_response 는 다음 요청으로 들어온다 → 상태를 핸들러 밖에 둔다
                h.pending = m
                return
            send({"type": "action_result", "seq": m["seq"], "status": "done", "game_seconds": 1.0, "observation": OBS})
        elif t == "trigger_response":
            if bad_trigger:
                send({"type": "error", "code": "param_out_of_range", "message": "bad"})
                return
            send({"type": "combat_ended", "seq": h.pending["seq"], "encounter_id": "enc_1", "result": {"cleared": True, "elapsed": 300.0},
                  "aftermath": {"xp": 40, "loot": [], "respawned_at": None}})
            send({"type": "action_result", "seq": h.pending["seq"], "status": "interrupted", "interrupted_by": "combat",
                  "game_seconds": 301.0, "observation": OBS})
    h.pending = None
    return h


class PlayClientTest(unittest.TestCase):
    def test_hello_falls_back_to_0_1_and_notes_it(self):
        g = FakeGame(play_handler())
        with PlayClient("127.0.0.1", g.port) as c:
            r = c.hello()
            self.assertEqual(r["type"], "hello_ok")
            self.assertEqual(c.protocol_version, "0.1")
            self.assertTrue(c.notes)
        self.assertEqual([m["protocol_version"] for m in g.received if m["type"] == "hello"], ["0.2", "0.1"])

    def test_act_collects_combat_and_answers_trigger_immediately(self):
        g = FakeGame(play_handler(accept_versions=("0.2",)))
        seen = []

        class R:
            def on_combat_started(self, m):
                seen.append(m["scenario"])

            def __call__(self, m):
                return {"w_survival": 0.42}

        with PlayClient("127.0.0.1", g.port) as c:
            c.hello()
            r = c.act("move_to", {"pos": [0, 0, 32]}, responder=R())
            self.assertEqual(r.status, "interrupted")
            self.assertEqual(len(r.combats), 1)
            self.assertTrue(r.combats[0].cleared)
            self.assertEqual(r.combats[0].replies, [{"w_survival": 0.42}])
            self.assertEqual(seen, ["forest_wolf_king"])
        tr = [m for m in g.received if m["type"] == "trigger_response"]
        self.assertEqual(tr, [{"type": "trigger_response", "encounter_id": "enc_1", "index": 0, "params": {"w_survival": 0.42}}])

    def test_error_during_combat_raises(self):
        g = FakeGame(play_handler(accept_versions=("0.2",), bad_trigger=True))
        with PlayClient("127.0.0.1", g.port) as c:
            c.hello()
            with self.assertRaises(PlayError) as cm:
                c.act("move_to", {"pos": [0, 0, 32]}, responder=lambda m: {"w_dps": 9})
            self.assertEqual(cm.exception.code, "param_out_of_range")


class LoadoutBuilderTest(unittest.TestCase):
    def test_static_params_json_to_entry(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "reports" / "20261123-001010"
            run.mkdir(parents=True)
            (run / "params.json").write_text(json.dumps({
                "class": "warrior", "persona": "stable", "method": "cma", "scenario": "forest_wolf_king",
                "source": {"type": "static", "params": {"w_dps": 0.9, "potion_hp": 0.5}},
                "game": {"name": "qa_arena", "version": "0.6.1", "protocol": "1.2"}}), encoding="utf-8")
            lb = LoadoutBuilder()
            e = lb.add_file(run)
            self.assertEqual(e.key, ("warrior", "forest_wolf_king"))
            self.assertEqual(e.source, "reports/20261123-001010 (cma)")
            desc = {"classes": ["warrior"], "game_version": "0.6.2",
                    "scenarios": [{"name": "forest_wolf_king", "boss": "forest_wolf_king"}]}
            self.assertEqual(lb.check_against(desc), [])
            self.assertTrue(any("0.6.1" in n for n in lb.notes))   # 버전 차이 경고
            self.assertEqual(lb.wire_entries(desc), [{"class": "warrior", "scenario": "forest_wolf_king", "boss": "forest_wolf_king",
                                                      "params": {"w_dps": 0.9, "potion_hp": 0.5},
                                                      "source": "reports/20261123-001010 (cma)"}])
            self.assertEqual(LoadoutBuilder.find_latest(Path(d) / "reports", "warrior", "forest_wolf_king"), run / "params.json")
            self.assertIsNone(LoadoutBuilder.find_latest(Path(d) / "reports", "mage", "forest_wolf_king"))

    def test_unknown_scenario_reported(self):
        lb = LoadoutBuilder()
        lb.entries[("warrior", "nope")] = LoadoutBuilder.entry_from_dict(
            {"class": "warrior", "scenario": "nope", "method": "cma", "source": {"type": "static", "params": {}}})
        self.assertTrue(lb.check_against({"classes": ["warrior"], "scenarios": [{"name": "base"}]}))


class ToolsTest(unittest.TestCase):
    def test_tools_follow_description_and_are_strict(self):
        tools = build_tools({"actions": [{"name": "move_to", "args": {}}, {"name": "interact", "args": {"verb": "talk|pickup"}}]})
        names = [t["name"] for t in tools]
        self.assertEqual(names, ["move_to", "interact", "inspect_ui", "finish"])   # ui_input 등 게임이 안 준 것은 없음
        for t in tools:
            s = t["input_schema"]
            self.assertTrue(t["strict"])
            self.assertFalse(s["additionalProperties"])
            self.assertEqual(sorted(s["required"]), sorted(s["properties"]))
        self.assertEqual(tools[1]["input_schema"]["properties"]["verb"]["enum"], ["talk", "pickup"])


def block(**kw):
    return SimpleNamespace(**kw)


class FakeApi:
    """messages.create 만 흉내: 정해 둔 응답을 차례로 돌려주고 요청을 기록."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = self

    def create(self, **kw):
        self.requests.append(dict(kw, messages=list(kw["messages"])))   # 루프가 같은 리스트에 계속 붙이므로 그 시점 복사
        return self.responses.pop(0)


def resp(content, stop="tool_use"):
    return SimpleNamespace(content=content, stop_reason=stop,
                           usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=3, cache_creation_input_tokens=0))


class PilotTest(unittest.TestCase):
    def test_loop_runs_tools_until_finish(self):
        g = FakeGame(play_handler(accept_versions=("0.2",)))
        api = FakeApi([
            resp([block(type="thinking", thinking=""), block(type="text", text="숲으로"),
                  block(type="tool_use", id="t1", name="move_to", input={"target": None, "pos": [0, 0, 32]})]),
            resp([block(type="text", text="생각만")], stop="end_turn"),          # 도구 없음 → 상기
            resp([block(type="tool_use", id="t2", name="finish", input={"success": True, "summary": "ok", "blocked": None})]),
        ])
        with PlayClient("127.0.0.1", g.port) as c:
            c.hello()
            c.describe()
            run = LlmPilot(c, responder=lambda m: None, config=PilotConfig(), api_client=api).run(OBS)
        self.assertEqual(run.end_reason, "finish")
        self.assertEqual(run.actions, 1)
        self.assertEqual(run.api_calls, 3)
        self.assertEqual(run.combats[0]["cleared"], True)
        self.assertEqual(run.usage["input_tokens"], 30)
        r0 = api.requests[0]
        self.assertEqual(r0["model"], "claude-opus-5-5")
        self.assertEqual(r0["output_config"], {"effort": "low"})
        self.assertEqual(r0["system"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("tool_choice", r0)
        # 도구 결과: move_to 의 None 인자는 게임에 보내지 않고, 전투 요약이 결과에 실린다
        act = next(m for m in g.received if m["type"] == "act")
        self.assertEqual(act["args"], {"pos": [0, 0, 32]})
        tr = api.requests[1]["messages"][-1]["content"][0]
        self.assertEqual(tr["tool_use_id"], "t1")
        out = json.loads(tr["content"])
        self.assertEqual(out["status"], "interrupted")
        self.assertEqual(out["combats"][0]["enemy"], None)
        self.assertTrue(out["combats"][0]["cleared"])
        self.assertEqual(api.requests[2]["messages"][-1]["role"], "user")   # 상기 메시지

    def test_no_progress_stops(self):
        g = FakeGame(play_handler(accept_versions=("0.2",)))
        call = resp([block(type="tool_use", id="t", name="move_to", input={"target": "npc", "pos": None})])
        api = FakeApi([call] * 5)
        with PlayClient("127.0.0.1", g.port) as c:
            c.hello()
            c.describe()
            run = LlmPilot(c, config=PilotConfig(no_progress_actions=3), api_client=api).run(OBS)
        self.assertEqual(run.end_reason, "no_progress")
        self.assertEqual(run.actions, 3)


if __name__ == "__main__":
    unittest.main()
