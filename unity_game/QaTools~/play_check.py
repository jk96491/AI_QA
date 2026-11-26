"""플레이 모드 자체 검증 (PLAY_MODE_REQUEST 6장) — LLM 없는 스크립트 클라이언트. 표준 라이브러리만.

    python play_check.py --game 127.0.0.1:7800 [--omni 127.0.0.1:7801] [--balance 127.0.0.1:7777] [--game2 127.0.0.1:7802]

  T2 핸드셰이크: protocol 불일치 → error(protocol_version), reset 전 act/observe → error(not_reset)
  T3 지각 필터 : 시야 밖 NPC 는 entities 에 없음 (--omni 인스턴스에서는 hidden:true 로 있음),
                 모달에 가린 버튼 interactable:false, 그 버튼 ui_click → failed(not_interactable) + 가린 요소 id
  P1 기타      : move_to·interact(talk)·대화 ui_click, unreachable, out_of_range, unknown_action
  T4 튜토리얼  : 고정 행동열로 q_tut_01~05 완주 ("나중에" 함정, 골드 부족 구매 실패, 안내 팝업 가림, 닿을 수 없는 상자, 늑대왕)
  T5 전투 동일성: 플레이 조우 result == 밸런스 서버 run_episode(같은 class·시나리오·seed·params·트리거 응답) result  (--balance 필요)
  T6 전투 인계 : move_to 중 어그로 → combat_started → trigger → (전투 중 observe = busy) → combat_ended → action_result(interrupted, combat), 패배 시 체크포인트 부활
  T7 결정성    : 같은 reset.seed + 같은 행동열 2회 → get_log·마지막 관찰이 같음 (--game2 를 주면 다른 인스턴스(예: 창 ↔ 헤드리스)와도 비교)
  T8 새 게임   : 진행 후 reset → 첫 장면과 완전히 같음. 밸런스 인스턴스(--balance)는 플레이 메시지를 모름
  T-P  물약    : (v0.3) 전투 물약 = 퀵슬롯 등록 물약 min(보유, cap), 마신 만큼 인벤토리 차감, 결계 barrier_restore·field_state
  T-N  메모    : (v0.3) pilot_note — hello 0.3·describe.pilot_notes, 관찰 불변, 로그(재생 비교에서 제외), 오류 코드, ui_click 가림 없음
"""
import argparse
import json
import socket
import sys

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, (" — " + detail) if detail else ""))
    return ok


class Conn:
    def __init__(self, ep):
        h, p = ep.rsplit(":", 1)
        self.s = socket.create_connection((h, int(p)), timeout=120)
        self.f = self.s.makefile("rwb")
        self.seq = 0

    def rq(self, m):
        self.f.write((json.dumps(m, ensure_ascii=False) + "\n").encode("utf-8"))
        self.f.flush()
        line = self.f.readline()
        if not line:
            raise RuntimeError("연결 끊김")
        return json.loads(line.decode("utf-8"))

    def send(self, m):
        self.f.write((json.dumps(m, ensure_ascii=False) + "\n").encode("utf-8"))
        self.f.flush()

    def recv(self):
        line = self.f.readline()
        if not line:
            raise RuntimeError("연결 끊김")
        return json.loads(line.decode("utf-8"))

    def act(self, action, responder=None, log=None, **args):
        """act 보내고 action_result(또는 error)까지 읽는다. 중간 전투 메시지는 log 에 쌓고 trigger 는 responder(msg) 로 응답."""
        self.seq += 1
        self.send({"type": "act", "seq": self.seq, "action": action, "args": args})
        while True:
            m = self.recv()
            if log is not None:
                log.append(m)
            if m.get("type") == "trigger":
                params = responder(m) if responder else None
                self.send({"type": "trigger_response", "encounter_id": m["encounter_id"], "index": m["index"], "params": params})
                continue
            if m.get("type") in ("combat_started", "combat_ended"):
                continue
            return m

    def close(self):
        try:
            self.f.write(b'{"type":"bye"}\n')
            self.f.flush()
        except OSError:
            pass
        self.s.close()


def ids(obs, key="entities"):
    return [e["id"] for e in obs[key]]


def ui(obs, uid):
    for e in obs["screen"]["ui"]:
        if e["id"] == uid:
            return e
    return None


PLAY_VERSION = "0.3"


def hello(c):
    return c.rq({"type": "hello", "protocol": "play", "protocol_version": PLAY_VERSION, "client": "play_check"})


def note(c, kind, text):
    c.seq += 1
    return c.rq({"type": "pilot_note", "seq": c.seq, "kind": kind, "text": text})


def no_notes(entries):
    return [e for e in entries if e[1] != "pilot_note"]


def t2(ep):
    print("== T2 핸드셰이크")
    c = Conn(ep)
    r = c.rq({"type": "hello", "protocol_version": "1.2", "client": "balance_qa"})
    check("밸런스 클라이언트 hello → protocol_version", r.get("type") == "error" and r.get("code") == "protocol_version", r.get("message", ""))
    r = c.rq({"type": "hello", "protocol": "play", "protocol_version": "9.0"})
    check("다른 버전 → protocol_version", r.get("code") == "protocol_version")
    r = c.rq({"type": "hello", "protocol": "play", "protocol_version": "0.1"})
    check("T-N1 hello play 0.1 → protocol_version (0.x 주.부 일치)", r.get("code") == "protocol_version", r.get("message", ""))
    r = hello(c)
    check("T-N1 hello play 0.3 → hello_ok (오류 후 연결 유지)", r.get("type") == "hello_ok" and r.get("protocol") == "play" and r.get("protocol_version") == "0.3",
          "game %s" % r.get("game_version"))
    r = c.act("move_to", target="npc_elder")
    check("reset 전 act → not_reset", r.get("code") == "not_reset")
    r = c.rq({"type": "observe"})
    check("reset 전 observe → not_reset", r.get("code") == "not_reset")
    d = c.rq({"type": "play_describe"})
    check("play_describe", d.get("type") == "play_description" and [a["name"] for a in d["actions"]] == ["move_to", "interact", "ui_click", "use_item", "engage", "wait"],
          "classes=%s scenarios=%s" % (d.get("classes"), [s["name"] for s in d.get("scenarios", [])]))
    check("T-N1 describe.pilot_notes {max_chars:200, kinds}", d.get("pilot_notes") == {"max_chars": 200, "kinds": ["thought", "plan", "finding"]}, str(d.get("pilot_notes")))
    check("describe.combat.encounter_start_state = barrier_inventory_potions", d["combat"].get("encounter_start_state") == "barrier_inventory_potions")
    r = c.rq({"type": "reset", "seed": 1, "start": "checkpoint"})
    check("reset 에 시작 지점 옵션 → bad_request (항상 새 게임)", r.get("code") == "bad_request")
    r = c.rq({"type": "reset", "seed": 1, "class": "paladin"})
    check("reset 모르는 class → unknown_class", r.get("code") == "unknown_class")
    r = c.rq({"type": "nope"})
    check("모르는 type → unknown_type", r.get("code") == "unknown_type")
    c.f.write(b"{not json\n")
    c.f.flush()
    r = json.loads(c.f.readline())
    check("JSON 오류 → bad_request", r.get("code") == "bad_request")
    c.close()
    # 새 연결은 reset 부터
    c = Conn(ep)
    r = c.rq({"type": "observe"})
    check("새 연결 → 다시 not_reset", r.get("code") == "not_reset")
    c.close()


def t3(ep, omni):
    print("== T3 지각 필터 + P1 행동")
    c = Conn(ep)
    hello(c)
    o = c.rq({"type": "reset", "seed": 1, "class": "warrior"})
    check("reset → observation", o.get("type") == "observation" and o["player"]["zone"] == "village", "entities=%s" % ids(o))
    check("시야 밖 NPC(npc_guard) 없음", "npc_guard" not in ids(o))
    check("시야 안 NPC(npc_elder) 있음", "npc_elder" in ids(o))
    check("alwaysKnown(portal_forest) 시야 밖이어도 있음", "portal_forest" in ids(o))
    check("hidden_included=false", o.get("hidden_included") is False)
    check("new_game 사건", any(e[1] == "new_game" for e in o["events"]))

    r = c.act("move_to", target="npc_guard")
    check("시야 밖 대상 move_to → not_visible", r.get("status") == "failed" and r.get("reason") == "not_visible", str(r.get("reason")))
    r = c.act("interact", target="npc_elder", verb="talk")
    check("범위 밖 interact → out_of_range (자동 접근 안 함)", r.get("reason") == "out_of_range", str(r.get("reason_detail")))
    r = c.act("move_to", pos=[-15, 0, 10])
    check("울타리 안 위치 move_to → unreachable", r.get("status") == "failed" and r.get("reason") == "unreachable", str(r.get("reason")))
    r = c.act("fly", target="npc_elder")
    check("모르는 행동 → error(unknown_action)", r.get("code") == "unknown_action")
    r = c.act("move_to")
    check("인자 없음 → error(bad_request)", r.get("code") == "bad_request")

    r = c.act("move_to", target="npc_elder")
    o = r.get("observation", {})
    el = next((e for e in o.get("entities", []) if e["id"] == "npc_elder"), None)
    check("move_to npc_elder → done", r.get("status") == "done" and el is not None and el["distance"] <= 2.5,
          "game_seconds=%s distance=%s" % (r.get("game_seconds"), el and el["distance"]))
    hud = ui(o, "ui.hud.quests")
    check("모달 없을 때 ui.hud.quests interactable:true", hud is not None and hud["interactable"] is True)

    r = c.act("interact", target="npc_elder", verb="talk")
    o = r["observation"]
    check("interact talk → 대화창", r.get("status") == "done" and o["screen"]["modal"] == "dialog",
          "text=%s" % (ui(o, "ui.dialog.text") or {}).get("text"))
    choices = [e["text"] for e in o["screen"]["ui"] if e["id"].startswith("ui.dialog.choice.")]
    check("선택지 2개 보임", choices == ["맡겨 주세요", "나중에"], str(choices))
    hud = ui(o, "ui.hud.quests")
    check("대화창에 가린 ui.hud.quests interactable:false", hud is not None and hud["interactable"] is False)
    r = c.act("ui_click", ui_id="ui.hud.quests")
    check("가린 버튼 ui_click → failed(not_interactable) + 가린 요소 id",
          r.get("status") == "failed" and r.get("reason") == "not_interactable" and "ui.dialog" in str(r.get("reason_detail")),
          str(r.get("reason_detail")))
    r = c.act("move_to", target="npc_guard")
    check("대화 중 move_to → blocked_by_modal", r.get("reason") == "blocked_by_modal")

    r = c.act("ui_click", ui_id="ui.dialog.choice.0")
    o = r["observation"]
    check("선택지 0 → 다음 노드", r.get("status") == "done" and o["screen"]["modal"] == "dialog" and
          [e["text"] for e in o["screen"]["ui"] if e["id"].startswith("ui.dialog.choice.")] == ["다녀오겠습니다"])
    r = c.act("ui_click", ui_id="ui.dialog.choice.1")
    check("사라진 선택지 1 → unknown_target", r.get("reason") == "unknown_target")
    r = c.act("ui_click", ui_id="ui.dialog.choice.0")
    o = r["observation"]
    kinds = [e[1] for e in o["events"]]
    check("대화 종료", o["screen"]["modal"] is None and "dialog_closed" in kinds, str(kinds))
    r = c.act("ui_click", ui_id="ui.hud.quests")
    o = r["observation"]
    check("모달 닫힌 뒤 ui.hud.quests 클릭 → 퀘스트 창", r.get("status") == "done" and o["screen"]["modal"] == "quests")
    h = c.rq({"type": "observe", "mode": "hierarchy", "root": "ui.quests", "max_depth": 3})
    check("hierarchy 관찰", h.get("type") == "observation" and h["tree"]["id"] == "ui.quests" and len(h["tree"]["children"]) > 0,
          "children=%s" % [ch["id"] for ch in h.get("tree", {}).get("children", [])])
    r = c.act("ui_click", ui_id="ui.quests.close")
    check("퀘스트 창 닫기", r["observation"]["screen"]["modal"] is None)

    # 시야: 경비에게 좌표로 다가가면 보이게 된다
    r = c.act("move_to", pos=[34, 0, -30])   # 경비(34,-22) 가 카메라 앞쪽에 오는 위치
    o = r["observation"]
    check("이동 후 npc_guard 시야에 들어옴", r.get("status") == "done" and "npc_guard" in ids(o), "entities=%s" % ids(o))
    r = c.act("wait", seconds=1.5)
    check("wait 1.5초", r.get("status") == "done" and abs(r.get("game_seconds", 0) - 1.5) < 1e-6, str(r.get("game_seconds")))
    lg = c.rq({"type": "get_log"})
    check("get_log", lg.get("type") == "play_log" and len(lg["entries"]) > 10, "entries=%d" % len(lg.get("entries", [])))
    c.close()

    if omni:
        c = Conn(omni)
        hello(c)
        d = c.rq({"type": "play_describe"})
        o = c.rq({"type": "reset", "seed": 1, "class": "warrior"})
        g = next((e for e in o["entities"] if e["id"] == "npc_guard"), None)
        check("omniscient: 시야 밖 npc_guard 가 hidden:true 로 있음", d["debug"]["omniscient"] is True and g is not None and g.get("hidden") is True,
              "hidden_included=%s" % o.get("hidden_included"))
        dlg = [e for e in o["screen"]["ui"] if e["id"].startswith("ui.dialog")]
        check("omniscient: 닫힌 대화창 요소도 hidden:true 로 있음", len(dlg) > 0 and all(e.get("hidden") for e in dlg), "%d개" % len(dlg))
        c.close()


def ent(obs, eid):
    return next((e for e in obs.get("entities", []) if e["id"] == eid), None)


def quest(obs, qid):
    return next((q for q in obs.get("quests", []) if q["id"] == qid), None)


def kinds(obs):
    return [e[1] for e in obs.get("events", [])]


def goto(c, target, near=None):
    """대상이 안 보이면 근처 좌표로 먼저 간 뒤 대상으로 (LLM 이 탐색하는 것과 같은 2단계)."""
    r = c.act("move_to", target=target)
    if r.get("reason") == "not_visible" and near is not None:
        c.act("move_to", pos=near)
        r = c.act("move_to", target=target)
    return r


def click(c, uid):
    return c.act("ui_click", ui_id=uid)


def t4(ep):
    print("== T4 튜토리얼 q_tut_01~04 (고정 행동열)")
    c = Conn(ep)
    hello(c)
    o = c.rq({"type": "reset", "seed": 3, "class": "warrior"})
    q1 = quest(o, "q_tut_01")
    check("시작: q_tut_01 진행 중, 촌장 마커 objective", q1 is not None and q1["state"] == "active" and ent(o, "npc_elder")["marker"] == "objective")

    # --- q_tut_01 + "나중에" 함정
    goto(c, "npc_elder")
    r = c.act("interact", target="npc_elder", verb="talk")
    o = r["observation"]
    check("촌장 대화 → q_tut_01 완료", "quest_completed" in kinds(o) and quest(o, "q_tut_01") is None)
    r = click(c, "ui.dialog.choice.1")   # 나중에
    o = r["observation"]
    check("함정: '나중에' → q_tut_02 수락 안 됨, 마커 quest_available",
          quest(o, "q_tut_02") is None and "quest_accepted" not in kinds(o) and ent(o, "npc_elder").get("marker") == "quest_available")
    c.act("interact", target="npc_elder", verb="talk")
    r = click(c, "ui.dialog.choice.0")   # 맡겨 주세요
    o = r["observation"]
    q2 = quest(o, "q_tut_02")
    check("'맡겨 주세요' → q_tut_02 수락, 진행도 [0,3]", q2 is not None and q2["objectives"][0]["progress"] == [0, 3])
    click(c, "ui.dialog.choice.0")

    # --- 닿을 수 없는 상자
    r = c.act("move_to", pos=[-15, 0, 10])
    check("울타리 안 상자 위치 → unreachable", r.get("reason") == "unreachable")

    # --- 골드 부족 구매 (보유 20G < 25G)
    r = goto(c, "npc_merchant", near=[-2, 0, -8])
    check("상인에게 이동", r.get("status") == "done", str(r.get("reason")))
    c.act("interact", target="npc_merchant", verb="talk")
    r = click(c, "ui.dialog.choice.0")
    o = r["observation"]
    big = ui(o, "ui.shop.buy.potion_large")
    check("상점 열림, 큰 물약(80G) 구매 버튼 비활성", o["screen"]["modal"] == "shop" and big is not None and big["interactable"] is False)
    r = click(c, "ui.shop.buy.potion_small")
    o = r["observation"]
    msg = (ui(o, "ui.shop.message") or {}).get("text", "")
    check("골드 부족 구매 → 실패 메시지가 관찰에 보임", "골드가 부족" in msg and "purchase_failed" in kinds(o) and o["player"]["gold"] == 20, msg)
    r = click(c, "ui.shop.buy.potion_large")
    check("비활성 버튼 클릭 → failed(not_interactable, disabled)", r.get("reason") == "not_interactable" and r.get("reason_detail") == "disabled")
    click(c, "ui.shop.close")

    # --- 숲에서 약초 3개
    r = c.act("move_to", target="portal_forest")
    check("숲 입구(alwaysKnown)로 이동", r.get("status") == "done", str(r.get("reason")))
    r = c.act("interact", target="portal_forest", verb="enter")
    o = r["observation"]
    check("숲 진입", o["player"]["zone"] == "forest" and "zone_entered" in kinds(o))
    herbs = {"herb_01": [-4, 0, -28], "herb_02": [4, 0, -23], "herb_03": [-6, 0, -15]}
    for h, near in herbs.items():
        r = goto(c, h, near)
        r = c.act("interact", target=h, verb="pickup")
        check("약초 줍기 " + h, r.get("status") == "done", str(r.get("reason")))
    o = r["observation"]
    q2 = quest(o, "q_tut_02")
    check("q_tut_02 진행도 [3,3] → ready", q2 is not None and q2["objectives"][0]["progress"] == [3, 3] and q2["state"] == "ready")
    c.act("move_to", target="portal_village")
    r = c.act("interact", target="portal_village", verb="enter")
    check("마을 복귀", r["observation"]["player"]["zone"] == "village")

    # --- q_tut_02 반납
    r = goto(c, "npc_elder")
    check("촌장 마커 quest_turn_in", ent(r["observation"], "npc_elder").get("marker") == "quest_turn_in")
    c.act("interact", target="npc_elder", verb="talk")
    r = click(c, "ui.dialog.choice.0")
    o = r["observation"]
    inv = {i["id"]: i["count"] for i in o["inventory"]}
    check("q_tut_02 완료: 약초 회수, 골드 50, 작은 물약 2", "quest_completed" in kinds(o) and o["player"]["gold"] == 50 and inv == {"potion_small": 2}, str(inv))
    click(c, "ui.dialog.choice.0")

    # --- q_tut_03 인벤토리 + 안내 팝업 가림
    r = click(c, "ui.hud.inventory")
    o = r["observation"]
    asg = ui(o, "ui.inventory.assign")
    check("인벤토리 첫 열기 → 안내 팝업(tip)이 위에 뜸", o["screen"]["modal"] == "tip" and asg is not None and asg["interactable"] is False)
    r = click(c, "ui.inventory.slot.potion_small")
    check("팝업에 가린 슬롯 클릭 → not_interactable, blocked by ui.tip",
          r.get("reason") == "not_interactable" and "ui.tip" in str(r.get("reason_detail")), str(r.get("reason_detail")))
    r = click(c, "ui.tip.ok")
    o = r["observation"]
    check("팝업 닫기 → 인벤토리, 선택 전 등록 버튼 비활성", o["screen"]["modal"] == "inventory" and ui(o, "ui.inventory.assign")["interactable"] is False)
    click(c, "ui.inventory.slot.potion_small")
    r = click(c, "ui.inventory.assign")
    o = r["observation"]
    check("퀵슬롯 등록 → q_tut_03 완료, q_tut_04 수락",
          o["player"]["quickslots"][0] == "potion_small" and quest(o, "q_tut_03") is None and quest(o, "q_tut_04") is not None)
    click(c, "ui.inventory.close")
    r = c.act("use_item", item_id="potion_small")
    check("체력 가득일 때 use_item → invalid_state", r.get("reason") == "invalid_state", str(r.get("reason_detail")))

    # --- q_tut_04 구매
    goto(c, "npc_merchant", near=[-2, 0, -8])
    c.act("interact", target="npc_merchant", verb="talk")
    click(c, "ui.dialog.choice.0")
    click(c, "ui.shop.buy.potion_small")
    r = click(c, "ui.shop.buy.potion_small")
    o = r["observation"]
    check("작은 물약 2개 구매 → q_tut_04 완료, 보상 후 골드 20", quest(o, "q_tut_04") is None and "quest_completed" in kinds(o) and o["player"]["gold"] == 20)
    r = click(c, "ui.shop.buy.potion_small")
    o = r["observation"]
    check("다시 구매 → 골드 부족 메시지", "골드가 부족" in (ui(o, "ui.shop.message") or {}).get("text", ""))
    r = click(c, "ui.shop.close")
    o = r["observation"]
    q5 = quest(o, "q_tut_05")
    check("q_tut_04 완료 → q_tut_05(늑대왕) 자동 수락", q5 is not None and q5["state"] == "active" and o["screen"]["modal"] is None)

    # --- q_tut_05 늑대왕 (로드아웃 없음 → 정의서 default, matched=false). 지면 체크포인트에서 다시
    c.act("move_to", target="portal_forest")
    c.act("interact", target="portal_forest", verb="enter")
    won, tries, matched = False, 0, []
    while not won and tries < 8:
        tries += 1
        c.act("move_to", pos=[0, 0, 8])
        log = []
        r = c.act("engage", log=log, target="wolf_king")
        st = next((m for m in log if m["type"] == "combat_started"), {})
        en = next((m for m in log if m["type"] == "combat_ended"), {})
        matched.append(st.get("loadout", {}).get("matched"))
        won = bool(en.get("result", {}).get("cleared"))
    o = r["observation"]
    inv = {i["id"]: i["count"] for i in o["inventory"]}
    check("늑대왕 처치 (%d번째 조우), 로드아웃 없음 → matched=false" % tries, won and all(m is False for m in matched) and inv.get("wolf_fang") == 1,
          "inventory=%s" % inv)
    q5 = quest(o, "q_tut_05")
    check("q_tut_05 처치 목표 완료 → ready, 늑대왕 사라짐", q5 is not None and q5["state"] == "ready" and ent(o, "wolf_king") is None)
    c.act("move_to", target="portal_village")
    c.act("interact", target="portal_village", verb="enter")
    r = goto(c, "npc_guard", near=[30, 0, -30])
    check("경비 마커 quest_turn_in", ent(r["observation"], "npc_guard") is not None and ent(r["observation"], "npc_guard").get("marker") == "quest_turn_in")
    c.act("interact", target="npc_guard", verb="talk")
    r = click(c, "ui.dialog.choice.0")
    click(c, "ui.dialog.choice.0")
    o = c.rq({"type": "observe"})
    check("경비 보고 → q_tut_05 완료, 진행 중 퀘스트 없음", o["quests"] == [] and o["player"]["gold"] == 70, "gold=%s" % o["player"]["gold"])
    lg = c.rq({"type": "get_log"})
    done = [e[2]["quest"] for e in lg["entries"] if e[1] == "quest_completed"]
    check("get_log: quest_completed 5개 (01→05)", done == ["q_tut_01", "q_tut_02", "q_tut_03", "q_tut_04", "q_tut_05"], str(done))

    # --- reset = 새 게임 (T8 일부)
    o = c.rq({"type": "reset", "seed": 3, "class": "warrior"})
    check("reset → 첫 장면 (골드 20, 인벤토리 비움, q_tut_01, 마을 시작점)",
          o["player"]["gold"] == 20 and o["inventory"] == [] and quest(o, "q_tut_01") is not None and abs(o["player"]["pos"][0]) <= 1.5 and abs(o["player"]["pos"][2]) <= 1.5
          and o["player"]["zone"] == "village")
    c.close()


def responder(m):
    """결정적 트리거 응답 (밸런스 서버에도 같은 값을 보낸다)."""
    return {"w_survival": round(0.3 + 0.15 * m["index"], 3)}


def balance_run(ep, cls, scenario, seed, params, triggers, replies):
    """밸런스 서버에서 같은 판을 돌린다. replies = 플레이 쪽이 보낸 trigger 응답 params (순서대로)."""
    b = Conn(ep)
    b.rq({"type": "hello", "protocol_version": "1.2", "client": "play_check"})
    msg = {"type": "run_episode", "episode_id": "t5", "class": cls, "scenario": scenario, "seed": seed, "params": params or {}}
    if triggers:
        msg["triggers"] = triggers
    b.send(msg)
    k = 0
    while True:
        m = b.recv()
        if m["type"] == "trigger":
            b.send({"type": "trigger_response", "episode_id": "t5", "index": m["index"], "params": replies[k] if k < len(replies) else None})
            k += 1
            continue
        b.close()
        return m.get("result"), k


def t56(ep, bal):
    print("== T5·T6 전투 인계·동일성")
    c = Conn(ep)
    hello(c)
    # --- set_loadout 검증 (run_episode.params 와 같은 규칙)
    base = {"class": "warrior", "scenario": "forest_wolf_king", "boss": "forest_wolf_king"}
    for name, entry, code in [
        ("모르는 class", dict(base, **{"class": "paladin"}), "unknown_class"),
        ("모르는 scenario", dict(base, scenario="nope"), "unknown_scenario"),
        ("시나리오와 다른 boss", dict(base, boss="default"), "boss_mismatch"),
        ("모르는 param", dict(base, params={"zzz": 1}), "unknown_param"),
        ("범위 밖 param", dict(base, params={"w_dps": 5}), "param_out_of_range"),
    ]:
        r = c.rq({"type": "set_loadout", "entries": [entry]})
        check("set_loadout %s → %s" % (name, code), r.get("code") == code, r.get("message", ""))
    r = c.rq({"type": "trigger_response", "encounter_id": "enc_1", "index": 0})
    check("전투 밖 trigger_response → bad_request", r.get("code") == "bad_request")

    stall = dict(base, params={"w_burst": 0.0, "w_dps": 0.0}, triggers={"boss_hp_below": [0.75, 0.5, 0.25]}, source="test: 딜 안 함 → 패배")
    r = c.rq({"type": "set_loadout", "persona": "stable", "entries": [stall]})
    check("set_loadout → loadout_ok", r.get("type") == "loadout_ok" and r.get("entries") == 1)
    o = c.rq({"type": "reset", "seed": 5, "class": "warrior"})
    o = prep_potions(c)
    inv0 = {i["id"]: i["count"] for i in o["inventory"]}
    check("T-P 준비: 작은 물약 4개, 퀵슬롯 등록", inv0.get("potion_small") == 4 and o["player"]["quickslots"][0] == "potion_small", str(inv0))
    c.act("move_to", target="portal_forest")
    r = c.act("interact", target="portal_forest", verb="enter")
    check("숲 진입", r["observation"]["player"]["zone"] == "forest")

    # --- T6: move_to 가 어그로 반경을 지나감 → 전투. 전투 중 observe·pilot_note → busy
    c.seq += 1
    c.send({"type": "act", "seq": c.seq, "action": "move_to", "args": {"pos": [0, 0, 32]}})
    order, busy, replies, st, en, res = [], None, [], None, None, None
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
                check("T-N4 전투 중 pilot_note → busy", nb.get("code") == "busy", str(nb))
            replies.append(None)
            c.send({"type": "trigger_response", "encounter_id": m["encounter_id"], "index": m["index"], "params": None})
        elif m["type"] == "combat_ended":
            en = m
        else:
            res = m
            break
    compact = [t for i, t in enumerate(order) if i == 0 or t != order[i - 1]]
    check("순서: combat_started → trigger → (observe=busy) → combat_ended → action_result",
          compact[:3] == ["combat_started", "trigger", "error:busy"] and compact[-2:] == ["combat_ended", "action_result"], str(compact))
    check("combat_started 필드 (seq·encounter·scenario·seed·loadout.matched)",
          st and st["seq"] == c.seq and st["encounter_id"] == "enc_1" and st["scenario"] == "forest_wolf_king" and st["boss"] == "forest_wolf_king"
          and isinstance(st["seed"], int) and st["loadout"]["matched"] is True, json.dumps(st, ensure_ascii=False)[:200])
    check("action_result interrupted(combat)", res.get("status") == "interrupted" and res.get("interrupted_by") == "combat", str(res.get("status")))
    o = res["observation"]
    check("T-P combat_started.potions = {potion_small, available 4, carried 3, cap 3}, start_state",
          st.get("potions") == {"item": "potion_small", "available": 4, "carried": 3, "cap": 3} and st.get("start_state") == "barrier_inventory_potions",
          str(st.get("potions")))
    fs = st.get("field_state") or {}
    check("T-P combat_started.field_state {hp_ratio, resource_ratio, potions, deaths_so_far}",
          fs.get("hp_ratio") == 1.0 and fs.get("potions") == 4 and fs.get("deaths_so_far") == 0 and "resource_ratio" in fs, str(fs))
    used = en["aftermath"].get("potions_used")
    inv1 = {i["id"]: i["count"] for i in o["inventory"]}
    check("T-P aftermath.potions_used = result.consumables_used, 인벤토리에서 차감",
          used == en["result"]["consumables_used"] and inv1.get("potion_small", 0) == 4 - used and ("item_removed" in kinds(o) or used == 0),
          "used=%s inventory=%s" % (used, inv1))
    check("T-P 관찰 events: barrier_restore", "barrier_restore" in kinds(o))
    check("패배 → 체크포인트 부활 (cp_forest), 늑대왕 남아 있음",
          en["result"]["cleared"] is False and en["aftermath"]["respawned_at"] == "cp_forest" and o["player"]["pos"] == [3.0, 0.0, -33.0]
          and "respawned" in kinds(o), "stalled=%s deaths=%s" % (en["result"].get("stalled"), en["result"].get("deaths")))
    check("전투 시간만큼 세계 시간 진행", res["game_seconds"] >= en["result"]["elapsed"], "game_seconds=%s elapsed=%s" % (res["game_seconds"], en["result"]["elapsed"]))
    if bal:
        br, k = balance_run(bal, "warrior", "forest_wolf_king", st["seed"], stall["params"], stall["triggers"], replies)
        check("T5 패배 판: 플레이 result == 밸런스 run_episode result", br == en["result"] and k == len(replies),
              "diff=%s" % ([kk for kk in (br or {}) if br.get(kk) != en["result"].get(kk)]))

    # --- 승리할 때까지 (조우마다 seed 가 달라진다): 학습값 대신 default + 트리거 응답
    normal = dict(base, params={}, triggers={"boss_hp_below": [0.75, 0.5, 0.25]}, source="test: default")
    c.rq({"type": "set_loadout", "entries": [normal]})
    won, n, same, books = False, 0, [], []
    while not won and n < 8:
        n += 1
        c.act("move_to", pos=[0, 0, 8])
        log = []
        r = c.act("engage", responder=responder, log=log, target="wolf_king")
        st = next(m for m in log if m["type"] == "combat_started")
        en = next(m for m in log if m["type"] == "combat_ended")
        sent = [responder(m) for m in log if m["type"] == "trigger"]
        won = en["result"]["cleared"]
        p = st["potions"]
        books.append(p["carried"] == min(p["available"], 3) and en["aftermath"]["potions_used"] == en["result"]["consumables_used"] <= p["carried"])
        if bal and p["carried"] == p["cap"]:
            br, k = balance_run(bal, "warrior", "forest_wolf_king", st["seed"], {}, normal["triggers"], sent)
            same.append(br == en["result"] and k == len(sent))
    check("T-P 조우 %d개 모두 carried = min(보유, cap), potions_used ≤ carried" % n, all(books), str(books))
    check("engage → done, 승리 (%d번째 조우)" % n, won and r.get("status") == "done", str(r.get("status")))
    o = r["observation"]
    check("승리 → 늑대왕 제거·전리품", ent(o, "wolf_king") is None and any(i["id"] == "wolf_fang" for i in o["inventory"]), str(en["aftermath"]))
    if bal:
        check("T5 carried == cap 인 조우 %d개 모두 result 일치 (트리거 응답 포함)" % len(same), all(same), str(same))
    lg = c.rq({"type": "get_log"})
    kinds_log = [e[1] for e in lg["entries"]]
    check("get_log 에 combat_start·trigger·combat_result 기록", all(k in kinds_log for k in ("combat_start", "trigger", "combat_result")))

    # --- 퀵슬롯에 물약이 없으면 물약 0개로 싸운다
    c.rq({"type": "set_loadout", "entries": [stall]})
    c.rq({"type": "reset", "seed": 5, "class": "warrior"})
    c.act("move_to", target="portal_forest")
    c.act("interact", target="portal_forest", verb="enter")
    log = []
    c.act("move_to", pos=[0, 0, 32], log=log, responder=lambda m: None)
    st = next((m for m in log if m["type"] == "combat_started"), {})
    en = next((m for m in log if m["type"] == "combat_ended"), {})
    check("T-P 퀵슬롯 물약 없음 → carried 0, consumables_used 0",
          st.get("potions") == {"item": None, "available": 0, "carried": 0, "cap": 3} and en.get("result", {}).get("consumables_used") == 0
          and en.get("aftermath", {}).get("potions_used") == 0, str(st.get("potions")))
    c.close()


def prep_potions(c):
    """튜토리얼 q_tut_01~04 를 빠르게: 작은 물약 4개 + 퀵슬롯 0 등록. 마지막 관찰 반환."""
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


def tn(ep):
    print("== T-N pilot_note (v0.3)")
    c = Conn(ep)
    hello(c)
    r = note(c, "thought", "reset 전 메모")
    check("T-N4 reset 전 pilot_note → not_reset", r.get("code") == "not_reset", str(r))
    c.rq({"type": "reset", "seed": 7, "class": "warrior"})
    r = note(c, "idea", "모르는 종류")
    check("T-N4 잘못된 kind → bad_request", r.get("code") == "bad_request", str(r))
    r = note(c, "plan", "   ")
    check("T-N4 빈 text → bad_request", r.get("code") == "bad_request", str(r))
    r = c.rq({"type": "pilot_note", "kind": "plan"})
    check("T-N4 text 없음 → bad_request", r.get("code") == "bad_request", str(r))
    o1 = c.rq({"type": "observe"})
    r = note(c, "thought", "촌장에게 먼저 말을 걸어 보자")
    check("pilot_note → pilot_note_ok (seq 그대로)", r == {"type": "pilot_note_ok", "seq": c.seq}, str(r))
    o2 = c.rq({"type": "observe"})
    check("T-N2 observe → pilot_note → observe: seq 말고 같음 (game_time 포함)", strip_seq(o1) == strip_seq(o2) and o2["seq"] == o1["seq"] + 1,
          "game_time %s → %s" % (o1.get("game_time"), o2.get("game_time")))
    h1 = c.rq({"type": "observe", "mode": "hierarchy", "root": "ui", "max_depth": 12})
    note(c, "plan", "인벤토리를 열어 물약을 확인한다")
    note(c, "finding", "경비병 위치를 알려 주는 곳이 없다")
    h2 = c.rq({"type": "observe", "mode": "hierarchy", "root": "ui", "max_depth": 12})
    check("T-N2 메모가 hierarchy 관찰에 안 나옴 (메모 3개 후에도 같은 트리)", strip_seq(h1) == strip_seq(h2) and "QA 플레이어" not in json.dumps(h2, ensure_ascii=False))
    r = click(c, "ui.hud.inventory")
    check("T-N5 패널이 떠 있어도 인벤토리 버튼 ui_click → done (가림 없음)", r.get("status") == "done", "%s %s" % (r.get("reason"), r.get("reason_detail")))
    sc = json.dumps(r["observation"]["screen"], ensure_ascii=False)
    check("T-N5 screen.ui 에 메모 없음", "경비병 위치" not in sc and "촌장에게 먼저" not in sc)
    long = "가" * 260
    r = note(c, "thought", long)
    lg = c.rq({"type": "get_log"})
    pn = [e for e in lg["entries"] if e[1] == "pilot_note"]
    check("T-N3 get_log 에 pilot_note {kind,text} 4개", [e[2]["kind"] for e in pn] == ["thought", "plan", "finding", "thought"]
          and pn[0][2] == {"kind": "thought", "text": "촌장에게 먼저 말을 걸어 보자"}, str([e[2] for e in pn][:3]))
    check("T-N3 max_chars 초과 → 200자로 잘림(…)", r.get("type") == "pilot_note_ok" and len(pn[-1][2]["text"]) == 200 and pn[-1][2]["text"].endswith("…"))
    r = note(c, "plan", "줄\n바꿈은  공백으로")
    lg = c.rq({"type": "get_log"})
    check("메모는 한 줄 (줄바꿈·연속 공백 → 공백 하나)", lg["entries"][-1][2]["text"] == "줄 바꿈은 공백으로", lg["entries"][-1][2]["text"])
    c.close()


def scripted_run(ep, seed=11, notes=False):
    """퀘스트·UI·이동·채집·전투(트리거 포함)를 섞은 고정 행동열. (get_log 항목, 마지막 관찰, 첫 관찰) 반환.
    notes=True 면 행동 사이사이에 pilot_note 를 끼운다 (T-N3: 로그에서 pilot_note 를 빼면 없는 판과 같아야 함)."""
    c = Conn(ep)
    hello(c)
    nt = (lambda k, t: c.rq({"type": "pilot_note", "kind": k, "text": t})) if notes else (lambda k, t: None)   # seq 를 쓰지 않음 (act seq 가 같아야 비교 가능)
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
    c.act("move_to", pos=[0, 0, 32], responder=responder)      # 어그로 → 전투 1
    c.act("move_to", pos=[0, 0, 8])
    c.act("engage", target="wolf_king", responder=responder)   # 전투 2
    last = c.rq({"type": "observe"})
    lg = c.rq({"type": "get_log"})
    again = c.rq({"type": "reset", "seed": seed, "class": "warrior"})
    c.close()
    return lg["entries"], last, first, again


def strip_seq(o):
    o = json.loads(json.dumps(o))
    o.pop("seq", None)
    return o


def t78(ep, ep2, bal):
    print("== T7 결정성 · T8 새 게임")
    a = scripted_run(ep)
    b = scripted_run(ep)
    nc = sum(1 for e in a[0] if e[1] == "combat_result")
    check("T7 같은 인스턴스 2회: get_log 동일 (%d항목, 전투 %d회)" % (len(a[0]), nc), a[0] == b[0] and nc >= 1)
    check("T7 마지막 관찰 동일", strip_seq(a[1]) == strip_seq(b[1]))
    n = scripted_run(ep, notes=True)
    check("T-N3 같은 행동열 + 메모 4개: 로그에서 pilot_note 를 빼면 메모 없는 판과 같음",
          no_notes(n[0]) == a[0] and len(n[0]) - len(a[0]) == 4 and strip_seq(n[1]) == strip_seq(a[1]),
          "항목 %d vs %d" % (len(n[0]), len(a[0])))
    c3 = scripted_run(ep, seed=12)
    check("T7 다른 seed → 전투 결과가 달라짐", [e for e in c3[0] if e[1] == "combat_result"] != [e for e in a[0] if e[1] == "combat_result"])
    if ep2:
        d = scripted_run(ep2)
        diff = next((i for i, (x, y) in enumerate(zip(a[0], d[0])) if x != y), None)
        check("T7 다른 인스턴스(%s)와도 get_log 동일" % ep2, a[0] == d[0], "첫 차이 #%s" % diff)
    check("T8 진행 후 reset → 첫 장면과 같은 관찰 (seq 제외)", strip_seq(a[2]) == strip_seq(a[3]),
          "gold=%s zone=%s" % (a[3]["player"]["gold"], a[3]["player"]["zone"]))
    if bal:
        b2 = Conn(bal)
        r = b2.rq({"type": "reset", "seed": 1})
        r2 = b2.rq({"type": "play_describe"})
        check("T8 밸런스 인스턴스는 플레이 메시지를 모름 (reset·play_describe → unknown_type)",
              r.get("code") == "unknown_type" and r2.get("code") == "unknown_type")
        b2.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="127.0.0.1:7800")
    ap.add_argument("--omni", default=None, help="-qaPlayOmniscient 로 띄운 인스턴스")
    ap.add_argument("--balance", default=None, help="같은 빌드의 밸런스 모드 인스턴스 (T5 비교·T8)")
    ap.add_argument("--game2", default=None, help="T7 교차 비교용 두 번째 플레이 인스턴스 (예: 헤드리스)")
    a = ap.parse_args()
    t2(a.game)
    t3(a.game, a.omni)
    t4(a.game)
    t56(a.game, a.balance)
    tn(a.game)
    t78(a.game, a.game2, a.balance)
    n = len(RESULTS)
    print("\n결과: %s (%d/%d)" % ("PASS" if all(RESULTS) else "FAIL", sum(RESULTS), n))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
