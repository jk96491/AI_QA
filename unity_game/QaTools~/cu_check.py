"""플레이 v0.4 raw 입력(비전 없는 computer use) 검사 — T-R. 표준 라이브러리만.
    python cu_check.py --game 127.0.0.1:7800 [--game2 127.0.0.1:7802]
"""
import argparse, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from play_check import Conn, check, RESULTS, ui, ent, kinds, quest, strip_seq


def hello4(c):
    return c.rq({"type": "hello", "protocol": "play", "protocol_version": "0.4", "client": "cu_check"})


def center(r):
    x, y, w, h = r
    return x + w / 2.0, y + h / 2.0


def click_ui(c, obs, uid):
    e = ui(obs, uid)
    if e is None or "rect" not in e:
        return {"status": "missing", "uid": uid}
    x, y = center(e["rect"])
    return c.act("pointer_click", x=x, y=y)


def click_ent(c, obs, eid):
    e = ent(obs, eid)
    if e is None or "screen_pos" not in e:
        return {"status": "missing", "eid": eid}
    x, y = e["screen_pos"]
    return c.act("pointer_click", x=x, y=y)


def scripted(ep):
    """raw 입력만으로: 촌장에게 걸어가 대화·수락, 인벤토리 키, 팝업 가림, esc, wasd, 바닥 클릭."""
    c = Conn(ep); hello4(c)
    o = c.rq({"type": "reset", "seed": 3, "class": "warrior", "input_mode": "raw"})
    r = click_ent(c, o, "npc_elder")            # 멀다 → 다가가기
    r = click_ent(c, r["observation"], "npc_elder")   # 범위 안 → 대화
    o = r["observation"]
    talk = r
    r = click_ui(c, o, "ui.dialog.choice.0"); r = click_ui(c, r["observation"], "ui.dialog.choice.0")   # 맡겨 주세요 → 다녀오겠습니다
    accepted = r
    inv = c.act("key_press", key="i")
    o = inv["observation"]
    blocked = click_ui(c, o, "ui.inventory.slot.potion_small") if ui(o, "ui.inventory.slot.potion_small") else c.act("pointer_click", x=400, y=200)
    esc = c.act("key_press", key="escape")
    esc2 = c.act("key_press", key="escape")
    hold = c.act("key_hold", key="d", seconds=1.0)
    ground = c.act("pointer_click", x=640, y=300)
    lg = c.rq({"type": "get_log"})
    c.close()
    return dict(talk=talk, accepted=accepted, inv=inv, blocked=blocked, esc=esc, esc2=esc2, hold=hold, ground=ground, log=lg["entries"], first=o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="127.0.0.1:7800")
    ap.add_argument("--game2", default=None)
    a = ap.parse_args()
    print("== T-R raw 입력 (v0.4)")
    c = Conn(a.game)
    r = hello4(c)
    check("hello 0.4 → hello_ok 0.4", r.get("type") == "hello_ok" and r.get("protocol_version") == "0.4", str(r.get("protocol_version")))
    d = c.rq({"type": "play_describe"})
    check("describe: input_modes·screen 1280x720·keys·actions_raw",
          d.get("input_modes") == ["semantic", "raw"] and d.get("screen") == {"width": 1280, "height": 720, "origin": "top_left"}
          and len(d.get("keys", [])) >= 7 and [x["name"] for x in d.get("actions_raw", [])][:5] == ["pointer_click", "pointer_move", "drag", "key_press", "key_hold"])
    o = c.rq({"type": "reset", "seed": 3, "class": "warrior", "input_mode": "raw"})
    hud = ui(o, "ui.hud.inventory")
    check("관찰 screen.ui[].rect, entities[].screen_pos", hud is not None and len(hud.get("rect", [])) == 4 and "screen_pos" in (ent(o, "npc_elder") or {}),
          "hud rect=%s" % (hud or {}).get("rect"))
    r = c.act("interact", target="npc_elder", verb="talk")
    check("raw 모드: id 행동(interact) → unknown_action", r.get("code") == "unknown_action", str(r.get("code")))
    r = c.act("move_to", target="npc_elder")
    check("raw 모드: move_to(target) → bad_request", r.get("code") == "bad_request", str(r.get("code")))
    r = c.act("pointer_click", x=1300, y=10)
    check("화면 밖 좌표 → bad_request", r.get("code") == "bad_request")
    r = c.act("key_press", key="z")
    check("모르는 키 → bad_request", r.get("code") == "bad_request")
    r = c.act("text_input", text="hello")
    check("text_input (입력 칸 없음) → failed invalid_state", r.get("status") == "failed" and r.get("reason") == "invalid_state")
    r = c.act("pointer_click", x=5, y=700)
    check("빈 곳 클릭 → done (헛클릭은 오류 아님), hit 필드 있음", r.get("status") == "done" and "hit" in r, "hit=%s" % r.get("hit"))
    c.close()
    c = Conn(a.game)
    c.rq({"type": "hello", "protocol": "play", "protocol_version": "0.3"})
    o = c.rq({"type": "reset", "seed": 3, "class": "warrior"})
    check("0.3 클라이언트: 좌표 없음 (기존 관찰 그대로)", all("rect" not in e for e in o["screen"]["ui"]) and all("screen_pos" not in e for e in o["entities"]))
    r = c.rq({"type": "reset", "seed": 3, "input_mode": "raw"})
    check("0.3 세션에서 input_mode → bad_request", r.get("code") == "bad_request")
    c.close()

    s = scripted(a.game)
    check("촌장 클릭 ×2 → 다가가서 대화 (dialog)", s["talk"].get("status") == "done" and s["talk"]["observation"]["screen"]["modal"] == "dialog",
          "%s %s hit=%s" % (s["talk"].get("status"), s["talk"].get("reason"), s["talk"].get("hit")))
    q2 = quest(s["accepted"]["observation"], "q_tut_02")
    check("선택지 rect 클릭 → q_tut_02 수락", q2 is not None, str(s["accepted"].get("hit")))
    check("key i → 인벤토리 + 안내 팝업", s["inv"]["observation"]["screen"]["modal"] == "tip")
    check("팝업에 가린 곳 클릭 → 팝업이 받음 (hit ui.tip…)", str(s["blocked"].get("hit", "")).startswith("ui.tip") and s["blocked"].get("status") == "done",
          "hit=%s" % s["blocked"].get("hit"))
    check("escape ×2 → 팝업·인벤토리 닫힘", s["esc"]["observation"]["screen"]["modal"] == "inventory" and s["esc2"]["observation"]["screen"]["modal"] is None)
    p0 = s["esc2"]["observation"]["player"]["pos"]; p1 = s["hold"]["observation"]["player"]["pos"]
    check("key_hold d 1초 → +x 로 이동", s["hold"].get("status") == "done" and p1[0] > p0[0] + 3, "%s → %s" % (p0, p1))
    check("바닥 클릭 → 그 점으로 이동", s["ground"].get("status") == "done" and s["ground"]["observation"]["player"]["pos"] != p1, str(s["ground"]["observation"]["player"]["pos"]))
    s2 = scripted(a.game)
    check("결정성: 같은 입력열 2회 → get_log 같음", s["log"] == s2["log"], "%d 항목" % len(s["log"]))
    if a.game2:
        s3 = scripted(a.game2)
        diff = next((i for i, (x, y) in enumerate(zip(s["log"], s3["log"])) if x != y), None)
        check("결정성: 창 ↔ 헤드리스 (%s) get_log 같음" % a.game2, s["log"] == s3["log"], "첫 차이 #%s: %s / %s" % (diff, s["log"][diff] if diff is not None else "", s3["log"][diff] if diff is not None else ""))
    n = len(RESULTS)
    print("\n결과: %s (%d/%d)" % ("PASS" if all(RESULTS) else "FAIL", sum(RESULTS), n))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
