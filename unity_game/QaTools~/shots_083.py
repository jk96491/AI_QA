"""0.8.3 화면 겹침 확인 (H1·H3·H4): 창 모드 플레이 인스턴스를 몰고 가며 캡처.
    QaArena.exe -qaPlay -qaPort 7810 -qaPlaySpeed 8 -qaPlayCombatSpeed 30   을 먼저 띄운다.
    python unity_game/QaTools~/shots_083.py <절대 출력 폴더> [port]
"""
import os, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from play_check import Conn, hello, note
from play_shots_lib import shot

OUT = os.path.abspath(sys.argv[1]); os.makedirs(OUT, exist_ok=True)
EP = "127.0.0.1:" + (sys.argv[2] if len(sys.argv) > 2 else "7810")

NOTES = [("thought", "촌장에게 먼저 말을 걸어 의뢰를 받는다. 대화창이 열리면 선택지를 고른다."),
         ("plan", "약초 3개를 모으고 촌장에게 반납, 물약을 퀵슬롯에 등록한 뒤 숲으로 간다."),
         ("observation", "HUD 퀵슬롯이 비어 있다. 인벤토리 창에서 등록해야 전투에 물약을 가져간다."),
         ("thought", "늑대왕 전투는 학습된 BT 가 한다. 결과는 combats 로 온다.")]

c = Conn(EP); hello(c)
c.rq({"type": "reset", "seed": 5, "class": "warrior"})
for k, t in NOTES: note(c, k, t)
time.sleep(0.8); shot(OUT, "1_field_panel_bottom")

# H1: 대화창 열린 장면 → 패널은 왼쪽 위
c.act("move_to", target="npc_elder"); c.act("interact", target="npc_elder", verb="talk")
time.sleep(0.8); shot(OUT, "2_dialog_panel_top")
c.act("ui_click", ui_id="ui.dialog.choice.0")
obs = c.act("wait", seconds=0.1)
# 대화가 남아 있으면 닫힐 때까지 첫 선택지
for _ in range(4):
    m = (obs.get("observation") or {}).get("screen", {}).get("modal")
    if m != "dialog": break
    obs = c.act("ui_click", ui_id="ui.dialog.choice.0")

# H1: 인벤토리 창 → 왼쪽 세로 띠
r = c.act("ui_click", ui_id="ui.hud.inventory")
if (r.get("observation") or {}).get("screen", {}).get("modal") == "tip": c.act("ui_click", ui_id="ui.tip.ok")
time.sleep(0.8); shot(OUT, "3_inventory_panel_strip")
c.act("ui_click", ui_id="ui.inventory.close")

# H3·H4: 늑대왕 전투 (로그 = 왼쪽 가운데, QA 패널 = 왼쪽 아래, 스킬 이름 = 슬롯 아래)
c.act("move_to", target="portal_forest"); c.act("interact", target="portal_forest", verb="enter")
c.act("move_to", pos=[0, 0, 8])
note(c, "thought", "늑대왕에게 다가가 전투를 시작한다.")
res = {}
def fight():
    res["r"] = c.act("engage", target="wolf_king")
t = threading.Thread(target=fight); t.start()
for name, wait in [("4_fight_a", 3.0), ("5_fight_b", 5.0), ("6_fight_c", 6.0)]:
    time.sleep(wait); shot(OUT, name)
t.join()
print("engage", res["r"].get("status"), res["r"].get("reason"))
c.close()
