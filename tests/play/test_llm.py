"""LLM 백엔드 — OpenAI 호환(가짜 HTTP)·설정 파일·LlmPilot 연동 (네트워크·LLM 없음)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from play_agent.client import PlayClient
from play_agent.llm import load_config, make_backend
from play_agent.llm.base import STOP_TOOL_USE, ToolResult
from play_agent.llm.openai_compat import OpenAICompatBackend
from play_agent.pilot import LlmPilot, PilotConfig
from tests.play.test_client import OBS, FakeGame, play_handler


class FakePost:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": dict(headers), "body": json.loads(json.dumps(body))})
        return self.replies.pop(0)


def tool_reply(name, args, cid="c1", text=""):
    return {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": text,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 7}}


class OpenAICompatTest(unittest.TestCase):
    def test_request_shape_and_tool_round_trip(self):
        post = FakePost([tool_reply("move_to", {"target": "npc_elder", "pos": None}, text="촌장에게 간다")])
        b = OpenAICompatBackend("qwen2.5:14b", base_url="http://localhost:11434/v1/", post=post)
        b.start("SYS", [{"name": "move_to", "description": "d", "input_schema": {"type": "object"}, "strict": True}], "시작")
        turn = b.complete()
        self.assertEqual(turn.stop, STOP_TOOL_USE)
        self.assertEqual(turn.texts, ["촌장에게 간다"])
        self.assertEqual((turn.calls[0].name, turn.calls[0].input), ("move_to", {"target": "npc_elder", "pos": None}))
        c = post.calls[0]
        self.assertEqual(c["url"], "http://localhost:11434/v1/chat/completions")
        self.assertNotIn("Authorization", c["headers"])                       # 로컬: 키 없음
        self.assertEqual(c["body"]["tools"][0], {"type": "function", "function": {"name": "move_to", "description": "d",
                                                                                 "parameters": {"type": "object"}}})
        self.assertEqual(c["body"]["messages"][0], {"role": "system", "content": "SYS"})
        b.add_tool_results([ToolResult("c1", '{"status":"done"}')])
        self.assertEqual(b.messages[-1], {"role": "tool", "tool_call_id": "c1", "content": '{"status":"done"}'})
        self.assertEqual(b.usage, {"input_tokens": 100, "output_tokens": 7})

    def test_bad_arguments_become_error_call(self):
        bad = {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
               "tool_calls": [{"id": "x", "function": {"name": "move_to", "arguments": "{nope"}}]}}]}
        b = OpenAICompatBackend("m", post=FakePost([bad]))
        b.start("S", [], "u")
        self.assertIn("JSON", b.complete().calls[0].error)

    def test_key_read_from_env_only(self):
        post = FakePost([{"choices": [{"finish_reason": "stop", "message": {"content": "hi"}}]}])
        b = OpenAICompatBackend("m", api_key_env="BTQA_TEST_KEY", post=post)
        b.start("S", [], "u")
        os.environ.pop("BTQA_TEST_KEY", None)
        with self.assertRaises(RuntimeError):
            b.complete()
        os.environ["BTQA_TEST_KEY"] = "abc"
        try:
            b.complete()
        finally:
            os.environ.pop("BTQA_TEST_KEY", None)
        self.assertEqual(post.calls[-1]["headers"]["Authorization"], "Bearer abc")


class ConfigTest(unittest.TestCase):
    def test_file_then_cli_override_and_secret_guard(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "llm.json"
            p.write_text(json.dumps({"llm": "openai", "model": "a", "base_url": "http://x/v1"}), encoding="utf-8")
            cfg = load_config(str(p), {"model": "b", "effort": None})
            self.assertEqual(cfg, {"llm": "openai", "model": "b", "base_url": "http://x/v1"})
            self.assertEqual(make_backend(cfg).label, "openai:b@http://x/v1")
            p.write_text(json.dumps({"llm": "openai", "api_key": "sk-123"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(str(p))
        with self.assertRaises(ValueError):
            make_backend({})                      # LLM 을 안 고르면 안내와 함께 거부
        with self.assertRaises(ValueError):
            make_backend({"llm": "openai"})       # openai 는 model 필수

    def test_example_file_is_valid(self):
        cfg = load_config("play_agent/llm.example.json")
        self.assertEqual(make_backend(cfg).label, "openai:qwen2.5:14b@http://localhost:11434/v1")


class PilotWithOpenAITest(unittest.TestCase):
    def test_pilot_runs_on_openai_backend_and_notes_text(self):
        g = FakeGame(play_handler(accept_versions=("0.3",), pilot_notes=True))
        post = FakePost([tool_reply("move_to", {"target": None, "pos": [0, 0, 32]}, text="숲으로 간다"),
                         tool_reply("finish", {"success": True, "summary": "ok", "blocked": None}, cid="c2")])
        with PlayClient("127.0.0.1", g.port) as c:
            c.hello()
            c.describe()
            run = LlmPilot(c, responder=lambda m: None, config=PilotConfig(),
                           backend=OpenAICompatBackend("m", post=post)).run(OBS)
        self.assertEqual(run.end_reason, "finish")
        self.assertEqual(run.llm, "openai:m@http://localhost:11434/v1")
        self.assertEqual(run.usage["input_tokens"], 200)
        self.assertEqual([m["text"] for m in g.received if m["type"] == "pilot_note"], ["숲으로 간다"])
        tool_msgs = [m for m in post.calls[1]["body"]["messages"] if m["role"] == "tool"]
        self.assertEqual(json.loads(tool_msgs[0]["content"])["status"], "interrupted")   # 전투 요약이 도구 결과로


if __name__ == "__main__":
    unittest.main()
