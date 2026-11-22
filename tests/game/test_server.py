"""게임 서버 프로토콜 테스트 (원시 소켓, balance_qa 없이). Unity 구현이 따라야 할 동작의 예시이기도 하다."""
import json
import socket
import unittest

from game_sim.server.server import GameServer


class RawClient:
    def __init__(self, address):
        self.sock = socket.create_connection(address, timeout=30)
        self.f = self.sock.makefile("rwb")

    def send(self, msg):
        self.f.write((json.dumps(msg) + "\n").encode("utf-8"))
        self.f.flush()

    def send_raw(self, data: bytes):
        self.f.write(data)
        self.f.flush()

    def recv(self):
        return json.loads(self.f.readline().decode("utf-8"))

    def close(self):
        self.f.close()
        self.sock.close()


class GameServerProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = GameServer(port=0)
        cls.server.start_in_thread()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.c = RawClient(self.server.address)

    def tearDown(self):
        self.c.send({"type": "bye"})
        self.c.close()

    def test_hello_and_version_mismatch(self):
        self.c.send({"type": "hello", "protocol_version": "1.0"})  # 같은 주 버전이면 허용
        self.assertEqual(self.c.recv()["type"], "hello_ok")
        self.c.send({"type": "hello", "protocol_version": "2.0"})
        reply = self.c.recv()
        self.assertEqual((reply["type"], reply["code"]), ("error", "protocol_version"))

    def test_describe_exposes_params_not_skills(self):
        self.c.send({"type": "describe"})
        d = self.c.recv()
        self.assertEqual(d["type"], "description")
        mage = next(c for c in d["classes"] if c["name"] == "mage")
        self.assertNotIn("skills", mage)
        names = {p["name"] for p in mage["params"]}
        self.assertTrue({"w_burst", "survival_hp_threshold", "kite_distance"} <= names)
        self.assertEqual(d["triggers"]["supported"], [0.75, 0.5, 0.25])

    def test_static_episode(self):
        self.c.send({"type": "run_episode", "episode_id": "a", "class": "archer", "seed": 5})
        r = self.c.recv()
        self.assertEqual((r["type"], r["episode_id"]), ("episode_result", "a"))
        self.assertEqual(r["result"]["seed"], 5)
        self.assertNotIn("events", r["result"])

    def test_trigger_roundtrip(self):
        self.c.send({"type": "run_episode", "episode_id": "t", "class": "warrior", "seed": 1,
                     "triggers": {"boss_hp_below": [0.5]}})
        indices = []
        while True:
            m = self.c.recv()
            if m["type"] != "trigger":
                break
            indices.append(m["index"])
            self.assertEqual(set(m["totals"]), {"elapsed", "deaths", "consumables_used", "boss_hp_remaining"})
            self.c.send({"type": "trigger_response", "episode_id": "t", "index": m["index"], "params": {}})
        self.assertEqual(m["type"], "episode_result")
        self.assertEqual(indices, [0, 1])

    def test_wrong_trigger_response_is_error_and_connection_survives(self):
        self.c.send({"type": "run_episode", "episode_id": "w", "class": "warrior", "seed": 1,
                     "triggers": {"boss_hp_below": [0.5]}})
        self.assertEqual(self.c.recv()["type"], "trigger")
        self.c.send({"type": "trigger_response", "episode_id": "WRONG", "index": 0, "params": {}})
        self.assertEqual(self.c.recv()["code"], "bad_request")
        self.c.send({"type": "describe"})
        self.assertEqual(self.c.recv()["type"], "description")

    def test_errors(self):
        cases = [
            ({"type": "nope"}, "unknown_type"),
            ({"type": "run_episode", "episode_id": "x", "class": "zzz", "seed": 1}, "unknown_class"),
            ({"type": "run_episode", "episode_id": "x", "class": "mage", "seed": 1, "scenario": "zzz"}, "unknown_scenario"),
            ({"type": "run_episode", "episode_id": "x", "class": "mage", "seed": 1, "params": {"zzz": 1}}, "unknown_param"),
            ({"type": "run_episode", "episode_id": "x", "class": "mage", "seed": 1, "params": {"w_dps": 9}}, "param_out_of_range"),
            ({"type": "run_episode", "class": "mage"}, "bad_request"),
        ]
        for msg, code in cases:
            self.c.send(msg)
            reply = self.c.recv()
            self.assertEqual((reply["type"], reply["code"]), ("error", code), msg)

    def test_malformed_json(self):
        self.c.send_raw(b"{not json}\n")
        self.assertEqual(self.c.recv()["code"], "bad_request")


if __name__ == "__main__":
    unittest.main()
