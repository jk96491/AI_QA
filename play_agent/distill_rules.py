"""QaArena 규칙 교사 — DAgger 에서 기계적으로 판단되는 장면은 규칙이 교정 라벨을 단다 (사용자 결정 2026-11-26: A, 범용 모델 아님).

SDK `btqa_play auto --rules play_agent.distill_rules:correct` 가 단계마다 부른다:
    correct(step_input_text, proposal) -> None | {"tool", "input", "thought", "rule"}
    None = 규칙상 문제 없음 (승인), dict = 이 정답으로 교정 (학생 제안이 규칙 위반), {"defer": 이유} = 규칙으로 못 정함 → 교사가 본다.
**입력(step_input)만 본다** — 학생이 볼 수 없는 정보로 교정하지 않는다 (grounding).

규칙 (r8 0.8.5 기준 평가 2026-11-27 에서 막힌 장면):
  R0 목표 우선: 지금 목표 대상이 손 닿는 곳(2.5)에 있는데 다른 대상으로 interact/move_to → 그 목표 대상과 상호작용  (seed 12)
  R1 사거리: interact 대상이 보이는데 상호작용 거리(2.5) 밖 → move_to 대상            (seed 5: 촌장 7.8 m 에 talk 반복)
  R2 창 반복: 상점 아닌 창에서 직전과 같은 버튼을 또 누름 → 그 창의 닫기                (seed 1: 인벤토리 '퀵슬롯 등록' 반복)
  R3 이른 포기: 진행 중 퀘스트가 있는데 finish → 보이는 목표 대상에게 (적이면 engage)      (robust: 늑대왕이 보이자 finish)
      단, 직전 전투에서 졌고 물약이 없으면 포기(finish)도 맞다 — 규칙이 막지 않는다
      보이는 대상이 없으면: 목표 글에 들어 있는 HUD 버튼(예 '인벤토리') → 그 버튼, 아니면 defer (seed 11: 물약 등록 중 finish)
  R5 빈 이동: move_to 의 target·pos 가 모두 null → 보이는 목표 대상, 없으면 defer (seed 11: bad_request)
  R6 없는 버튼: 화면 ui 에 없는 ui_id 클릭 → 목표 글의 HUD 버튼, 아니면 defer (seed 14)
  R7 창 막힘: 창이 열렸는데 move_to/interact → 목표 글과 같은 글의 창 버튼, 없으면 닫기 (seed 14: 상점에서 이동)
  R4 같은 실패 반복: 직전 행동이 failed 인데 같은 행동 → R1 로 풀리면 그것, 아니면 교사에게 (None + 표시 없음 → relay 경고가 잡는다)
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

REACH = 2.5            # play_description.limits.interact_range (QaArena)
REPEAT_OK_MODALS = ("shop",)   # 상점은 같은 '구매'를 여러 번 누르는 게 정상 (물약 2개)


def _same(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    def norm(x):
        return json.dumps([x.get("tool"), {k: v for k, v in (x.get("input") or {}).items() if v is not None}], sort_keys=True)
    return norm(a) == norm(b)


def _targets(o: Mapping[str, Any]) -> List[str]:
    """첫 진행 중 퀘스트의 첫 미완료 목표 대상 (ready 면 반납 대상)."""
    for q in o.get("quests") or []:
        objs = [x for x in q.get("objectives") or [] if not x.get("done")]
        if q.get("state") == "ready":
            return [t for x in objs for t in x.get("hint_targets") or []]
        if objs:
            return list(objs[0].get("hint_targets") or [])
    return []


def correct(user_text: str, proposal: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    d = json.loads(user_text)
    o = d.get("observation") or {}
    la = d.get("last_action") or {}
    ents = {e.get("id"): e for e in o.get("entities") or []}
    screen = o.get("screen") or {}
    modal = screen.get("modal")
    tool, inp = proposal.get("tool"), dict(proposal.get("input") or {})

    # R0 목표 대상이 손 닿는 곳에 있는데 다른 곳으로 (seed 12: 약초 2/3, herb_03 2.3 m 옆에서 마을 입구로)
    tg = _targets(o)
    reach = [ents[t] for t in tg if t in ents and (ents[t].get("distance") or 99) <= REACH and ents[t].get("actions")]
    on_goal = inp.get("target") in tg
    btn_text = next((str(u.get("text") or "") for u in screen.get("ui") or [] if u.get("id") == inp.get("ui_id")), "")
    hud_detour = tool == "ui_click" and not modal and not (btn_text and btn_text in _objective_text(o))
    if reach and not on_goal and (tool in ("interact", "move_to") or hud_detour):   # seed 12: 상인 앞에서 인벤토리 열기
        e = reach[0]
        return {"tool": "interact", "input": {"target": e["id"], "verb": e["actions"][0]},
                "thought": "목표 대상 %s 이(가) 바로 옆이다 — %s" % (e.get("label") or e["id"], e["actions"][0]), "rule": "R0_goal_in_reach"}

    # R7 창이 열렸는데 이동·상호작용 (seed 14: 상점 창에서 move_to → blocked_by_modal)
    if modal and tool in ("move_to", "interact"):
        obj = _objective_text(o)
        btns = [u for u in screen.get("ui") or [] if u.get("role") == "button" and u.get("interactable") is not False
                and not str(u.get("id", "")).startswith("ui.hud.")]
        hit = [u for u in btns if u.get("text") and u["text"] in obj and not str(u["id"]).endswith(".close")]
        close = [u for u in btns if str(u.get("id", "")).endswith(".close")]
        pick = hit[0] if hit else close[0] if close else None
        if pick:
            return {"tool": "ui_click", "input": {"ui_id": pick["id"]},
                    "thought": "창 %s 이 열려 있다 — %s" % (modal, "목표 글의 '%s'" % pick["text"] if hit else "먼저 닫는다"),
                    "rule": "R7_modal_blocks_move"}
        return {"defer": "창 %s 이 열렸는데 이동 — 맞는 버튼 없음" % modal}

    # R6 화면에 없는 버튼 (seed 14: 대화가 끝났는데 ui.dialog.choice.0)
    if tool == "ui_click" and inp.get("ui_id") and inp["ui_id"] not in {u.get("id") for u in screen.get("ui") or []}:
        b = _objective_button(o, screen) if not modal else None
        if b:
            return {"tool": "ui_click", "input": {"ui_id": b["id"]},
                    "thought": "목표 글의 '%s' — 그 버튼을 연다" % b["text"], "rule": "R6_missing_button"}
        for t in _targets(o) if not modal else []:   # seed 16: 닫힌 인벤토리 '닫기' 반복 → 목표 대상에게
            if t in ents:
                e = ents[t]
                if (e.get("distance") or 99) <= REACH and e.get("actions"):
                    return {"tool": "interact", "input": {"target": t, "verb": e["actions"][0]},
                            "thought": "%s 이(가) 바로 옆이다 — %s" % (e.get("label") or t, e["actions"][0]), "rule": "R6_missing_button"}
                return {"tool": "move_to", "input": {"target": t, "pos": None},
                        "thought": "%s 이(가) 멂 %.1f — 다가간다" % (e.get("label") or t, e.get("distance") or 0), "rule": "R6_missing_button"}
        return {"defer": "화면에 없는 버튼 %s" % inp["ui_id"]}

    # R1 사거리
    if tool == "interact" and inp.get("target") in ents:
        e = ents[inp["target"]]
        if e.get("distance") is not None and e["distance"] > REACH:
            return {"tool": "move_to", "input": {"target": e["id"], "pos": None},
                    "thought": "%s 이(가) 멂 %.1f — 먼저 다가간다" % (e.get("label") or e["id"], e["distance"]), "rule": "R1_range"}

    # R2 창 안 같은 버튼 반복
    if tool == "ui_click" and modal and modal not in REPEAT_OK_MODALS and la.get("tool") == "ui_click" \
            and la.get("status") == "done" and _same(la, proposal):
        close = [u["id"] for u in screen.get("ui") or [] if u.get("role") == "button"
                 and str(u.get("id", "")).endswith(".close") and u.get("interactable") is not False]
        if close:
            return {"tool": "ui_click", "input": {"ui_id": close[0]},
                    "thought": "창 %s 에서 같은 버튼을 또 눌렀다 — 창을 닫는다" % modal, "rule": "R2_modal_repeat"}

    # R3 이른 포기
    if tool == "finish" and o.get("quests"):
        lost = any(c.get("cleared") is False for c in la.get("combats") or [])
        no_potion = not any("potion" in str(i.get("id") or i.get("item") or "") for i in o.get("inventory") or [])
        if lost and no_potion:
            return None
        for t in _targets(o):
            if t in ents:
                e = ents[t]
                if e.get("role") == "enemy":
                    return {"tool": "engage", "input": {"target": t},
                            "thought": "퀘스트가 남았다 — %s 이(가) 보인다, 싸우러 간다" % (e.get("label") or t), "rule": "R3_early_finish"}
                return {"tool": "move_to", "input": {"target": t, "pos": None},
                        "thought": "퀘스트가 남았다 — %s 에게 간다" % (e.get("label") or t), "rule": "R3_early_finish"}
        b = _objective_button(o, screen)
        if b:
            return {"tool": "ui_click", "input": {"ui_id": b["id"]},
                    "thought": "퀘스트가 남았다 — 목표 글의 '%s' 를 연다" % b["text"], "rule": "R3_early_finish"}
        return {"defer": "진행 중 퀘스트가 있는데 finish — 보이는 대상·버튼 없음"}

    # R5 빈 이동
    if tool == "move_to" and inp.get("target") in (None, "", "null", "None") and not inp.get("pos"):   # 궁수 11: "null" 문자열
        for t in _targets(o):
            if t in ents:
                return {"tool": "move_to", "input": {"target": t, "pos": None},
                        "thought": "%s 에게 간다" % (ents[t].get("label") or t), "rule": "R5_empty_move"}
        b = _objective_button(o, screen) if not modal else None
        if b:
            return {"tool": "ui_click", "input": {"ui_id": b["id"]},
                    "thought": "목표 글의 '%s' — 그 버튼을 연다" % b["text"], "rule": "R5_empty_move"}
        return {"defer": "move_to 인자가 비었고 보이는 목표 대상이 없음"}

    # R8 반복 감시 (history 형식만, 2026-11-27 r13: 약초↔포털 왕복·등록 버튼 20번) — 위 규칙이 못 잡은 반복을 이어 가면 교사에게
    seq = [x for x in list(d.get("recent_actions") or []) + [la] if x] if "recent_actions" in d else []
    if len(seq) >= 3 and not (modal in REPEAT_OK_MODALS):
        names = [(x.get("tool"), json.dumps(x.get("input") or {}, sort_keys=True)) for x in seq]
        me = (tool, json.dumps({k: v for k, v in inp.items() if v is not None}, sort_keys=True))
        if names[-1] == names[-2] == names[-3] == me:
            return {"defer": "같은 행동 4번째 — 진척 여부를 교사가 본다"}
        if len(names) >= 3 and names[-1] != names[-2] and names[-3] == names[-1] and me == names[-2]:
            return {"defer": "두 행동을 번갈아 반복 중 — 교사가 본다"}
    return None


def _objective_button(o: Mapping[str, Any], screen: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """목표 글에 들어 있는 HUD 버튼 (예 '인벤토리에서 … 등록' → ui.hud.inventory)."""
    obj = _objective_text(o)
    for u in screen.get("ui") or []:
        if u.get("role") == "button" and str(u.get("id", "")).startswith("ui.hud.") and u.get("text") and u["text"] in obj:
            return u
    return None


def _objective_text(o: Mapping[str, Any]) -> str:
    for q in o.get("quests") or []:
        objs = [x for x in q.get("objectives") or [] if not x.get("done")]
        if objs:
            return str(objs[0].get("text") or "")
    return ""


__all__ = ["correct", "REACH"]
