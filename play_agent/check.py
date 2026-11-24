"""check-play — 플레이 프로토콜 적합성 + 스크립트 튜토리얼 완주 (LLM 없음).

unity_game/QaTools~/play_check.py (Unity 쪽 자체 검증) 의 T2~T8·T-P·T-N 을 학습 쪽으로 옮기고 T9 를 더했다:
  T2 핸드셰이크 · T3 지각 필터+P1 행동 · T4 튜토리얼 q_tut_01~05 · T5 전투 동일성(--balance) · T6 전투 인계
  T7 결정성 · T8 새 게임 · T9 학습 결과 인계(--loadout: params.json/policy.json → set_loadout + 응답기, 밸런스 결과와 일치)
  T-P (v0.3) 전투 물약 = 퀵슬롯 물약 min(보유, cap), 사용분 차감 · T-N (v0.3) pilot_note
  T-D (0.3 선택 필드 4.2.1) 행동 설명·스키마가 게임 선언 또는 QaArena 스펙에 있는지 + 선언 규칙 (SDK validate_description)
T5·T9 의 밸런스 비교는 물약을 cap 개 가져간 조우(carried == cap)만 한다 — 밸런스 판은 항상 cap 개로 시작한다.

인스턴스는 직접 띄운 것(--game 등)을 쓰거나 --exe 로 헤드리스 인스턴스를 띄운다.
검사 항목의 세부 기대값(좌표·UI id·골드)은 QaArena 0.6.x 튜토리얼 데이터에 맞춘 것이다.
"""
from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from btqa_play.client import BOSS_MISMATCH_CODES, PlayClient, parse_endpoint
from btqa_play.spec import PlaySpec
from btqa_play.tools import tool_sources, validate_description
from play_agent import QA_ARENA_SPEC
from play_agent.loadout import LoadoutBuilder

EXPECTED_ACTIONS = ["move_to", "interact", "ui_click", "use_item", "engage", "wait"]
START_STATE = "barrier_inventory_potions"   # v0.3 (v0.2 이하 "full")


class Checker:
    def __init__(self) -> None:
        self.results: List[Tuple[str, bool, str]] = []

    def check(self, name: str, ok: Any, detail: str = "") -> bool:
        ok = bool(ok)
        self.results.append((name, ok, detail))
        print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, (" — " + detail) if detail else ""), flush=True)
        return ok

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(ok for _, ok, _ in self.results)


class Conn:
    """검사용 얇은 래퍼: 원문 메시지(dict)를 그대로 다룬다. 전송·수신은 PlayClient."""

    def __init__(self, ep: str) -> None:
        self.pc = PlayClient.connect(ep, timeout=120, client_name="check_play")
        self.seq = 0

    def rq(self, m: Dict[str, Any]) -> Dict[str, Any]:
        return self.pc.request(m)

    def send(self, m: Dict[str, Any]) -> None:
        self.pc.send(m)

    def recv(self) -> Dict[str, Any]:
        return self.pc.recv()

    def hello(self) -> Dict[str, Any]:
        return self.pc.hello()

    def act(self, action: str, responder: Optional[Callable] = None, log: Optional[list] = None, **args: Any) -> Dict[str, Any]:
        self.seq += 1
        self.send({"type": "act", "seq": self.seq, "action": action, "args": args})
        while True:
            m = self.recv()
            if log is not None:
                log.append(m)
            if m.get("type") == "combat_started":
                hook = getattr(responder, "on_combat_started", None)
                if hook is not None:
                    hook(m)
                continue
            if m.get("type") == "trigger":
                params = responder(m) if responder else None
                self.send({"type": "trigger_response", "encounter_id": m["encounter_id"], "index": m["index"], "params": params})
                continue
            if m.get("type") == "combat_ended":
                continue
            return m

    def close(self) -> None:
        self.pc.close()


def ids(obs, key="entities"):
    return [e["id"] for e in obs.get(key, [])]


def ui(obs, uid):
    return next((e for e in obs.get("screen", {}).get("ui", []) if e["id"] == uid), None)


def ent(obs, eid):
    return next((e for e in obs.get("entities", []) if e["id"] == eid), None)


def quest(obs, qid):
    return next((q for q in obs.get("quests", []) if q["id"] == qid), None)


def kinds(obs):
    return [e[1] for e in obs.get("events", [])]


def goto(c, target, near=None):
    """대상이 안 보이면 근처 좌표로 먼저 간 뒤 대상으로."""
    r = c.act("move_to", target=target)
    if r.get("reason") == "not_visible" and near is not None:
        c.act("move_to", pos=near)
        r = c.act("move_to", target=target)
    return r


def click(c, uid):
    return c.act("ui_click", ui_id=uid)


def note(c, kind, text):
    """pilot_note 원문 요청 (seq 를 쓰지 않는다 — act seq 가 같아야 재생 비교가 된다)."""
    return c.rq({"type": "pilot_note", "kind": kind, "text": text})


def no_notes(entries):
    return [e for e in entries if e[1] != "pilot_note"]


def prep_potions(c):
    """튜토리얼 q_tut_01~04 를 빠르게: 작은 물약 4개 + 퀵슬롯 0 등록 (전투에 cap=3 개를 가져가게). 마지막 관찰 반환."""
    goto(c, "npc_elder")
    c.act("interact", target="npc_elder", verb="talk")
    click(c, "ui.dialog.choice.0")
    click(c, "ui.dialog.choice.0")
    c.act("move_to", target="portal_forest")
    c.act("interact", target="portal_forest", verb="enter")
    for h, near in {"herb_01": [-4, 0, -28], "herb_02": [4, 0, -23], "herb_03": [-6, 0, -15]}.items():
        goto(c, h, near)
        c.act("interact", target=h, verb="pickup")
    c.act("move_to", target="portal_village")
    c.act("interact", target="portal_village", verb="enter")
    goto(c, "npc_elder")
    c.act("interact", target="npc_elder", verb="talk")
    click(c, "ui.dialog.choice.0")
    click(c, "ui.dialog.choice.0")
    click(c, "ui.hud.inventory")
    click(c, "ui.tip.ok")
    click(c, "ui.inventory.slot.potion_small")
    click(c, "ui.inventory.assign")
    click(c, "ui.inventory.close")
    goto(c, "npc_merchant", near=[-2, 0, -8])
    c.act("interact", target="npc_merchant", verb="talk")
    click(c, "ui.dialog.choice.0")
    click(c, "ui.shop.buy.potion_small")
    click(c, "ui.shop.buy.potion_small")
    return click(c, "ui.shop.close")["observation"]


def scripted_responder(m):
    """결정적 트리거 응답 (밸런스 서버에도 같은 값을 보낸다)."""
    return {"w_survival": round(0.3 + 0.15 * m["index"], 3)}


def balance_run(ep, cls, scenario, seed, params, triggers, replies):
    """밸런스 서버(v1.2)에서 같은 판을 돌린다. replies = 플레이 쪽이 보낸 trigger 응답 params (순서대로)."""
    h, p = parse_endpoint(ep)
    s = socket.create_connection((h, p), timeout=120)
    f = s.makefile("rwb")

    def tx(m):
        f.write((json.dumps(m, ensure_ascii=False) + "\n").encode("utf-8"))
        f.flush()

    def rx():
        return json.loads(f.readline().decode("utf-8"))

    tx({"type": "hello", "protocol_version": "1.2", "client": "check_play"})
    rx()
    msg = {"type": "run_episode", "episode_id": "t5", "class": cls, "scenario": scenario, "seed": seed, "params": params or {}}
    if triggers:
        msg["triggers"] = triggers
    tx(msg)
    k = 0
    try:
        while True:
            m = rx()
            if m["type"] == "trigger":
                tx({"type": "trigger_response", "episode_id": "t5", "index": m["index"], "params": replies[k] if k < len(replies) else None})
                k += 1
                continue
            return m.get("result"), k
    finally:
        try:
            tx({"type": "bye"})
        except OSError:
            pass
        s.close()


# ====================================================================== T2
def t2(ck: Checker, ep: str) -> None:
    print("== T2 핸드셰이크")
    c = Conn(ep)
    r = c.rq({"type": "hello", "protocol_version": "1.2", "client": "balance_qa"})
    ck.check("밸런스 클라이언트 hello → protocol_version", r.get("type") == "error" and r.get("code") == "protocol_version", r.get("message", ""))
    r = c.rq({"type": "hello", "protocol": "play", "protocol_version": "9.0"})
    ck.check("다른 버전 → protocol_version", r.get("code") == "protocol_version")
    r = c.hello()
    ck.check("hello play → hello_ok (오류 후 연결 유지)", r.get("type") == "hello_ok" and r.get("protocol") == "play",
             "game %s, protocol %s%s" % (r.get("game_version"), c.pc.protocol_version, (" — " + "; ".join(c.pc.notes)) if c.pc.notes else ""))
    r = c.act("move_to", target="npc_elder")
    ck.check("reset 전 act → not_reset", r.get("code") == "not_reset")
    r = c.rq({"type": "observe"})
    ck.check("reset 전 observe → not_reset", r.get("code") == "not_reset")
    d = c.rq({"type": "play_describe"})
    ck.check("play_describe actions = 실제 지원 목록 (ui_input 없음)",
             d.get("type") == "play_description" and [a["name"] for a in d["actions"]] == EXPECTED_ACTIONS,
             "classes=%s scenarios=%s" % (d.get("classes"), [s["name"] for s in d.get("scenarios", [])]))
    sc = {s["name"]: s.get("boss") for s in d.get("scenarios", [])}
    ck.check("scenarios = {name, boss}, forest_wolf_king → forest_wolf_king", sc.get("forest_wolf_king") == "forest_wolf_king" and sc.get("base") == "default")
    enc = (d.get("combat") or {}).get("encounters") or []
    ck.check("combat.encounters 에 wolf_king → forest_wolf_king", any(e.get("enemy") == "wolf_king" and e.get("scenario") == "forest_wolf_king" for e in enc), str(enc))
    ck.check("T-N1 hello play 0.3 + describe.pilot_notes", c.pc.protocol_version == "0.3" and bool(d.get("pilot_notes")),
             "protocol %s, pilot_notes %s" % (c.pc.protocol_version, d.get("pilot_notes")))
    ck.check("T-P describe.combat.encounter_start_state = %s" % START_STATE, (d.get("combat") or {}).get("encounter_start_state") == START_STATE,
             str((d.get("combat") or {}).get("encounter_start_state")))
    spec = PlaySpec.load(QA_ARENA_SPEC)
    problems = validate_description(d, spec) if d.get("type") == "play_description" else ["play_describe 실패"]
    src = tool_sources(d, spec) if not problems else {}
    ck.check("T-D 행동 설명·스키마가 게임 선언 또는 QaArena 스펙에 모두 있음 + 선언 규칙 (4.2.1)", not problems,
             "; ".join(problems) if problems else "출처 %s, pilot_guide %s" % (
                 ",".join("%s=%s" % kv for kv in src.items()), "있음" if d.get("pilot_guide") else "없음"))
    r = c.rq({"type": "reset", "seed": 1, "start": "checkpoint"})
    ck.check("reset 에 시작 지점 옵션 → bad_request (항상 새 게임)", r.get("code") == "bad_request")
    r = c.rq({"type": "reset", "seed": 1, "class": "paladin"})
    ck.check("reset 모르는 class → unknown_class", r.get("code") == "unknown_class")
    r = c.rq({"type": "nope"})
    ck.check("모르는 type → unknown_type", r.get("code") == "unknown_type")
    c.pc.send_raw(b"{not json\n")
    r = c.recv()
    ck.check("JSON 오류 → bad_request", r.get("code") == "bad_request")
    c.close()
    c = Conn(ep)
    r = c.rq({"type": "observe"})
    ck.check("새 연결 → 다시 not_reset", r.get("code") == "not_reset")
    c.close()


# ====================================================================== T3
def t3(ck: Checker, ep: str, omni: Optional[str]) -> None:
    print("== T3 지각 필터 + P1 행동")
    c = Conn(ep)
    c.hello()
    o = c.rq({"type": "reset", "seed": 1, "class": "warrior"})
    ck.check("reset → observation", o.get("type") == "observation" and o["player"]["zone"] == "village", "entities=%s" % ids(o))
    ck.check("시야 밖 NPC(npc_guard) 없음", "npc_guard" not in ids(o))
    ck.check("시야 안 NPC(npc_elder) 있음", "npc_elder" in ids(o))
    ck.check("alwaysKnown(portal_forest) 시야 밖이어도 있음", "portal_forest" in ids(o))
    ck.check("hidden_included=false", o.get("hidden_included") is False)
    ck.check("new_game 사건", "new_game" in kinds(o))
    ck.check("player.quickslots 길이 2", len(o["player"].get("quickslots") or []) == 2, str(o["player"].get("quickslots")))

    r = c.act("move_to", target="npc_guard")
    ck.check("시야 밖 대상 move_to → not_visible", r.get("status") == "failed" and r.get("reason") == "not_visible", str(r.get("reason")))
    r = c.act("interact", target="npc_elder", verb="talk")
    ck.check("범위 밖 interact → out_of_range (자동 접근 안 함)", r.get("reason") == "out_of_range", str(r.get("reason_detail")))
    ck.check("reason_detail 형식 'distance N'", str(r.get("reason_detail", "")).startswith("distance "), str(r.get("reason_detail")))
    r = c.act("move_to", pos=[-15, 0, 10])
    ck.check("울타리 안 위치 move_to → unreachable", r.get("status") == "failed" and r.get("reason") == "unreachable", str(r.get("reason")))
    r = c.act("fly", target="npc_elder")
    ck.check("모르는 행동 → error(unknown_action)", r.get("code") == "unknown_action")
    r = c.act("ui_input", ui_id="ui.hud.gold", text="x")
    ck.check("ui_input(미지원) → error(unknown_action)", r.get("code") == "unknown_action")
    r = c.act("move_to")
    ck.check("인자 없음 → error(bad_request)", r.get("code") == "bad_request")

    r = c.act("move_to", target="npc_elder")
    o = r.get("observation", {})
    el = ent(o, "npc_elder")
    ck.check("move_to npc_elder → done", r.get("status") == "done" and el is not None and el["distance"] <= 2.5,
             "game_seconds=%s distance=%s" % (r.get("game_seconds"), el and el["distance"]))
    hud = ui(o, "ui.hud.quests")
    ck.check("모달 없을 때 ui.hud.quests interactable:true", hud is not None and hud["interactable"] is True)

    r = c.act("interact", target="npc_elder", verb="talk")
    o = r["observation"]
    ck.check("interact talk → 대화창", r.get("status") == "done" and o["screen"]["modal"] == "dialog",
             "text=%s" % (ui(o, "ui.dialog.text") or {}).get("text"))
    choices = [e["text"] for e in o["screen"]["ui"] if e["id"].startswith("ui.dialog.choice.")]
    ck.check("선택지 2개 보임", choices == ["맡겨 주세요", "나중에"], str(choices))
    hud = ui(o, "ui.hud.quests")
    ck.check("대화창에 가린 ui.hud.quests interactable:false", hud is not None and hud["interactable"] is False)
    r = c.act("ui_click", ui_id="ui.hud.quests")
    ck.check("가린 버튼 ui_click → failed(not_interactable) + 'blocked by ui.dialog…'",
             r.get("status") == "failed" and r.get("reason") == "not_interactable" and str(r.get("reason_detail", "")).startswith("blocked by ui.dialog"),
             str(r.get("reason_detail")))
    r = c.act("move_to", target="npc_guard")
    ck.check("대화 중 move_to → blocked_by_modal", r.get("reason") == "blocked_by_modal")

    r = c.act("ui_click", ui_id="ui.dialog.choice.0")
    o = r["observation"]
    ck.check("선택지 0 → 다음 노드", r.get("status") == "done" and o["screen"]["modal"] == "dialog" and
             [e["text"] for e in o["screen"]["ui"] if e["id"].startswith("ui.dialog.choice.")] == ["다녀오겠습니다"])
    r = c.act("ui_click", ui_id="ui.dialog.choice.1")
    ck.check("사라진 선택지 1 → unknown_target", r.get("reason") == "unknown_target")
    r = c.act("ui_click", ui_id="ui.dialog.choice.0")
    o = r["observation"]
    ck.check("대화 종료", o["screen"]["modal"] is None and "dialog_closed" in kinds(o), str(kinds(o)))
    r = c.act("ui_click", ui_id="ui.hud.quests")
    o = r["observation"]
    ck.check("모달 닫힌 뒤 ui.hud.quests 클릭 → 퀘스트 창", r.get("status") == "done" and o["screen"]["modal"] == "quests")
    h = c.rq({"type": "observe", "mode": "hierarchy", "root": "ui.quests", "max_depth": 3})
    ck.check("hierarchy 관찰", h.get("type") == "observation" and h["tree"]["id"] == "ui.quests" and len(h["tree"]["children"]) > 0,
             "children=%s" % [ch["id"] for ch in h.get("tree", {}).get("children", [])])
    r = c.act("ui_click", ui_id="ui.quests.close")
    ck.check("퀘스트 창 닫기", r["observation"]["screen"]["modal"] is None)

    r = c.act("move_to", pos=[34, 0, -30])
    o = r["observation"]
    ck.check("이동 후 npc_guard 시야에 들어옴", r.get("status") == "done" and "npc_guard" in ids(o), "entities=%s" % ids(o))
    r = c.act("wait", seconds=1.5)
    ck.check("wait 1.5초", r.get("status") == "done" and abs(r.get("game_seconds", 0) - 1.5) < 1e-6, str(r.get("game_seconds")))
    lg = c.rq({"type": "get_log"})
    ck.check("get_log (entries, next_seq)", lg.get("type") == "play_log" and len(lg["entries"]) > 10, "entries=%d" % len(lg.get("entries", [])))
    c.close()

    if omni:
        c = Conn(omni)
        c.hello()
        d = c.rq({"type": "play_describe"})
        o = c.rq({"type": "reset", "seed": 1, "class": "warrior"})
        g = ent(o, "npc_guard")
        ck.check("omniscient: 시야 밖 npc_guard 가 hidden:true 로 있음", d["debug"]["omniscient"] is True and g is not None and g.get("hidden") is True,
                 "hidden_included=%s" % o.get("hidden_included"))
        dlg = [e for e in o["screen"]["ui"] if e["id"].startswith("ui.dialog")]
        ck.check("omniscient: 닫힌 대화창 요소도 hidden:true 로 있음", len(dlg) > 0 and all(e.get("hidden") for e in dlg), "%d개" % len(dlg))
        c.close()


# ====================================================================== T4
def t4(ck: Checker, ep: str) -> None:
    print("== T4 튜토리얼 q_tut_01~05 (고정 행동열)")
    c = Conn(ep)
    c.hello()
    o = c.rq({"type": "reset", "seed": 3, "class": "warrior"})
    q1 = quest(o, "q_tut_01")
    ck.check("시작: q_tut_01 진행 중, 촌장 마커 objective", q1 is not None and q1["state"] == "active" and ent(o, "npc_elder")["marker"] == "objective")

    goto(c, "npc_elder")
    r = c.act("interact", target="npc_elder", verb="talk")
    o = r["observation"]
    ck.check("촌장 대화 → q_tut_01 완료", "quest_completed" in kinds(o) and quest(o, "q_tut_01") is None)
    o = click(c, "ui.dialog.choice.1")["observation"]   # 나중에
    ck.check("함정: '나중에' → q_tut_02 수락 안 됨, 마커 quest_available",
             quest(o, "q_tut_02") is None and "quest_accepted" not in kinds(o) and ent(o, "npc_elder").get("marker") == "quest_available")
    c.act("interact", target="npc_elder", verb="talk")
    o = click(c, "ui.dialog.choice.0")["observation"]   # 맡겨 주세요
    q2 = quest(o, "q_tut_02")
    ck.check("'맡겨 주세요' → q_tut_02 수락, 진행도 [0,3]", q2 is not None and q2["objectives"][0]["progress"] == [0, 3])
    click(c, "ui.dialog.choice.0")

    r = c.act("move_to", pos=[-15, 0, 10])
    ck.check("울타리 안 상자 위치 → unreachable", r.get("reason") == "unreachable")

    r = goto(c, "npc_merchant", near=[-2, 0, -8])
    ck.check("상인에게 이동", r.get("status") == "done", str(r.get("reason")))
    c.act("interact", target="npc_merchant", verb="talk")
    o = click(c, "ui.dialog.choice.0")["observation"]
    big = ui(o, "ui.shop.buy.potion_large")
    ck.check("상점 열림, 큰 물약(80G) 구매 버튼 비활성", o["screen"]["modal"] == "shop" and big is not None and big["interactable"] is False)
    o = click(c, "ui.shop.buy.potion_small")["observation"]
    msg = (ui(o, "ui.shop.message") or {}).get("text", "")
    ck.check("골드 부족 구매 → 실패 메시지가 관찰에 보임", "골드가 부족" in msg and "purchase_failed" in kinds(o) and o["player"]["gold"] == 20, msg)
    r = click(c, "ui.shop.buy.potion_large")
    ck.check("비활성 버튼 클릭 → failed(not_interactable, disabled)", r.get("reason") == "not_interactable" and r.get("reason_detail") == "disabled")
    click(c, "ui.shop.close")

    r = c.act("move_to", target="portal_forest")
    ck.check("숲 입구(alwaysKnown)로 이동", r.get("status") == "done", str(r.get("reason")))
    o = c.act("interact", target="portal_forest", verb="enter")["observation"]
    ck.check("숲 진입", o["player"]["zone"] == "forest" and "zone_entered" in kinds(o))
    herbs = {"herb_01": [-4, 0, -28], "herb_02": [4, 0, -23], "herb_03": [-6, 0, -15]}
    for h, near in herbs.items():
        goto(c, h, near)
        r = c.act("interact", target=h, verb="pickup")
        ck.check("약초 줍기 " + h, r.get("status") == "done", str(r.get("reason")))
    o = r["observation"]
    q2 = quest(o, "q_tut_02")
    ck.check("q_tut_02 진행도 [3,3] → ready", q2 is not None and q2["objectives"][0]["progress"] == [3, 3] and q2["state"] == "ready")
    c.act("move_to", target="portal_village")
    r = c.act("interact", target="portal_village", verb="enter")
    ck.check("마을 복귀", r["observation"]["player"]["zone"] == "village")

    r = goto(c, "npc_elder")
    ck.check("촌장 마커 quest_turn_in", ent(r["observation"], "npc_elder").get("marker") == "quest_turn_in")
    c.act("interact", target="npc_elder", verb="talk")
    o = click(c, "ui.dialog.choice.0")["observation"]
    inv = {i["id"]: i["count"] for i in o["inventory"]}
    ck.check("q_tut_02 완료: 약초 회수, 골드 50, 작은 물약 2", "quest_completed" in kinds(o) and o["player"]["gold"] == 50 and inv == {"potion_small": 2}, str(inv))
    click(c, "ui.dialog.choice.0")

    o = click(c, "ui.hud.inventory")["observation"]
    asg = ui(o, "ui.inventory.assign")
    ck.check("인벤토리 첫 열기 → 안내 팝업(modal tip)이 위에 뜸", o["screen"]["modal"] == "tip" and asg is not None and asg["interactable"] is False)
    r = click(c, "ui.inventory.slot.potion_small")
    ck.check("팝업에 가린 슬롯 클릭 → not_interactable, blocked by ui.tip",
             r.get("reason") == "not_interactable" and "ui.tip" in str(r.get("reason_detail")), str(r.get("reason_detail")))
    o = click(c, "ui.tip.ok")["observation"]
    ck.check("팝업 닫기 → 인벤토리, 선택 전 등록 버튼 비활성", o["screen"]["modal"] == "inventory" and ui(o, "ui.inventory.assign")["interactable"] is False)
    click(c, "ui.inventory.slot.potion_small")
    o = click(c, "ui.inventory.assign")["observation"]
    ck.check("퀵슬롯 등록 → q_tut_03 완료, q_tut_04 수락",
             o["player"]["quickslots"][0] == "potion_small" and quest(o, "q_tut_03") is None and quest(o, "q_tut_04") is not None)
    click(c, "ui.inventory.close")
    r = c.act("use_item", item_id="potion_small")
    ck.check("체력 가득일 때 use_item → invalid_state", r.get("reason") == "invalid_state", str(r.get("reason_detail")))

    goto(c, "npc_merchant", near=[-2, 0, -8])
    c.act("interact", target="npc_merchant", verb="talk")
    click(c, "ui.dialog.choice.0")
    click(c, "ui.shop.buy.potion_small")
    o = click(c, "ui.shop.buy.potion_small")["observation"]
    ck.check("작은 물약 2개 구매 → q_tut_04 완료, 보상 후 골드 20", quest(o, "q_tut_04") is None and "quest_completed" in kinds(o) and o["player"]["gold"] == 20)
    o = click(c, "ui.shop.buy.potion_small")["observation"]
    ck.check("다시 구매 → 골드 부족 메시지", "골드가 부족" in (ui(o, "ui.shop.message") or {}).get("text", ""))
    o = click(c, "ui.shop.close")["observation"]
    q5 = quest(o, "q_tut_05")
    ck.check("q_tut_04 완료 → q_tut_05(늑대왕) 자동 수락", q5 is not None and q5["state"] == "active" and o["screen"]["modal"] is None)

    c.act("move_to", target="portal_forest")
    c.act("interact", target="portal_forest", verb="enter")
    won, tries, matched, r = False, 0, [], {}
    while not won and tries < 8:
        tries += 1
        c.act("move_to", pos=[0, 0, 8])
        log: list = []
        r = c.act("engage", log=log, target="wolf_king")
        st = next((m for m in log if m["type"] == "combat_started"), {})
        en = next((m for m in log if m["type"] == "combat_ended"), {})
        matched.append((st.get("loadout") or {}).get("matched"))
        won = bool((en.get("result") or {}).get("cleared"))
    o = r["observation"]
    inv = {i["id"]: i["count"] for i in o["inventory"]}
    ck.check("늑대왕 처치 (%d번째 조우), 로드아웃 없음 → matched=false" % tries, won and all(m is False for m in matched) and inv.get("wolf_fang") == 1,
             "inventory=%s" % inv)
    q5 = quest(o, "q_tut_05")
    ck.check("q_tut_05 처치 목표 완료 → ready, 늑대왕 사라짐", q5 is not None and q5["state"] == "ready" and ent(o, "wolf_king") is None)
    c.act("move_to", target="portal_village")
    c.act("interact", target="portal_village", verb="enter")
    r = goto(c, "npc_guard", near=[30, 0, -30])
    g = ent(r["observation"], "npc_guard")
    ck.check("경비 마커 quest_turn_in", g is not None and g.get("marker") == "quest_turn_in")
    c.act("interact", target="npc_guard", verb="talk")
    click(c, "ui.dialog.choice.0")
    click(c, "ui.dialog.choice.0")
    o = c.rq({"type": "observe"})
    ck.check("경비 보고 → q_tut_05 완료, 진행 중 퀘스트 없음", o["quests"] == [] and o["player"]["gold"] == 70, "gold=%s" % o["player"]["gold"])
    lg = c.rq({"type": "get_log"})
    done = [e[2]["quest"] for e in lg["entries"] if e[1] == "quest_completed"]
    ck.check("get_log: quest_completed 5개 (01→05)", done == ["q_tut_01", "q_tut_02", "q_tut_03", "q_tut_04", "q_tut_05"], str(done))

    o = c.rq({"type": "reset", "seed": 3, "class": "warrior"})
    ck.check("reset → 첫 장면 (골드 20, 인벤토리 비움, q_tut_01, 마을 시작점)",
             o["player"]["gold"] == 20 and o["inventory"] == [] and quest(o, "q_tut_01") is not None and o["player"]["pos"] == [0.0, 0.0, 0.0]
             and o["player"]["zone"] == "village")
    c.close()


# ====================================================================== T5·T6
def t56(ck: Checker, ep: str, bal: Optional[str]) -> None:
    print("== T5·T6 전투 인계·동일성")
    c = Conn(ep)
    c.hello()
    base = {"class": "warrior", "scenario": "forest_wolf_king", "boss": "forest_wolf_king"}
    for name, entry, codes in [
        ("모르는 class", dict(base, **{"class": "paladin"}), ("unknown_class",)),
        ("모르는 scenario", dict(base, scenario="nope"), ("unknown_scenario",)),
        ("시나리오와 다른 boss", dict(base, boss="default"), BOSS_MISMATCH_CODES),
        ("모르는 param", dict(base, params={"zzz": 1}), ("unknown_param",)),
        ("범위 밖 param", dict(base, params={"w_dps": 5}), ("param_out_of_range",)),
    ]:
        r = c.rq({"type": "set_loadout", "entries": [entry]})
        ck.check("set_loadout %s → %s" % (name, "/".join(codes)), r.get("code") in codes, "%s %s" % (r.get("code"), r.get("message", "")))
    r = c.rq({"type": "trigger_response", "encounter_id": "enc_1", "index": 0})
    ck.check("전투 밖 trigger_response → bad_request", r.get("code") == "bad_request")

    stall = dict(base, params={"w_burst": 0.0, "w_dps": 0.0}, triggers={"boss_hp_below": [0.75, 0.5, 0.25]}, source="test: 딜 안 함 → 패배")
    r = c.rq({"type": "set_loadout", "persona": "stable", "entries": [stall]})
    ck.check("set_loadout → loadout_ok", r.get("type") == "loadout_ok" and r.get("entries") == 1)
    c.rq({"type": "reset", "seed": 5, "class": "warrior"})
    o = prep_potions(c)
    inv0 = {i["id"]: i["count"] for i in o["inventory"]}
    ck.check("T-P 준비: 작은 물약 4개, 퀵슬롯 등록", inv0.get("potion_small") == 4 and o["player"]["quickslots"][0] == "potion_small", str(inv0))
    c.act("move_to", target="portal_forest")
    r = c.act("interact", target="portal_forest", verb="enter")
    ck.check("숲 진입", r["observation"]["player"]["zone"] == "forest")

    c.seq += 1
    c.send({"type": "act", "seq": c.seq, "action": "move_to", "args": {"pos": [0, 0, 32]}})
    order: List[str] = []
    busy = None
    replies: list = []
    st = en = res = None
    while True:
        m = c.recv()
        order.append(m["type"])
        if m["type"] == "combat_started":
            st = m
        elif m["type"] == "trigger":
            if busy is None:
                c.send({"type": "observe"})
                busy = c.recv()
                order.append("error:" + str(busy.get("code")))
                c.send({"type": "pilot_note", "kind": "thought", "text": "전투 중 메모"})
                nb = c.recv()
                ck.check("T-N4 전투 중 pilot_note → busy", nb.get("code") == "busy", str(nb))
            replies.append(None)
            c.send({"type": "trigger_response", "encounter_id": m["encounter_id"], "index": m["index"], "params": None})
        elif m["type"] == "combat_ended":
            en = m
        else:
            res = m
            break
    compact = [t for i, t in enumerate(order) if i == 0 or t != order[i - 1]]
    ck.check("순서: combat_started → trigger → (observe=busy) → combat_ended → action_result",
             compact[:3] == ["combat_started", "trigger", "error:busy"] and compact[-2:] == ["combat_ended", "action_result"], str(compact))
    ck.check("combat_started 필드 (seq·encounter·enemy·scenario·boss·seed·loadout·triggers·start_state)",
             st and st["seq"] == c.seq and st["encounter_id"] == "enc_1" and st.get("enemy") == "wolf_king" and st["scenario"] == "forest_wolf_king"
             and st["boss"] == "forest_wolf_king" and isinstance(st["seed"], int) and st["loadout"]["matched"] is True
             and st.get("triggers") == {"boss_hp_below": [0.75, 0.5, 0.25]} and st.get("start_state") == START_STATE,
             json.dumps(st, ensure_ascii=False)[:220])
    ck.check("조우 seed = SplitMix64(reset.seed=5, k=1)", st and st["seed"] == encounter_seed(5, 1), "seed=%s 기대 %s" % (st and st["seed"], encounter_seed(5, 1)))
    ck.check("action_result interrupted(combat)", res.get("status") == "interrupted" and res.get("interrupted_by") == "combat", str(res.get("status")))
    o = res["observation"]
    ck.check("T-P combat_started.potions = {potion_small, available 4, carried 3, cap 3}",
             st.get("potions") == {"item": "potion_small", "available": 4, "carried": 3, "cap": 3}, str(st.get("potions")))
    fs = st.get("field_state") or {}
    ck.check("T-P combat_started.field_state {hp_ratio, resource_ratio, potions, deaths_so_far}",
             fs.get("hp_ratio") == 1.0 and fs.get("potions") == 4 and fs.get("deaths_so_far") == 0 and "resource_ratio" in fs, str(fs))
    used = en["aftermath"].get("potions_used")
    inv1 = {i["id"]: i["count"] for i in o["inventory"]}
    ck.check("T-P aftermath.potions_used = result.consumables_used, 인벤토리에서 차감",
             used == en["result"]["consumables_used"] and inv1.get("potion_small", 0) == 4 - used and ("item_removed" in kinds(o) or used == 0),
             "used=%s inventory=%s" % (used, inv1))
    ck.check("T-P 관찰 events: barrier_restore", "barrier_restore" in kinds(o))
    ck.check("패배 → 체크포인트 부활 (cp_forest), 늑대왕 남아 있음",
             en["result"]["cleared"] is False and en["aftermath"]["respawned_at"] == "cp_forest" and o["player"]["pos"] == [3.0, 0.0, -33.0]
             and "respawned" in kinds(o), "stalled=%s deaths=%s" % (en["result"].get("stalled"), en["result"].get("deaths")))
    ck.check("전투 시간만큼 세계 시간 진행", res["game_seconds"] >= en["result"]["elapsed"], "game_seconds=%s elapsed=%s" % (res["game_seconds"], en["result"]["elapsed"]))
    if bal:
        br, k = balance_run(bal, "warrior", "forest_wolf_king", st["seed"], stall["params"], stall["triggers"], replies)
        ck.check("T5 패배 판: 플레이 result == 밸런스 run_episode result", br == en["result"] and k == len(replies),
                 "diff=%s" % ([kk for kk in (br or {}) if br.get(kk) != en["result"].get(kk)]))

    normal = dict(base, params={}, triggers={"boss_hp_below": [0.75, 0.5, 0.25]}, source="test: default")
    c.rq({"type": "set_loadout", "entries": [normal]})
    won, n, same, books = False, 0, [], []
    r = {}
    while not won and n < 8:
        n += 1
        c.act("move_to", pos=[0, 0, 8])
        log: list = []
        r = c.act("engage", responder=scripted_responder, log=log, target="wolf_king")
        st = next(m for m in log if m["type"] == "combat_started")
        en = next(m for m in log if m["type"] == "combat_ended")
        sent = [scripted_responder(m) for m in log if m["type"] == "trigger"]
        won = en["result"]["cleared"]
        p = st.get("potions") or {}
        books.append(p.get("carried") == min(p.get("available", -1), 3)
                     and en["aftermath"].get("potions_used") == en["result"]["consumables_used"] <= p.get("carried", -1))
        if bal and p.get("carried") == p.get("cap"):
            br, k = balance_run(bal, "warrior", "forest_wolf_king", st["seed"], {}, normal["triggers"], sent)
            same.append(br == en["result"] and k == len(sent))
    ck.check("T-P 조우 %d개 모두 carried = min(보유, cap), potions_used ≤ carried" % n, all(books), str(books))
    ck.check("engage → done, 승리 (%d번째 조우)" % n, won and r.get("status") == "done", str(r.get("status")))
    o = r["observation"]
    ck.check("승리 → 늑대왕 제거·전리품 (aftermath.loot)", ent(o, "wolf_king") is None and any(i["id"] == "wolf_fang" for i in o["inventory"]), str(en["aftermath"]))
    if bal:
        ck.check("T5 carried == cap 인 조우 %d개 모두 result 일치 (트리거 응답 포함)" % len(same), all(same), str(same))
    lg = c.rq({"type": "get_log"})
    kinds_log = [e[1] for e in lg["entries"]]
    ck.check("get_log 에 combat_start·trigger·combat_result 기록", all(k in kinds_log for k in ("combat_start", "trigger", "combat_result")))

    # 퀵슬롯에 물약이 없으면 물약 0개로 싸운다
    c.rq({"type": "set_loadout", "entries": [stall]})
    c.rq({"type": "reset", "seed": 5, "class": "warrior"})
    c.act("move_to", target="portal_forest")
    c.act("interact", target="portal_forest", verb="enter")
    log = []
    c.act("move_to", pos=[0, 0, 32], log=log, responder=lambda m: None)
    st = next((m for m in log if m["type"] == "combat_started"), {})
    en = next((m for m in log if m["type"] == "combat_ended"), {})
    ck.check("T-P 퀵슬롯 물약 없음 → carried 0, consumables_used 0",
             st.get("potions") == {"item": None, "available": 0, "carried": 0, "cap": 3} and en.get("result", {}).get("consumables_used") == 0
             and en.get("aftermath", {}).get("potions_used") == 0, str(st.get("potions")))
    c.close()


# ====================================================================== T-N
def tn(ck: Checker, ep: str) -> None:
    print("== T-N pilot_note (v0.3)")
    c = Conn(ep)
    c.hello()
    r = note(c, "thought", "reset 전 메모")
    ck.check("T-N4 reset 전 pilot_note → not_reset", r.get("code") == "not_reset", str(r))
    c.rq({"type": "reset", "seed": 7, "class": "warrior"})
    r = note(c, "idea", "모르는 종류")
    ck.check("T-N4 잘못된 kind → bad_request", r.get("code") == "bad_request", str(r))
    r = note(c, "plan", "   ")
    ck.check("T-N4 빈 text → bad_request", r.get("code") == "bad_request", str(r))
    o1 = c.rq({"type": "observe"})
    r = note(c, "thought", "촌장에게 먼저 말을 걸어 보자")
    ck.check("pilot_note → pilot_note_ok", r.get("type") == "pilot_note_ok", str(r))
    o2 = c.rq({"type": "observe"})
    ck.check("T-N2 observe → pilot_note → observe: seq 말고 같음 (game_time 포함)", strip_seq(o1) == strip_seq(o2),
             "game_time %s → %s" % (o1.get("game_time"), o2.get("game_time")))
    h1 = c.rq({"type": "observe", "mode": "hierarchy", "root": "ui", "max_depth": 12})
    note(c, "plan", "인벤토리를 열어 물약을 확인한다")
    note(c, "finding", "경비병 위치를 알려 주는 곳이 없다")
    h2 = c.rq({"type": "observe", "mode": "hierarchy", "root": "ui", "max_depth": 12})
    ck.check("T-N2 메모가 hierarchy 관찰에 안 나옴", strip_seq(h1) == strip_seq(h2) and "QA 플레이어" not in json.dumps(h2, ensure_ascii=False))
    r = click(c, "ui.hud.inventory")
    ck.check("T-N5 패널이 떠 있어도 인벤토리 버튼 ui_click → done (가림 없음)", r.get("status") == "done",
             "%s %s" % (r.get("reason"), r.get("reason_detail")))
    sc = json.dumps(r["observation"]["screen"], ensure_ascii=False)
    ck.check("T-N5 screen.ui 에 메모 없음", "경비병 위치" not in sc and "촌장에게 먼저" not in sc)
    lg = c.rq({"type": "get_log"})
    pn = [e for e in lg["entries"] if e[1] == "pilot_note"]
    ck.check("T-N3 get_log 에 pilot_note {kind,text} 3개", [e[2]["kind"] for e in pn] == ["thought", "plan", "finding"]
             and pn[0][2] == {"kind": "thought", "text": "촌장에게 먼저 말을 걸어 보자"}, str([e[2] for e in pn]))
    c.close()


def encounter_seed(seed: int, k: int) -> int:
    """PLAY_PROTOCOL 4.7 조우 seed (SplitMix64 혼합, 0 ~ 2^31-1)."""
    m = (1 << 64) - 1
    z = (seed + 0x9E3779B97F4A7C15 * k) & m
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & m
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & m
    z ^= z >> 31
    return z & 0x7FFFFFFF


# ====================================================================== T7·T8
def scripted_run(ep: str, seed: int = 11, notes: bool = False):
    """notes=True 면 행동 사이에 pilot_note 4개 (T-N3: 로그에서 pilot_note 를 빼면 없는 판과 같아야 함)."""
    c = Conn(ep)
    c.hello()
    nt = (lambda k, s: note(c, k, s)) if notes else (lambda k, s: None)
    c.rq({"type": "set_loadout", "entries": [{"class": "warrior", "scenario": "forest_wolf_king",
                                              "params": {"w_survival": 0.5}, "triggers": {"boss_hp_below": [0.75, 0.5, 0.25]}}]})
    first = c.rq({"type": "reset", "seed": seed, "class": "warrior"})
    nt("plan", "촌장부터 찾아간다")
    goto(c, "npc_elder")
    c.act("interact", target="npc_elder", verb="talk")
    nt("thought", "약초 퀘스트를 받는다")
    click(c, "ui.dialog.choice.0")
    click(c, "ui.dialog.choice.0")
    nt("finding", "테스트 발견 메모")
    click(c, "ui.hud.quests")
    click(c, "ui.quests.close")
    c.act("move_to", target="portal_forest")
    c.act("interact", target="portal_forest", verb="enter")
    for h, near in {"herb_01": [-4, 0, -28], "herb_02": [4, 0, -23]}.items():
        goto(c, h, near)
        c.act("interact", target=h, verb="pickup")
    c.act("wait", seconds=2.5)
    nt("plan", "늑대왕 쪽으로 간다")
    c.act("move_to", pos=[0, 0, 32], responder=scripted_responder)
    c.act("move_to", pos=[0, 0, 8])
    c.act("engage", target="wolf_king", responder=scripted_responder)
    last = c.rq({"type": "observe"})
    lg = c.rq({"type": "get_log"})
    again = c.rq({"type": "reset", "seed": seed, "class": "warrior"})
    c.close()
    return lg["entries"], last, first, again


def strip_seq(o):
    o = json.loads(json.dumps(o))
    o.pop("seq", None)
    return o


def t78(ck: Checker, ep: str, ep2: Optional[str], bal: Optional[str]) -> None:
    print("== T7 결정성 · T8 새 게임")
    a = scripted_run(ep)
    b = scripted_run(ep)
    nc = sum(1 for e in a[0] if e[1] == "combat_result")
    ck.check("T7 같은 인스턴스 2회: get_log 동일 (%d항목, 전투 %d회)" % (len(a[0]), nc), a[0] == b[0] and nc >= 1)
    ck.check("T7 마지막 관찰 동일", strip_seq(a[1]) == strip_seq(b[1]))
    nn = scripted_run(ep, notes=True)
    ck.check("T-N3 같은 행동열 + 메모 4개: 로그에서 pilot_note 를 빼면 메모 없는 판과 같음",
             no_notes(nn[0]) == a[0] and len(nn[0]) - len(a[0]) == 4 and strip_seq(nn[1]) == strip_seq(a[1]),
             "항목 %d vs %d" % (len(nn[0]), len(a[0])))
    c3 = scripted_run(ep, seed=12)
    ck.check("T7 다른 seed → 전투 결과가 달라짐", [e for e in c3[0] if e[1] == "combat_result"] != [e for e in a[0] if e[1] == "combat_result"])
    if ep2:
        d = scripted_run(ep2)
        diff = next((i for i, (x, y) in enumerate(zip(a[0], d[0])) if x != y), None)
        ck.check("T7 다른 인스턴스(%s)와도 get_log 동일" % ep2, a[0] == d[0], "첫 차이 #%s" % diff)
    ck.check("T8 진행 후 reset → 첫 장면과 같은 관찰 (seq 제외)", strip_seq(a[2]) == strip_seq(a[3]),
             "gold=%s zone=%s" % (a[3]["player"]["gold"], a[3]["player"]["zone"]))
    if bal:
        h, p = parse_endpoint(bal)
        s = socket.create_connection((h, p), timeout=60)
        f = s.makefile("rwb")
        out = []
        for m in ({"type": "reset", "seed": 1}, {"type": "play_describe"}):
            f.write((json.dumps(m) + "\n").encode("utf-8"))
            f.flush()
            out.append(json.loads(f.readline().decode("utf-8")))
        s.close()
        ck.check("T8 밸런스 인스턴스는 플레이 메시지를 모름 (reset·play_describe → unknown_type)",
                 all(r.get("code") == "unknown_type" for r in out))


# ====================================================================== T9
def t9(ck: Checker, ep: str, bal: Optional[str], loadout_paths: Sequence[str], seed: int = 21, max_encounters: int = 6) -> None:
    """학습 결과(params.json / policy.json) → set_loadout + 응답기 → 필드 전투. 밸런스 run_episode 와 result 일치."""
    print("== T9 학습 결과 인계 (%s)" % ", ".join(loadout_paths))
    lb = LoadoutBuilder()
    for pth in loadout_paths:
        lb.add_file(pth)
    c = Conn(ep)
    c.hello()
    d = c.rq({"type": "play_describe"})
    problems = lb.check_against(d)
    ck.check("로드아웃 ↔ play_description 일치", not problems, "; ".join(problems + lb.notes))
    entries = lb.wire_entries(d)
    r = c.rq({"type": "set_loadout", "persona": lb.persona(), "entries": entries})
    ck.check("set_loadout(학습 결과 %d개) → loadout_ok" % len(entries), r.get("type") == "loadout_ok", str(r.get("message", "")))
    responder = lb.responder()
    fwk = [e for e in lb.entries.values() if e.scenario == "forest_wolf_king"]
    if not fwk:
        ck.check("forest_wolf_king 로드아웃 있음 (필드 조우 대상)", False, "가진 키: %s" % list(lb.entries))
        c.close()
        return
    e = fwk[0]
    c.rq({"type": "reset", "seed": seed, "class": e.cls})
    prep_potions(c)   # 전투에 물약 cap 개 (v0.3: 퀵슬롯 물약만 가져간다)
    c.act("move_to", target="portal_forest")
    c.act("interact", target="portal_forest", verb="enter")
    wins, same, n, answered, short = 0, [], 0, 0, 0
    while n < max_encounters:
        r = c.act("move_to", pos=[0, 0, 8])
        log: list = []
        r = c.act("engage", responder=responder, log=log, target="wolf_king")
        st = next((m for m in log if m["type"] == "combat_started"), None)
        en = next((m for m in log if m["type"] == "combat_ended"), None)
        if st is None or en is None:
            break
        n += 1
        ck_matched = (st.get("loadout") or {}).get("matched") is True
        trig = [m for m in log if m["type"] == "trigger"]
        sent = [e.policy.params(m) for m in trig] if e.policy is not None else [None] * len(trig)
        answered += len(trig)
        p = st.get("potions") or {}
        if p and p.get("carried") != p.get("cap"):   # 물약이 모자란 조우 = 학습·밸런스 판과 시작이 다름 → 비교 안 함
            short += 1
        elif bal:
            br, k = balance_run(bal, e.cls, e.scenario, st["seed"], e.params,
                                {"boss_hp_below": e.triggers} if e.triggers else None, sent)
            same.append(br == en["result"] and k == len(sent) and ck_matched)
        if en["result"]["cleared"]:
            wins += 1
            break   # 처치하면 적이 사라진다
    ck.check("학습 로드아웃으로 늑대왕 처치 (%d번째 조우, 트리거 응답 %d회, %s)" % (n, answered, e.method), wins == 1, e.source)
    if bal:
        ck.check("T9 carried == cap 조우 %d개 모두 밸런스 run_episode 와 result 일치 (matched=true, 물약 모자란 조우 %d개 제외)" % (len(same), short),
                 same and all(same), str(same))
    c.close()


# ====================================================================== 인스턴스 띄우기
def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Instances:
    """--exe 로 헤드리스 인스턴스를 띄운다: play, play(omniscient), play2(T7 교차), balance."""

    def __init__(self, exe: str, timeout: float = 90.0) -> None:
        self.exe = str(Path(exe))
        self.timeout = timeout
        self.procs: List[subprocess.Popen] = []

    def start(self, play_flags: Sequence[str] = ()) -> str:
        port = free_port()
        cmd = [self.exe, "-batchmode", "-nographics"] + list(play_flags) + ["-qaPort", str(port)]
        self.procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        ep = "127.0.0.1:%d" % port
        self._wait(port)
        return ep

    def _wait(self, port: int) -> None:
        end = time.time() + self.timeout
        while time.time() < end:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                return
            except OSError:
                time.sleep(0.3)
        raise TimeoutError("게임 인스턴스가 %d 포트를 열지 않음" % port)

    def stop(self) -> None:
        for p in self.procs:
            p.kill()
        for p in self.procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass


def run_all(game: str, omni: Optional[str] = None, balance: Optional[str] = None, game2: Optional[str] = None,
            loadout: Sequence[str] = (), only: Optional[Sequence[str]] = None) -> Checker:
    ck = Checker()
    want = set(only or ("T2", "T3", "T4", "T56", "TN", "T78", "T9"))
    if "T2" in want:
        t2(ck, game)
    if "T3" in want:
        t3(ck, game, omni)
    if "T4" in want:
        t4(ck, game)
    if "T56" in want:
        t56(ck, game, balance)
    if "TN" in want:
        tn(ck, game)
    if "T78" in want:
        t78(ck, game, game2, balance)
    if "T9" in want and loadout:
        t9(ck, game, balance, loadout)
    n = len(ck.results)
    print("\n결과: %s (%d/%d)" % ("PASS" if ck.passed else "FAIL", sum(1 for _, ok, _ in ck.results if ok), n), flush=True)
    return ck
