"""밸런스 모드 회귀(T1) 스냅샷: 고정 seed·params·트리거 응답으로 episode_result 를 모아 JSON 으로 저장/비교.

  python balance_snapshot.py save <host:port> <out.json>
  python balance_snapshot.py diff <host:port> <baseline.json>      # 하나라도 다르면 exit 1

파이썬 표준 라이브러리만 사용. 플레이 모드 작업 전후 결과가 바이트 단위로 같은지 확인용.
"""
import json
import socket
import sys

CASES = []
for cls in ("warrior", "mage", "archer"):
    for scen in ("base", "patch_boss_fast"):
        for seed in (11, 222, 3333):
            CASES.append({"class": cls, "scenario": scen, "seed": seed, "triggers": False})
    # 트리거 왕복 + 부분 덮어쓰기 응답
    CASES.append({"class": cls, "scenario": "base", "seed": 4444, "triggers": True})


class Conn:
    def __init__(self, ep):
        h, p = ep.rsplit(":", 1)
        self.s = socket.create_connection((h, int(p)), timeout=60)
        self.f = self.s.makefile("rwb")

    def send(self, m):
        self.f.write((json.dumps(m, ensure_ascii=False) + "\n").encode("utf-8"))
        self.f.flush()

    def recv(self):
        line = self.f.readline()
        if not line:
            raise RuntimeError("연결 끊김")
        return json.loads(line.decode("utf-8"))


def run(ep):
    c = Conn(ep)
    c.send({"type": "hello", "protocol_version": "1.2", "client": "balance_snapshot"})
    hello = c.recv()
    out = {"game_version": hello.get("game_version"), "results": []}
    for i, case in enumerate(CASES):
        msg = {"type": "run_episode", "episode_id": "snap#%d" % i, "class": case["class"],
               "scenario": case["scenario"], "seed": case["seed"], "params": {}}
        if case["triggers"]:
            msg["triggers"] = {"boss_hp_below": [0.75, 0.5, 0.25]}
        c.send(msg)
        while True:
            m = c.recv()
            if m["type"] == "trigger":
                # 결정적 응답: index 에 따라 w_survival 을 바꿈
                c.send({"type": "trigger_response", "episode_id": m["episode_id"], "index": m["index"],
                        "params": {"w_survival": round(0.3 + 0.15 * m["index"], 3)}})
                continue
            if m["type"] != "episode_result":
                raise RuntimeError("예상 밖 메시지: %s" % m)
            out["results"].append({"case": case, "result": m["result"]})
            break
    c.send({"type": "bye"})
    return out


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("save", "diff"):
        print(__doc__)
        sys.exit(2)
    cmd, ep, path = sys.argv[1:]
    cur = run(ep)
    if cmd == "save":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, sort_keys=True, indent=1)
        print("saved %d results (game %s) -> %s" % (len(cur["results"]), cur["game_version"], path))
        return
    with open(path, encoding="utf-8") as f:
        base = json.load(f)
    bad = 0
    for a, b in zip(base["results"], cur["results"]):
        if json.dumps(a["result"], sort_keys=True) != json.dumps(b["result"], sort_keys=True):
            bad += 1
            diffk = [k for k in a["result"] if a["result"].get(k) != b["result"].get(k)]
            print("DIFF", a["case"], diffk)
    n = len(base["results"])
    print("T1 snapshot: %d/%d identical (baseline %s, now %s)" % (n - bad, n, base["game_version"], cur["game_version"]))
    sys.exit(1 if bad or len(cur["results"]) != n else 0)


if __name__ == "__main__":
    main()
