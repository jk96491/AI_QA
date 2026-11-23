"""PilotRelay — 대화형 에이전트(예: Claude Code 세션)가 직접 플레이어가 되는 중계기. API 호출 없음.

LlmPilot 은 Claude API 를 스스로 부르는 루프다. 이 중계기는 반대로 루프를 바깥 에이전트에게 맡긴다:

    host  : 게임에 접속(hello·describe·set_loadout·reset)해 연결을 붙잡고, 127.0.0.1:<port> 에서 도구 호출을 기다린다
    step  : 도구 호출 1개 {"tool": ..., "input": {...}, "thought": "...", "kind": "thought"} 를 host 에 보내고
            결과(JSON 한 줄)를 출력하고 끝난다. thought 가 있으면 행동 전에 pilot_note(v0.3)로 게임 화면에 띄운다.
            tool = "note" 면 행동 없이 메모만, "intro" 면 처음 관찰.

도구 = LlmPilot 과 같은 GameTools (전투는 학습된 BT·응답기가 끝낸다). finish 를 받으면 host 가
reports/relay-<시각>/run.json·play_log.json 을 남기고 종료한다. 중계 메시지는 게임 프로토콜과 별개 (JSON Lines).
"""
from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from play_agent.client import PlayClient
from play_agent.loadout import LoadoutBuilder
from play_agent.tools import GameTools, build_tools, compact_observation, to_text

DEFAULT_RELAY_PORT = 7899


class PilotRelay:
    def __init__(self, game: str, loadout: Optional[List[str]] = None, seed: int = 1, cls: str = "warrior",
                 port: int = DEFAULT_RELAY_PORT, out: str = "reports", pilot: str = "claude-code") -> None:
        self.game, self.seed, self.cls, self.port, self.out, self.pilot = game, seed, cls, port, Path(out), pilot
        self.lb = LoadoutBuilder()
        for p in loadout or []:
            self.lb.add_file(p)
        self.transcript: List[Dict[str, Any]] = []
        self.client: Any = None

    def serve(self) -> Path:
        t0 = time.time()
        with PlayClient.connect(self.game) as c:
            c.hello()
            desc = c.describe()
            problems = self.lb.check_against(desc)
            if problems:
                raise SystemExit("로드아웃 문제: " + "; ".join(problems))
            if self.lb.entries:
                c.set_loadout(self.lb.wire_entries(desc), persona=self.lb.persona())
            first = c.reset(seed=self.seed, cls=self.cls)
            tools = GameTools(c, self.lb.responder())
            intro = {"game": "%s %s" % (desc.get("game"), desc.get("game_version")),
                     "quests_in_game": desc.get("quests"),
                     "tools": [{"name": t["name"], "args": list(t["input_schema"]["properties"])} for t in build_tools(desc, strict=False)],
                     "observation": compact_observation(first)}
            self.client = c
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(("127.0.0.1", self.port))
                srv.listen(1)
                print("relay ready 127.0.0.1:%d (game %s)" % (self.port, self.game), flush=True)
                while tools.finished is None:
                    conn, _ = srv.accept()
                    with conn:
                        req = json.loads(conn.makefile("rb").readline().decode("utf-8"))
                        out = self._handle(tools, req, intro)
                        conn.sendall((to_text(out) + "\n").encode("utf-8"))
            log = c.get_log()
            notes = c.notes + self.lb.notes
        return self._save(desc, tools, log, notes, round(time.time() - t0, 1))

    def _handle(self, tools: GameTools, req: Mapping[str, Any], intro: Mapping[str, Any]) -> Dict[str, Any]:
        name, inp = req.get("tool"), dict(req.get("input") or {})
        if name == "intro":   # 처음 관찰·도구 목록 다시 보기 (행동 아님)
            return dict(intro)
        thought, kind = req.get("thought"), str(req.get("kind") or "thought")
        shown = None
        if thought:
            shown = self.client.note(str(thought), kind)
        if name == "note":   # 메모만
            self.transcript.append({"note": thought, "kind": kind, "shown": shown})
            return {"ok": True, "shown": shown}
        try:
            out = tools.execute(str(name), inp)
        except Exception as e:   # PlayError 등 → 세션 종료로 기록
            tools.finished = {"success": False, "summary": "relay error", "blocked": "game_error: %s" % e}
            out = {"error": str(e)}
        self.transcript.append({"tool": name, "input": inp, "thought": thought, "kind": kind if thought else None, "shown": shown, "status": out.get("status"), "reason": out.get("reason"),
                                "error": out.get("error"), "combats": out.get("combats")})
        return out

    def _save(self, desc: Mapping[str, Any], tools: GameTools, log: Mapping[str, Any], notes: List[str], seconds: float) -> Path:
        out = self.out / ("relay-" + time.strftime("%Y%m%d-%H%M%S"))
        out.mkdir(parents=True, exist_ok=True)
        run = {"game": "%s %s" % (desc.get("game"), desc.get("game_version")), "seed": self.seed, "class": self.cls,
               "pilot": self.pilot, "loadout": [e.source for e in self.lb.entries.values()], "notes": notes,
               "end_reason": "finish", "finish": tools.finished, "actions": tools.actions,
               "combats": [x.summary() for x in tools.combats], "seconds": seconds,
               "last_observation": tools.last_observation, "transcript": self.transcript,
               "pilot_notes": self.client.pilot_notes, "pilot_notes_shown_in_game": self.client.supports_pilot_notes}
        (out / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (out / "play_log.json").write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")
        print("기록:", out, flush=True)
        return out


def relay_step(tool: str, tool_input: Mapping[str, Any], port: int = DEFAULT_RELAY_PORT,
               thought: Optional[str] = None, kind: str = "thought") -> str:
    req: Dict[str, Any] = {"tool": tool, "input": dict(tool_input)}
    if thought:
        req.update(thought=thought, kind=kind)
    with socket.create_connection(("127.0.0.1", port)) as s:
        s.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
        return s.makefile("rb").readline().decode("utf-8").strip()
