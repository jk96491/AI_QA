"""하네스에 직접 판을 돌려 평균 진단치를 본다. python peek.py [port] [n] [persona θ φ 덮어쓰기 JSON]"""
import json, socket, sys
from collections import Counter, defaultdict

port = int(sys.argv[1]) if len(sys.argv) > 1 else 7791
n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
tp = [float(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else None   # "θ,φ"
extra = {c: {"survival_hp_threshold": tp[0], "dps_hp_floor": tp[1]} for c in ("warrior", "mage", "archer")} if tp else {}
s = socket.create_connection(("127.0.0.1", port)); f = s.makefile("rwb")
def rq(m):
    f.write((json.dumps(m) + "\n").encode()); f.flush(); return json.loads(f.readline())
rq({"type": "hello", "protocol_version": "1.1"})
for cls in ("warrior", "mage", "archer"):
    agg = defaultdict(float); hits = Counter(); dmg = Counter(); moves = Counter(); inval = 0; clr = 0
    for i in range(n):
        r = rq({"type": "run_episode", "episode_id": "p#%d" % i, "class": cls, "seed": 5000 + i,
                "params": extra.get(cls, {}), "record_events": True})["result"]
        clr += r["cleared"]; inval += r["invalid"]
        for k, v in r["block_time"].items(): agg[k] += v / n
        agg["deaths"] += r["deaths"] / n; agg["elapsed"] += r["elapsed"] / n; agg["boss_left"] += r["boss_hp_remaining"] / n
        for t, kind, pl in r["events"]:
            if kind == "hit": hits[pl["kind"]] += 1 / n; dmg[pl["kind"]] += pl["dmg"] / n
            if kind == "boss": moves[pl["move"]] += 1 / n
    print("== %s clear=%.2f invalid=%.2f  %s" % (cls, clr / n, inval / n, {k: round(v, 1) for k, v in agg.items()}))
    print("   boss moves:", {k: round(v, 1) for k, v in moves.items()})
    print("   dmg taken :", {k: round(v) for k, v in dmg.items()})
