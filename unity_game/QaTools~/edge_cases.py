"""프로토콜 경계 사례 검사 (check-game 이 다루지 않는 오류 처리). 표준 라이브러리만 사용.

    venv\\Scripts\\python.exe unity_game/QaTools~/edge_cases.py --game 127.0.0.1:7777

참조 구현(game_sim)과 비교하려면 `python -m game_sim serve --port 7790` 후 --game 127.0.0.1:7790.
폴더 이름 끝의 '~' 는 Unity 가 임포트하지 않게 하기 위함.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time

TIMEOUT = 30.0


class Conn:
    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.create_connection((host, port), timeout=TIMEOUT)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.f = self.sock.makefile("rwb")

    def raw(self, line: bytes) -> None:
        self.f.write(line)
        self.f.flush()

    def send(self, msg) -> None:
        self.raw((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))

    def recv(self):
        line = self.f.readline()
        if not line:
            return None
        return json.loads(line.decode("utf-8"))

    def rq(self, msg):
        self.send(msg)
        return self.recv()

    def close(self) -> None:
        # makefile() 이 열려 있으면 sock.close() 만으로는 실제로 닫히지 않는다 → shutdown 후 둘 다 닫기
        for fn in (lambda: self.sock.shutdown(socket.SHUT_RDWR), self.f.close, self.sock.close):
            try:
                fn()
            except OSError:
                pass


def ep(eid="e#1", **kw):
    m = {"type": "run_episode", "episode_id": eid, "class": "warrior", "seed": 1}
    m.update(kw)
    return m


class Checker:
    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port
        self.results = []

    def conn(self) -> Conn:
        c = Conn(self.host, self.port)
        r = c.rq({"type": "hello", "protocol_version": "1.1", "client": "edge_cases"})
        assert r and r["type"] == "hello_ok", r
        return c

    def check(self, name: str, fn) -> None:
        try:
            detail = fn() or "ok"
            self.results.append((True, name, detail))
        except Exception as exc:  # noqa: BLE001
            self.results.append((False, name, "%s: %s" % (type(exc).__name__, exc)))

    @staticmethod
    def expect_error(r, code: str, episode_id=None) -> str:
        assert r is not None, "응답 없음 (연결 끊김)"
        assert r.get("type") == "error", "error 기대, %r 받음" % r.get("type")
        assert r.get("code") == code, "code %r 기대, %r 받음 (%s)" % (code, r.get("code"), r.get("message"))
        if episode_id is not None:
            assert r.get("episode_id") == episode_id, "episode_id %r 기대, %r" % (episode_id, r.get("episode_id"))
        return "error(%s) %s" % (code, r.get("message", ""))

    @staticmethod
    def alive(c: Conn) -> None:
        r = c.rq({"type": "describe"})
        assert r and r["type"] == "description", "오류 후 연결이 살아 있지 않음: %r" % (r,)

    def run_triggered_until(self, c: Conn, eid: str, n_good: int):
        """트리거 판을 시작해 n_good 개 트리거에 정상 응답하고 다음 trigger 메시지를 돌려준다."""
        c.send(ep(eid, triggers={"boss_hp_below": [0.75, 0.5, 0.25]}))
        for i in range(n_good):
            t = c.recv()
            assert t and t["type"] == "trigger" and t["index"] == i, t
            c.send({"type": "trigger_response", "episode_id": eid, "index": i, "params": {}})
        t = c.recv()
        assert t and t["type"] == "trigger" and t["index"] == n_good, t
        return t

    # ------------------------------------------------------------------ 검사 목록
    def run_all(self) -> bool:
        c = self.conn()

        def bad_json():
            c.raw(b'{"type": "describe",\n')
            d = self.expect_error(c.recv(), "bad_request")
            self.alive(c)
            return d

        def non_object():
            c.raw(b"[1, 2, 3]\n")
            return self.expect_error(c.recv(), "bad_request")

        def no_type():
            return self.expect_error(c.rq({"hello": 1}), "bad_request")

        def unknown_type():
            return self.expect_error(c.rq({"type": "dance"}), "unknown_type")

        def empty_lines():
            c.raw(b"\n\r\n   \n")
            self.alive(c)

        def crlf():
            c.raw(b'{"type":"describe"}\r\n')
            r = c.recv()
            assert r["type"] == "description", r

        def utf8_bom():
            c.raw(b'\xef\xbb\xbf{"type":"describe"}\n')
            r = c.recv()
            # BOM 은 프로토콜 위반 — 거부하든 받아들이든 연결만 유지하면 된다
            self.alive(c)
            return "응답 type=%s (어느 쪽이든 허용, 연결 유지)" % r.get("type")

        def proto_major():
            return self.expect_error(c.rq({"type": "hello", "protocol_version": "2.0"}), "protocol_version")

        def proto_minor_ok():
            r = c.rq({"type": "hello", "protocol_version": "1.9"})
            assert r["type"] == "hello_ok", r

        def missing_field(key):
            def fn():
                m = ep("mf#" + key)
                m.pop(key)
                return self.expect_error(c.rq(m), "bad_request")
            return fn

        def unknown_class():
            return self.expect_error(c.rq(ep("uc#1", **{"class": "bard"})), "unknown_class", "uc#1")

        def unknown_scenario():
            return self.expect_error(c.rq(ep("us#1", scenario="nope")), "unknown_scenario", "us#1")

        def params_not_object():
            return self.expect_error(c.rq(ep("pn#1", params=[1, 2])), "bad_request", "pn#1")

        def param_not_number():
            return self.expect_error(c.rq(ep("pnn#1", params={"w_dps": "high"})), "bad_request", "pnn#1")

        def param_unknown():
            return self.expect_error(c.rq(ep("pu#1", params={"w_magic": 0.5})), "unknown_param", "pu#1")

        def param_low():
            return self.expect_error(c.rq(ep("pl#1", params={"w_dps": -0.01})), "param_out_of_range", "pl#1")

        def param_high():
            return self.expect_error(c.rq(ep("ph#1", params={"potion_hp": 0.95})), "param_out_of_range", "ph#1")

        def param_edges_ok():
            r = c.rq(ep("pe#1", params={"w_dps": 0.0, "w_burst": 1.0, "min_commit": 3}))
            assert r["type"] == "episode_result", r

        def class_param_isolation():
            # 원거리 전용 kite_distance 는 전사에 없음
            return self.expect_error(c.rq(ep("ci#1", params={"kite_distance": 3.0})), "unknown_param")

        def null_scenario_is_base():
            a = c.rq(ep("ns#1", scenario=None))
            b = c.rq(ep("ns#2", scenario="base"))
            assert a["type"] == b["type"] == "episode_result", (a, b)
            assert a["result"] == b["result"], "scenario null 과 base 결과가 다름"

        def unknown_fields_ignored():
            r = c.rq(ep("uf#1", future_field={"x": 1}))
            assert r["type"] == "episode_result", r

        def record_events():
            r = c.rq(ep("re#1", record_events=True))
            ev = r["result"].get("events")
            assert isinstance(ev, list) and ev, "events 없음"
            r2 = c.rq(ep("re#2"))
            assert "events" not in r2["result"], "record_events 없는데 events 포함"
            return "events %d개" % len(ev)

        def trig_wrong_index():
            self.run_triggered_until(c, "tw#1", 1)
            c.send({"type": "trigger_response", "episode_id": "tw#1", "index": 5, "params": {}})
            d = self.expect_error(c.recv(), "bad_request")
            self.alive(c)
            return d

        def trig_wrong_episode():
            self.run_triggered_until(c, "te#1", 0)
            c.send({"type": "trigger_response", "episode_id": "other", "index": 0})
            d = self.expect_error(c.recv(), "bad_request")
            self.alive(c)
            return d

        def trig_other_message():
            self.run_triggered_until(c, "to#1", 2)
            c.send({"type": "describe"})
            d = self.expect_error(c.recv(), "bad_request")
            self.alive(c)
            return d

        def trig_bad_json():
            self.run_triggered_until(c, "tj#1", 0)
            c.raw(b"{oops\n")
            d = self.expect_error(c.recv(), "bad_request")
            self.alive(c)
            return d

        def trig_param_unknown():
            self.run_triggered_until(c, "tu#1", 1)
            c.send({"type": "trigger_response", "episode_id": "tu#1", "index": 1, "params": {"w_magic": 1}})
            d = self.expect_error(c.recv(), "unknown_param")
            self.alive(c)
            return d

        def trig_param_range():
            self.run_triggered_until(c, "tr#1", 0)
            c.send({"type": "trigger_response", "episode_id": "tr#1", "index": 0, "params": {"w_dps": 2}})
            d = self.expect_error(c.recv(), "param_out_of_range")
            self.alive(c)
            return d

        def trig_partial_override():
            # index 0 에서 w_dps 만 바꾸고 이후 빈 응답 → 처음부터 params={"w_dps":..} 와 같은 결과
            eid = "tp#1"
            c.send(ep(eid, triggers={"boss_hp_below": [0.75, 0.5, 0.25]}, params={"w_burst": 0.3}))
            while True:
                m = c.recv()
                if m["type"] == "trigger":
                    params = {"w_dps": 0.8} if m["index"] == 0 else {}
                    c.send({"type": "trigger_response", "episode_id": eid, "index": m["index"], "params": params})
                else:
                    break
            assert m["type"] == "episode_result", m
            ref = c.rq(ep("tp#2", params={"w_burst": 0.3, "w_dps": 0.8}))
            a, b = dict(m["result"]), dict(ref["result"])
            a.pop("triggers_fired"), b.pop("triggers_fired")
            assert a == b, "부분 덮어쓰기 결과 불일치"
            return "triggers_fired=%d" % m["result"]["triggers_fired"]

        def trig_empty_list():
            r = c.rq(ep("tl#1", triggers={"boss_hp_below": []}))
            assert r["type"] == "episode_result" and r["result"]["triggers_fired"] == 0, r

        def triggers_bad_shape():
            return self.expect_error(c.rq(ep("tb#1", triggers={"boss_hp_below": "half"})), "bad_request")

        for name, fn in [
            ("깨진 JSON → bad_request, 연결 유지", bad_json),
            ("JSON 배열 → bad_request", non_object),
            ("type 없음 → bad_request", no_type),
            ("모르는 type → unknown_type", unknown_type),
            ("빈 줄 무시", empty_lines),
            ("CRLF 줄끝 허용", crlf),
            ("UTF-8 BOM 줄 → 연결 유지", utf8_bom),
            ("hello 주 버전 2.0 → protocol_version", proto_major),
            ("hello 부 버전 1.9 → hello_ok", proto_minor_ok),
            ("run_episode episode_id 누락 → bad_request", missing_field("episode_id")),
            ("run_episode class 누락 → bad_request", missing_field("class")),
            ("run_episode seed 누락 → bad_request", missing_field("seed")),
            ("unknown_class (+episode_id 반환)", unknown_class),
            ("unknown_scenario (+episode_id 반환)", unknown_scenario),
            ("params 배열 → bad_request", params_not_object),
            ("params 값 문자열 → bad_request", param_not_number),
            ("모르는 파라미터 → unknown_param", param_unknown),
            ("하한 밖 → param_out_of_range", param_low),
            ("상한 밖 → param_out_of_range", param_high),
            ("범위 끝값·정수 허용", param_edges_ok),
            ("다른 직업 전용 파라미터 → unknown_param", class_param_isolation),
            ("scenario null = base", null_scenario_is_base),
            ("모르는 요청 필드 무시", unknown_fields_ignored),
            ("record_events", record_events),
            ("트리거 index 불일치 → bad_request, 연결 유지", trig_wrong_index),
            ("트리거 episode_id 불일치 → bad_request", trig_wrong_episode),
            ("트리거 대기 중 다른 메시지 → bad_request", trig_other_message),
            ("트리거 응답 깨진 JSON → bad_request", trig_bad_json),
            ("트리거 응답 모르는 파라미터 → unknown_param", trig_param_unknown),
            ("트리거 응답 범위 밖 → param_out_of_range", trig_param_range),
            ("트리거 응답 부분 덮어쓰기", trig_partial_override),
            ("빈 트리거 목록 = 트리거 없음", trig_empty_list),
            ("triggers 형식 오류 → bad_request", triggers_bad_shape),
        ]:
            self.check(name, fn)
        c.close()

        # ----- 연결 수준 -----
        def disconnect_mid_trigger():
            c1 = self.conn()
            self.run_triggered_until(c1, "dc#1", 1)
            c1.close()   # 트리거 대기 중 끊김
            time.sleep(0.2)
            c2 = self.conn()
            self.alive(c2)
            c2.close()
            return "다음 연결 정상"

        def disconnect_mid_line():
            c1 = self.conn()
            c1.raw(b'{"type":"desc')
            c1.close()
            c2 = self.conn()
            self.alive(c2)
            c2.close()

        def bye_then_reconnect():
            c1 = self.conn()
            c1.send({"type": "bye"})
            assert c1.recv() is None, "bye 후 연결이 닫히지 않음"
            c1.close()
            c2 = self.conn()
            self.alive(c2)
            c2.close()

        def probe_connect():
            # 런처의 포트 확인(접속 후 바로 닫기)이 서버를 망가뜨리지 않는지
            for _ in range(5):
                s = socket.create_connection((self.host, self.port), timeout=TIMEOUT)
                s.close()
            c2 = self.conn()
            self.alive(c2)
            c2.close()

        for name, fn in [
            ("트리거 대기 중 연결 끊김 → 다음 연결 대기", disconnect_mid_trigger),
            ("줄 중간에 연결 끊김 → 다음 연결 대기", disconnect_mid_line),
            ("bye → 연결 닫고 다음 연결 대기", bye_then_reconnect),
            ("포트 확인용 접속·즉시 종료 반복", probe_connect),
        ]:
            self.check(name, fn)

        ok = all(r[0] for r in self.results)
        for passed, name, detail in self.results:
            print("[%s] %s — %s" % ("PASS" if passed else "FAIL", name, detail))
        print("\n결과: %s (%d/%d)" % ("PASS" if ok else "FAIL", sum(r[0] for r in self.results), len(self.results)))
        return ok


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="127.0.0.1:7777")
    a = ap.parse_args()
    host, port = a.game.rsplit(":", 1)
    sys.exit(0 if Checker(host, int(port)).run_all() else 1)


if __name__ == "__main__":
    main()
