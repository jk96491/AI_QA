"""늑대왕 아레나 패턴 연출 캡처 (0.8.0): 창 모드 플레이 인스턴스로 늑대왕과 싸우며 일정 간격으로 창을 캡처한다.
    QaArena.exe -qaPlay -qaPort 7800 -qaPlaySpeed 16 -qaPlayCombatSpeed 6   을 먼저 띄운 뒤
    python unity_game/QaTools~/wk_shots.py <출력 폴더> [간격초=4] [최대장수=30]
"""
import os, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import play_shots_lib as lib
from play_check import Conn, hello

OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else "."
GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
MAXN = int(sys.argv[3]) if len(sys.argv) > 3 else 30
os.makedirs(OUT, exist_ok=True)
c = Conn("127.0.0.1:7800"); hello(c)
c.rq({"type": "reset", "seed": 5, "class": "warrior"})
c.act("move_to", target="portal_forest"); c.act("interact", target="portal_forest", verb="enter")
c.act("move_to", pos=[0, 0, 8])
res = {}
def fight():
    log = []
    res["r"] = c.act("engage", log=log, target="wolf_king")
    res["log"] = log
t = threading.Thread(target=fight); t.start()
i = 0
while t.is_alive() and i < MAXN:
    time.sleep(GAP); i += 1
    lib.shot(OUT, "wk_%02d" % i)
t.join()
en = next(m for m in res["log"] if m["type"] == "combat_ended")
print("cleared", en["result"]["cleared"], "elapsed", en["result"]["elapsed"])
c.close()
