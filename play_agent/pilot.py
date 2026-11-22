"""LlmPilot — 비전투를 Claude 가 플레이하는 수동 tool use 루프 (PLAY_PROTOCOL 5장).

- 모델 claude-opus-5-5 (thinking 상시, 깊이는 output_config.effort), tool_choice auto + strict 도구
- 시스템 프롬프트·도구 목록은 세션 내내 고정 → 시스템 블록 캐시 지점 + 상위 cache_control(대화 꼬리 자동 캐시)
- 전투는 도구 실행(PlayClient.act) 안에서 학습된 BT·응답기가 끝내고, 요약만 도구 결과에 실린다
- 상한: 행동 수, API 호출 수, 진척 없음(N 행동 동안 퀘스트·지역·인벤토리·골드 변화 없음)
- 결과: PilotRun (끝난 이유, finish 요약, 전투, 토큰 사용량, 대화 기록) — 재현은 게임 get_log 의 행동열로

anthropic SDK(1.x, Python ≥ 3.10)는 run() 에서만 import 한다 → 나머지 play_agent 는 프로젝트 venv(3.8)에서도 돈다.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from play_agent.client import PlayClient
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
- 상호작용은 먼저 move_to 로 다가간 뒤 interact. 보이지 않는 대상은 근처 좌표나 지역 입구로 먼저 간다.
- 창(modal)이 열려 있으면 그 창의 버튼으로 진행하거나 닫는다. interactable:false 버튼은 가려졌거나 비활성이다 — 가린 창부터 처리한다.
- 전투는 네가 하지 않는다. 적에게 다가가거나 engage 하면 학습된 전투 AI 가 싸우고 결과가 combats 로 온다. 지면 체크포인트에서 부활하니 다시 시도할 수 있다.
- 목표를 다 이뤘거나, 같은 시도를 반복해도 진척이 없으면 finish 를 부른다. 게임 버그로 보이는 것은 blocked 에 구체적으로 적는다 (UI id·메시지 포함).
- 말은 짧게. 생각은 하되 출력 텍스트는 최소로."""


@dataclass
class PilotConfig:
    model: str = DEFAULT_MODEL
    effort: str = "low"               # low | medium | high … (Opus 5.5 기본 medium)
    max_tokens: int = 8000            # 응답 1회 (thinking 포함)
    max_actions: int = 150            # 게임 행동 수 상한
    max_calls: int = 250              # API 호출 상한
    no_progress_actions: int = 25     # 이만큼 행동하는 동안 진척 없으면 중단
    goal: str = "튜토리얼 퀘스트를 모두 끝까지 완료하라 (진행 중인 퀘스트가 없어질 때까지)."


@dataclass
class PilotRun:
    end_reason: str = ""
    finish: Optional[Dict[str, Any]] = None
    actions: int = 0
    api_calls: int = 0
    combats: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0
    last_observation: Dict[str, Any] = field(default_factory=dict)
    transcript: List[Dict[str, Any]] = field(default_factory=list)   # (assistant 텍스트·도구 호출·결과 요약)

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in ("end_reason", "finish", "actions", "api_calls", "combats", "usage",
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
                 api_client: Any = None) -> None:
        self.client = client
        self.cfg = config or PilotConfig()
        self.tools = GameTools(client, responder)
        self._api = api_client   # 테스트에서 가짜 주입 가능 (messages.create 만 쓴다)

    def _anthropic(self) -> Any:
        if self._api is None:
            import anthropic   # Python ≥ 3.10 전용 venv (PLAY_PROTOCOL 5장)
            self._api = anthropic.Anthropic()
        return self._api

    def run(self, first_observation: Mapping[str, Any]) -> PilotRun:
        cfg = self.cfg
        api = self._anthropic()
        desc = self.client.description
        tool_defs = build_tools(desc)
        system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
        intro = {
            "goal": cfg.goal,
            "game": "%s %s" % (desc.get("game"), desc.get("game_version")),
            "quests_in_game": desc.get("quests"),
            "observation": compact_observation(first_observation),
        }
        messages: List[Dict[str, Any]] = [{"role": "user", "content": to_text(intro)}]
        run = PilotRun(usage={"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})
        t0 = time.time()
        last_sig, stale = progress_signature(first_observation), 0
        run.last_observation = dict(first_observation)

        while True:
            if run.api_calls >= cfg.max_calls:
                run.end_reason = "max_calls"
                break
            resp = api.messages.create(
                model=cfg.model, max_tokens=cfg.max_tokens, system=system, tools=tool_defs, messages=messages,
                output_config={"effort": cfg.effort}, cache_control={"type": "ephemeral"},
            )
            run.api_calls += 1
            for k in run.usage:
                run.usage[k] += int(getattr(resp.usage, k, 0) or 0)
            messages.append({"role": "assistant", "content": resp.content})
            texts = [b.text for b in resp.content if getattr(b, "type", "") == "text" and b.text.strip()]
            calls = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
            if texts:
                run.transcript.append({"assistant": "\n".join(texts)})

            if resp.stop_reason == "pause_turn":
                continue
            if resp.stop_reason in ("refusal", "max_tokens") and not calls:
                run.end_reason = "stop_" + str(resp.stop_reason)
                break
            if not calls:
                # auto 는 호출을 보장하지 않는다 → 한 번 상기시키고 계속 (도구 강제는 Opus 5.5 에서 400)
                messages.append({"role": "user", "content": "도구로 다음 행동을 하거나 finish 를 불러라."})
                run.transcript.append({"nudge": True})
                continue

            results = []
            for call in calls:
                try:
                    out = self.tools.execute(call.name, call.input)
                    is_err = "error" in out
                except Exception as e:   # PlayError(전투 중 error·연결 끊김) → 세션 종료
                    run.end_reason = "game_error: %s" % e
                    out, is_err = {"error": str(e)}, True
                run.transcript.append({"tool": call.name, "input": call.input,
                                       "status": out.get("status"), "reason": out.get("reason"),
                                       "error": out.get("error"), "combats": out.get("combats")})
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": to_text(out), "is_error": is_err})
                if run.end_reason:
                    break
            messages.append({"role": "user", "content": results})

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
                stale += sum(1 for c in calls if c.name not in ("finish", "inspect_ui"))
                if stale >= cfg.no_progress_actions:
                    run.end_reason = "no_progress"
                    break

        run.combats = [c.summary() for c in self.tools.combats]
        run.seconds = round(time.time() - t0, 1)
        return run
