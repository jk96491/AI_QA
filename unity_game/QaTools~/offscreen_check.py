"""0.8.4 OFFSCREEN_TARGET_REQUEST 확인: 퀘스트 목표 대상이 시야 밖이어도 known:"marker" 로 관찰에 있고 move_to(id) 가 된다.
    python unity_game/QaTools~/offscreen_check.py 127.0.0.1:7810
장면 A: 촌장 옆, q_tut_04 수락 직후 → npc_merchant.   장면 B: 늑대왕 처치 뒤 마을 입구 → npc_guard (반납).
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import play_check as pc
from play_check import Conn, hello, check, ent, quest, click, goto

sys.stdout.reconfigure(encoding="utf-8")
EP = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:7810"


def show(o, eid):
    e = ent(o, eid)
    print("   ", eid, json.dumps(e, ensure_ascii=False) if e else None)
    return e


c = Conn(EP); hello(c)
o = c.rq({"type": "reset", "seed": 3, "class": "warrior"})
check("시작: 목표 대상이 아닌 시야 밖 npc_guard 없음, 상인은 마커 아님", ent(o, "npc_guard") is None and (ent(o, "npc_merchant") or {}).get("known") != "marker")
check("시작: q_tut_01 대상 npc_elder 있음", ent(o, "npc_elder") is not None)

# q1·q2 수락
goto(c, "npc_elder"); c.act("interact", target="npc_elder", verb="talk")
click(c, "ui.dialog.choice.0"); r = click(c, "ui.dialog.choice.0")
# 숲에서 약초 3개 (약초 = q_tut_02 목표 대상 → 숲에 들어가면 시야 밖이어도 known:marker)
c.act("move_to", target="portal_forest"); r = c.act("interact", target="portal_forest", verb="enter")
o = r["observation"]
herbs = [e for e in o["entities"] if e["id"].startswith("herb_")]
print("   숲 진입 직후 약초:", [(e["id"], e.get("known"), e.get("hidden")) for e in herbs])
check("숲 진입: 약초(목표 대상)가 관찰에 있음", len(herbs) >= 3)
for h in ["herb_01", "herb_02", "herb_03"]:
    r = c.act("move_to", target=h)
    check("move_to(%s) id 로 바로 done" % h, r.get("status") == "done", str(r.get("reason")))
    c.act("interact", target=h, verb="pickup")
o = c.act("wait", seconds=0.1)["observation"]
check("약초 3개 뒤 남은 herb_04 는 목표 완료라 마커 아님", (ent(o, "herb_04") or {}).get("known") != "marker")
c.act("move_to", target="portal_village"); c.act("interact", target="portal_village", verb="enter")
r = c.act("move_to", target="npc_elder")
check("마을 복귀 → move_to(npc_elder) (반납 대상) done", r.get("status") == "done", str(r.get("reason")))
c.act("interact", target="npc_elder", verb="talk"); click(c, "ui.dialog.choice.0"); click(c, "ui.dialog.choice.0")
# q3 퀵슬롯
click(c, "ui.hud.inventory"); click(c, "ui.tip.ok"); click(c, "ui.inventory.slot.potion_small"); click(c, "ui.inventory.assign")
r = click(c, "ui.inventory.close")
o = r["observation"]

print("== 장면 A: 촌장 옆, q_tut_04 수락 직후")
print("    player.pos", o["player"]["pos"], "quests", [(q["id"], q["state"]) for q in o["quests"]])
m = show(o, "npc_merchant")
check("A: npc_merchant 가 시야 밖이어도 entities 에 known:marker", m is not None and m.get("known") == "marker" and "hidden" not in m)
r = c.act("move_to", target="npc_merchant")
check("A: move_to(npc_merchant) → done (not_visible 아님)", r.get("status") == "done", str(r.get("reason")))
show(r["observation"], "npc_merchant")

# q4 구매 → q5 자동 수락
c.act("interact", target="npc_merchant", verb="talk"); click(c, "ui.dialog.choice.0")
click(c, "ui.shop.buy.potion_small"); click(c, "ui.shop.buy.potion_small"); r = click(c, "ui.shop.close")
o = r["observation"]
check("q_tut_05 active: 반납 대상 npc_guard 는 아직 마커 아님 (처치 전)", (ent(o, "npc_guard") or {}).get("known") != "marker")

# 늑대왕
c.act("move_to", target="portal_forest"); c.act("interact", target="portal_forest", verb="enter")
won, tries = False, 0
while not won and tries < 8:
    tries += 1
    r = c.act("move_to", target="wolf_king")   # 처치 목표 대상 → 시야 밖이어도 id 로 이동 (어그로 → 전투)
    log = []
    if r.get("status") == "done":
        r = c.act("engage", log=log, target="wolf_king")
    en = next((m for m in log if m["type"] == "combat_ended"), None)
    won = bool(en and en["result"].get("cleared")) or (quest(r["observation"], "q_tut_05") or {}).get("state") == "ready"
print("    늑대왕 시도", tries, "처치", won)
check("늑대왕 처치 (q_tut_05 ready)", won)
c.act("move_to", target="portal_village"); r = c.act("interact", target="portal_village", verb="enter")
o = r["observation"]

print("== 장면 B: 마을 입구, 늑대왕 처치 뒤 (q_tut_05 ready)")
print("    player.pos", o["player"]["pos"], "quests", [(q["id"], q["state"]) for q in o["quests"]])
g = show(o, "npc_guard")
check("B: npc_guard 가 시야 밖이어도 entities 에 known:marker (반납 대상)", g is not None and g.get("known") == "marker")
r = c.act("move_to", target="npc_guard")
check("B: move_to(npc_guard) → done", r.get("status") == "done", str(r.get("reason")))
c.close()
print("결과: %s (%d/%d)" % ("PASS" if all(pc.RESULTS) else "FAIL", sum(pc.RESULTS), len(pc.RESULTS)))
