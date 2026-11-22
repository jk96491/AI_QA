"""하네스(7791)에 직접 판을 돌려 stable(θ.8 φ.7) 클리어율로 파라미터를 탐색한다.

python retune.py search <cls> [n_cand] [n_ep]        무작위 탐색 → 상위 결과
python retune.py eval   <cls> '<json params>' [n_ep]   한 조합 평가
python retune.py blend  <cls> '<json best>' [target] [n_ep]   default↔best 섞는 비율 이분 탐색
"""
import json, random, socket, sys

PERSONA = {"survival_hp_threshold": 0.8, "dps_hp_floor": 0.7}
SEED0 = 3_000_000


class G:
    def __init__(self, port=7791):
        s = socket.create_connection(("127.0.0.1", port))
        self.f = s.makefile("rwb")
        self.rq({"type": "hello", "protocol_version": "1.2"})
        self.desc = self.rq({"type": "describe"})

    def rq(self, m):
        self.f.write((json.dumps(m) + "\n").encode()); self.f.flush()
        return json.loads(self.f.readline())

    def params(self, cls):
        return next(c for c in self.desc["classes"] if c["name"] == cls)["params"]

    def eval(self, cls, p, n, seed0=SEED0):
        q = dict(p); q.update(PERSONA)
        clr = st = dth = 0; t = 0.0
        for i in range(n):
            r = self.rq({"type": "run_episode", "episode_id": "r#%d" % i, "class": cls, "seed": seed0 + i, "params": q})["result"]
            clr += r["cleared"]; st += r["stalled"]; dth += r["deaths"]; t += r["elapsed"]
        return clr / n, st / n, dth / n, t / n


def bt_params(g, cls):
    return [p for p in g.params(cls) if p["group"] == "bt"]


def defaults(g, cls):
    return {p["name"]: p["default"] for p in bt_params(g, cls)}


def main():
    g = G()
    cmd, cls = sys.argv[1], sys.argv[2]
    if cmd == "search":
        nc = int(sys.argv[3]) if len(sys.argv) > 3 else 200
        ne = int(sys.argv[4]) if len(sys.argv) > 4 else 40
        rnd = random.Random(1)
        res = []
        for k in range(nc):
            p = {d["name"]: round(rnd.uniform(*d["range"]), 3) for d in bt_params(g, cls)}
            c, s, dd, t = g.eval(cls, p, ne)
            res.append((c, -s, p, s, dd, t))
        res.sort(key=lambda x: (x[0], x[1]), reverse=True)
        for c, _, p, s, dd, t in res[:6]:
            print("clear=%.2f stalled=%.2f deaths=%.2f t=%.0f %s" % (c, s, dd, t, json.dumps(p)))
        print("default:", g.eval(cls, defaults(g, cls), ne))
    elif cmd == "eval":
        p = json.loads(sys.argv[3]); ne = int(sys.argv[4]) if len(sys.argv) > 4 else 300
        print("clear=%.3f stalled=%.3f deaths=%.2f t=%.0f" % g.eval(cls, p, ne))
    elif cmd == "blend":
        best = json.loads(sys.argv[3])
        target = float(sys.argv[4]) if len(sys.argv) > 4 else 0.6
        ne = int(sys.argv[5]) if len(sys.argv) > 5 else 300
        d0 = defaults(g, cls)
        lo, hi = 0.0, 1.0
        def mix(a):
            return {k: round(d0[k] + (best[k] - d0[k]) * a, 2) for k in d0}
        for _ in range(9):
            mid = (lo + hi) / 2
            c = g.eval(cls, mix(mid), ne)[0]
            print("alpha=%.3f clear=%.3f" % (mid, c))
            if c < target: lo = mid
            else: hi = mid
        a = (lo + hi) / 2
        p = mix(a)
        print("RESULT alpha=%.3f %s" % (a, json.dumps(p)))
        print("check: clear=%.3f stalled=%.3f deaths=%.2f t=%.0f" % g.eval(cls, p, ne, seed0=SEED0 + 50_000))


if __name__ == "__main__":
    main()
