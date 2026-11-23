"""LlmPilot — 비전투를 LLM 이 플레이하는 수동 tool use 루프 (PLAY_PROTOCOL 5장). LLM 은 사용자가 고른다.

- LLM 은 `play_agent.llm.LlmBackend` (Claude API / OpenAI 호환 로컬·클라우드). 안내 docs/LLM_SETUP.md
- 시스템 프롬프트·도구 목록은 세션 내내 고정 (Claude 는 프롬프트 캐시)
- 전투는 도구 실행(PlayClient.act) 안에서 학습된 BT·응답기가 끝내고, 요약만 도구 결과에 실린다
- LLM 이 말한 텍스트는 pilot_note(thought) 로 게임 화면에 표시 (play v0.3, 아니면 기록만)
- 상한: 행동 수, API 호출 수, 진척 없음(N 행동 동안 퀘스트·지역·인벤토리·골드 변화 없음)
- 결과: PilotRun (끝난 이유, finish 요약, 전투, 토큰 사용량, 대화 기록) — 재현은 게임 get_log 의 행동열로

anthropic SDK 는 AnthropicBackend 안에서만 import → openai 백엔드·나머지 play_agent 는 프로젝트 venv(3.8)에서도 돈다.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from play_agent.client import PlayClient
from play_agent.llm.base import STOP_MAX_TOKENS, STOP_PAUSE, STOP_REFUSAL, LlmBackend, ToolResult
from play_agent.tools import GameTools, build_tools, compact_observation, to_text

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """너는 게임 QA 플레이어다. Unity 게임의 비전투 부분(이동·대화·퀘스트·아이템·UI)을 도구로 직접 플레이한다.

게임 화면 대신 구조화된 관찰(JSON)을 받는다:
- player: 지역·위치·체력·골드·퀵슬롯·상태
- quests: 진행 중인 퀘스트와 목표 (progress [현재, 목표], hint_targets = 관련 엔티티 id). state=ready 는 반납만 남은 것
- entities: 지금 보이는 것만 (시야 밖은 없다). marker: quest_available / quest_turn_in / objective
- screen.modal: 입력을 막는 창 (dialog / quests / inventory / shop / tip). screen.ui: 클릭 가능한 UI 요소 (interactable)
- events: 직전 이후 일어난 일

규칙:
- 세계는 네가 행동할 때만 흐른다. 서두를 필요 없다.
- 행동은 반드시 도구로 한다. 한 번에 도구 하나씩 부르고 결과를 보고 다음을 정한다.
- 도구를 부르기 전에 왜 그 행동을 하는지 한 문장으로 말한다 (게임 화면에 플레이어 생각으로 표시된다).
- 상호작용은 먼저 move_to 로 다가간 뒤 interact. 보이지 않는 대상은 근처 좌표나 지역 입구로 먼저 간다.
- 창(modal)이 열려 있으면 그 창의 버튼으로 진행하거나 닫는다. interactable:false 버튼은 가려졌거나 비활성이다 — 가린 창부터 처리한다.
- 전투는 네가 하지 않는다. 적에게 다가가거나 engage 하면 학습된 전투 AI 가 싸우고 결과가 combats 로 온다. 전투 물약은 퀵슬롯에 등록한 인벤토리 물약이다. 지면 체크포인트에서 부활하니 다시 시도할 수 있다.
- 목표를 다 이뤘거나, 같은 시도를 반복해도 진척이 없으면 finish 를 부른다. 게임 버그로 보이는 것은 blocked 에 구체적으로 적는다 (UI id·메시지 포함).
- 말은 짧게."""


@dataclass
class PilotConfig:
    model: str = DEFAULT_MODEL        # api_client 를 직접 줄 때(AnthropicBackend) 만 쓴다
    effort: str = "low"
    max_tokens: int = 8000
    max_actions: int = 150            # 게임 행동 수 상한
    max_calls: int = 250              # LLM 호출 상한
    no_progress_actions: int = 25     # 이만큼 행동하는 동안 진척 없으면 중단
    goal: str = "튜토리얼 퀘스트를 모두 끝까지 완료하라 (진행 중인 퀘스트가 없어질 때까지)."


@dataclass
class PilotRun:
    end_reason: str = ""
    llm: str = ""
    finish: Optional[Dict[str, Any]] = None
    actions: int = 0
    api_calls: int = 0
    combats: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0
    last_observation: Dict[str, Any] = field(default_factory=dict)
    transcript: List[Dict[str, Any]] = field(default_factory=list)   # (assistant 텍스트·도구 호출·결과 요약)

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in ("end_reason", "llm", "finish", "actions", "api_calls", "combats", "usage",
                                              "seconds", "last_observation", "transcript")}


def progress_signature(obs: Mapping[str, Any]) -> str:
    """진척 판단용: 퀘스트 상태·진행도, 지역, 인벤토리, 골드, 퀵슬롯."""
    p = obs.get("player") or {}
    q = [(x.get("id"), x.get("state"), [tuple(o.get("progress") or ()) for o in x.get("objectives") or []])
         for x in obs.get("quests") or []]
    inv = sorted((i.get("id"), i.get("count")) for i in obs.get("inventory") or [])
    return json.dumps([q, p.get("zone"), inv, p.get("gold"), p.get("quickslots")], ensure_ascii=False, default=str)


class LlmPilot:
    def __init__(self, client: PlayClient, responder: Any = None, config: Optional[PilotConfig] = None,
                 api_client: Any = None, backend: Optional[LlmBackend] = None) -> None:
        self.client = client
        self.cfg = config or PilotConfig()
        self.tools = GameTools(client, responder)
        if backend is None:   # 하위 호환: 백엔드를 안 주면 Claude API (api_client = 가짜 주입 가능)
            from play_agent.llm.anthropic_backend import AnthropicBackend
            backend = AnthropicBackend(model=self.cfg.model, effort=self.cfg.effort, max_tokens=self.cfg.max_tokens,
                                       api_client=api_client)
        self.backend = backend

    def run(self, first_observation: Mapping[str, Any]) -> PilotRun:
        cfg, llm = self.cfg, self.backend
        desc = self.client.description
        intro = {
            "goal": cfg.goal,
            "game": "%s %s" % (desc.get("game"), desc.get("game_version")),
            "quests_in_game": desc.get("quests"),
            "observation": compact_observation(first_observation),
        }
        llm.start(SYSTEM_PROMPT, build_tools(desc), to_text(intro))
        run = PilotRun(llm=llm.label)
        t0 = time.time()
        last_sig, stale = progress_signature(first_observation), 0
        run.last_observation = dict(first_observation)

        while True:
            if run.api_calls >= cfg.max_calls:
                run.end_reason = "max_calls"
                break
            turn = llm.complete()
            run.api_calls += 1
            if turn.texts:
                text = "\n".join(turn.texts)
                run.transcript.append({"assistant": text})
                self.client.note(text)   # v0.3 게임이면 화면에 표시, 아니면 클라이언트 기록만

            if turn.stop == STOP_PAUSE:
                continue
            if turn.stop in (STOP_REFUSAL, STOP_MAX_TOKENS) and not turn.calls:
                run.end_reason = "stop_" + turn.stop
                break
            if not turn.calls:
                # 도구 호출은 보장되지 않는다 → 한 번 상기시키고 계속
                llm.add_user("도구로 다음 행동을 하거나 finish 를 불러라.")
                run.transcript.append({"nudge": True})
                continue

            results: List[ToolResult] = []
            for call in turn.calls:
                if call.error:   # 인자 파싱 실패 → 실행하지 않고 알려 준다
                    out, is_err = {"error": call.error}, True
                else:
                    try:
                        out = self.tools.execute(call.name, call.input)
                        is_err = "error" in out
                    except Exception as e:   # PlayError(전투 중 error·연결 끊김) → 세션 종료
                        run.end_reason = "game_error: %s" % e
                        out, is_err = {"error": str(e)}, True
                run.transcript.append({"tool": call.name, "input": call.input,
                                       "status": out.get("status"), "reason": out.get("reason"),
                                       "error": out.get("error"), "combats": out.get("combats")})
                results.append(ToolResult(call.id, to_text(out), is_err))
                if run.end_reason:
                    break
            llm.add_tool_results(results)

            run.actions = self.tools.actions
            if self.tools.last_observation:
                run.last_observation = self.tools.last_observation
            if run.end_reason:
                break
            if self.tools.finished is not None:
                run.finish = self.tools.finished
                run.end_reason = "finish"
                break
            if run.actions >= cfg.max_actions:
                run.end_reason = "max_actions"
                break
            sig = progress_signature(run.last_observation)
            if sig != last_sig:
                last_sig, stale = sig, 0
            else:
                stale += sum(1 for c in turn.calls if c.name not in ("finish", "inspect_ui"))
                if stale >= cfg.no_progress_actions:
                    run.end_reason = "no_progress"
                    break

        run.usage = dict(llm.usage)
        run.combats = [c.summary() for c in self.tools.combats]
        run.seconds = round(time.time() - t0, 1)
        return run
