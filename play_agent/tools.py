"""게임 행동 ↔ LLM 도구 정의 계층 (API 루프 LlmPilot 과 이후 MCP 래퍼가 공유).

- build_tools(description) : play_description.actions 중 **게임이 지원한다고 한 것만** 도구로 만든다 (+ 메타 도구)
- GameTools.execute(name, input) : 도구 호출 → PlayClient → LLM 에게 줄 결과(dict)
- compact_observation(obs) : LLM 에게 보일 관찰 (seq 제거·숫자 반올림, 키 순서 고정 → 캐시 안정)

도구 스키마는 strict 용: 모든 속성 required + additionalProperties false, 선택 인자는 null 허용.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Mapping, Optional

from play_agent.client import ActResult, Combat, PlayClient, PlayError

NULLABLE_STR = {"anyOf": [{"type": "string"}, {"type": "null"}]}
NULLABLE_NUM = {"anyOf": [{"type": "number"}, {"type": "null"}]}
POS = {"anyOf": [{"type": "array", "items": {"type": "number"}}, {"type": "null"}]}

#: 알려진 행동의 스키마·설명. 게임이 새 행동을 선언하면 _generic_schema 로 만든다.
KNOWN_ACTIONS: Dict[str, Dict[str, Any]] = {
    "move_to": {
        "description": "엔티티(target) 또는 좌표(pos=[x,y,z]) 로 걸어간다. 둘 중 하나만 준다. 대상의 상호작용 거리 안에 들어가면 끝난다. "
                       "시야 밖 대상은 not_visible — 근처 좌표로 먼저 간다. 이동 중 적의 어그로 범위에 들어가면 전투가 자동으로 시작되고 "
                       "학습된 BT 가 싸운다 (결과는 combats 에 온다).",
        "properties": {"target": NULLABLE_STR, "pos": POS},
    },
    "interact": {
        "description": "엔티티와 상호작용 (verb: 엔티티 actions 에 있는 것). 범위 밖이면 out_of_range — 먼저 move_to.",
        "properties": {"target": {"type": "string"}, "verb": {"type": "string"}},
    },
    "ui_click": {
        "description": "화면 UI 요소를 클릭 (screen.ui 의 id). interactable:false 인 요소는 가려졌거나 비활성이라 실패한다.",
        "properties": {"ui_id": {"type": "string"}},
    },
    "use_item": {
        "description": "인벤토리 아이템 사용 (inventory 의 id).",
        "properties": {"item_id": {"type": "string"}},
    },
    "engage": {
        "description": "적에게 다가가 일부러 전투를 시작한다. 전투는 학습된 BT 가 하고, 끝나면 결과가 combats 에 온다.",
        "properties": {"target": {"type": "string"}},
    },
    "wait": {
        "description": "세계 시간을 보낸다: seconds 초, 또는 until 사건(dialog_closed / combat_ended / quest_update) 중 먼저.",
        "properties": {"seconds": NULLABLE_NUM, "until": NULLABLE_STR},
    },
}

META_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "inspect_ui",
        "description": "UI 계층 트리를 본다 (디버그용, 평소엔 필요 없음). root = UI id (예: ui.inventory) 또는 null(전체).",
        "input_schema": {"type": "object", "properties": {"root": NULLABLE_STR}, "required": ["root"], "additionalProperties": False},
    },
    {
        "name": "finish",
        "description": "플레이를 끝낸다. 목표를 다 이뤘거나, 더 진행할 방법이 없다고 판단했을 때. "
                       "blocked 에 막힌 이유(게임 버그로 보이는 것 포함)를 적는다.",
        "input_schema": {
            "type": "object",
            "properties": {"success": {"type": "boolean"}, "summary": {"type": "string"}, "blocked": NULLABLE_STR},
            "required": ["success", "summary", "blocked"], "additionalProperties": False,
        },
    },
]


def _generic_schema(args: Mapping[str, Any]) -> Dict[str, Any]:
    return {k: NULLABLE_STR for k in args}


def build_tools(description: Mapping[str, Any], strict: bool = True) -> List[Dict[str, Any]]:
    """play_description.actions → Claude 도구 목록 (게임이 준 순서 그대로, 메타 도구는 뒤)."""
    tools = []
    for a in description.get("actions") or []:
        name = str(a["name"])
        known = KNOWN_ACTIONS.get(name)
        props = dict(known["properties"]) if known else _generic_schema(a.get("args") or {})
        desc = known["description"] if known else "게임 행동 %s (인자 %s)" % (name, json.dumps(a.get("args"), ensure_ascii=False))
        verbs = (a.get("args") or {}).get("verb")
        if name == "interact" and isinstance(verbs, str):
            props["verb"] = {"type": "string", "enum": [v.strip() for v in verbs.split("|") if v.strip()]}
        tools.append({
            "name": name,
            "description": desc,
            "input_schema": {"type": "object", "properties": props, "required": list(props), "additionalProperties": False},
        })
    tools += [dict(t) for t in META_TOOLS]
    if strict:
        tools = [dict(t, strict=True) for t in tools]
    return tools


def _round(x: Any) -> Any:
    if isinstance(x, float):
        return round(x, 2)
    if isinstance(x, list):
        return [_round(v) for v in x]
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    return x


def compact_observation(obs: Mapping[str, Any]) -> Dict[str, Any]:
    o = {k: v for k, v in obs.items() if k not in ("type", "seq")}
    return _round(o)


class GameTools:
    """도구 호출 실행기. responder = 전투 트리거 응답기 (CombatResponder)."""

    def __init__(self, client: PlayClient, responder: Optional[Callable[..., Any]] = None) -> None:
        self.client = client
        self.responder = responder
        self.finished: Optional[Dict[str, Any]] = None
        self.combats: List[Combat] = []
        self.last_observation: Dict[str, Any] = {}
        self.actions = 0

    def execute(self, name: str, tool_input: Mapping[str, Any]) -> Dict[str, Any]:
        if name == "finish":
            self.finished = dict(tool_input)
            return {"ok": True}
        if name == "inspect_ui":
            root = tool_input.get("root")
            kw = {"root": root} if root else {}
            return _round(self.client.observe("hierarchy", max_depth=4, **kw))
        args = {k: v for k, v in tool_input.items() if v is not None}
        self.actions += 1
        r: ActResult = self.client.act(name, args, responder=self.responder)
        self.combats += r.combats
        if r.is_error:   # 인자·행동 이름 오류 (action_result 아님)
            return {"error": r.get("code"), "message": r.get("message")}
        self.last_observation = r.observation
        out: Dict[str, Any] = {"status": r.status}
        for k in ("reason", "reason_detail", "interrupted_by", "game_seconds"):
            if r.get(k) is not None:
                out[k] = _round(r.get(k))
        if r.combats:
            out["combats"] = [c.summary() for c in r.combats]
        out["observation"] = compact_observation(r.observation)
        return out


def to_text(result: Mapping[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


__all__ = ["build_tools", "GameTools", "compact_observation", "to_text", "PlayError"]
