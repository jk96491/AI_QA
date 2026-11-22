"""게임 프로토콜 적합성 검사.

Unity 빌드(또는 어떤 게임 구현)든 이 검사를 통과하면 학습 플랫폼에 붙일 수 있다.

    python -m balance_qa check-game --game 127.0.0.1:7777
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional

from balance_qa.control.param_source import ParamSource, StaticParamSource
from balance_qa.core.types import EpisodeResult, GameError, TriggerState
from balance_qa.game_api import protocol as P
from balance_qa.game_api.client import EpisodeRequest, GameClient
from balance_qa.spec.game_info import GameDescription

CHECK_SEED = 424242


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    required: bool = True

    def line(self) -> str:
        mark = "PASS" if self.passed else ("FAIL" if self.required else "WARN")
        return "[%s] %s%s" % (mark, self.name, (" — " + self.detail) if self.detail else "")


class _RecordingSource(ParamSource):
    """트리거를 기록하고, 지정한 파라미터로 응답."""

    def __init__(self, base: dict, thresholds, reply: dict) -> None:
        self.base = dict(base)
        self.trigger_thresholds = tuple(thresholds)
        self.reply = dict(reply)
        self.seen: List[TriggerState] = []

    def base_params(self):
        return dict(self.base)

    def on_trigger(self, state: TriggerState):
        self.seen.append(state)
        return dict(self.reply)


class ConformanceChecker:
    def __init__(self, client: GameClient) -> None:
        self.client = client
        self.results: List[CheckResult] = []
        self.desc: Optional[GameDescription] = None

    def _check(self, name: str, fn: Callable[[], str], required: bool = True) -> bool:
        try:
            detail = fn() or ""
            self.results.append(CheckResult(name, True, detail, required))
            return True
        except Exception as exc:  # 검사 실패 내용 기록
            self.results.append(CheckResult(name, False, "%s: %s" % (type(exc).__name__, exc), required))
            return False

    def _expect_error(self, code: str, req: EpisodeRequest, source: ParamSource) -> str:
        try:
            self.client.run_episode(req, source)
        except GameError as exc:
            if exc.code != code:
                raise AssertionError("error code %r 기대, %r 받음" % (code, exc.code))
            return "error(%s)" % code
        raise AssertionError("error(%s) 를 기대했으나 정상 결과" % code)

    def run(self) -> List[CheckResult]:
        c = self.client
        if not self._check("connect + hello", lambda: (c.connect(), "protocol %s" % c.hello_info.get("protocol_version"))[1]):
            return self.results

        def describe() -> str:
            self.desc = c.describe(refresh=True)
            d = self.desc
            assert d.classes, "classes 비어 있음"
            assert "base" in d.scenarios, "scenario 'base' 필수"
            assert d.state_features, "triggers.state_features 비어 있음"
            for info in d.classes.values():
                for p in info.params.values():
                    assert p.low < p.high and p.low <= p.default <= p.high, "%s.%s 범위/기본값 오류" % (info.name, p.name)
            return "game=%s %s, classes=%s" % (d.game, d.game_version, list(d.classes))

        if not self._check("describe 형식", describe):
            return self.results
        d = self.desc
        assert d is not None
        cls = next(iter(d.classes))
        defaults = d.classes[cls].default_params()

        results: List[EpisodeResult] = []

        def static_episode() -> str:
            r = c.run_episode(EpisodeRequest(cls, CHECK_SEED), StaticParamSource({}))
            results.append(r)
            assert r.seed == CHECK_SEED, "result.seed 가 요청 seed 와 다름"
            assert r.elapsed > 0 and r.elapsed <= d.time_limit + 1e-6, "elapsed 범위 이상: %s" % r.elapsed
            assert 0.0 <= r.boss_hp_remaining <= 1.0, "boss_hp_remaining 는 0~1"
            assert (r.clear_time is not None) == r.cleared, "cleared 와 clear_time 불일치"
            assert r.triggers_fired == 0, "트리거를 요청하지 않았는데 triggers_fired=%d" % r.triggers_fired
            return "cleared=%s elapsed=%.1f deaths=%d" % (r.cleared, r.elapsed, r.deaths)

        self._check("run_episode (기본 파라미터)", static_episode)

        def full_params() -> str:
            r = c.run_episode(EpisodeRequest(cls, CHECK_SEED), StaticParamSource(defaults))
            if results:
                assert r.to_dict() == results[0].to_dict(), "정의서 default 를 명시해도 결과가 같아야 함"
            return "ok"

        self._check("params 생략 = 정의서 default", full_params)

        def determinism() -> str:
            a = c.run_episode(EpisodeRequest(cls, CHECK_SEED + 1), StaticParamSource(defaults)).to_dict()
            b = c.run_episode(EpisodeRequest(cls, CHECK_SEED + 1), StaticParamSource(defaults)).to_dict()
            assert a == b, "같은 seed·params 인데 결과가 다름"
            return "동일"

        self._check("시드 결정성", determinism)

        def seed_variation() -> str:
            times = {c.run_episode(EpisodeRequest(cls, CHECK_SEED + 10 + i), StaticParamSource(defaults)).elapsed for i in range(4)}
            assert len(times) > 1, "seed 가 달라도 결과가 모두 같음 (난수가 seed 를 안 쓰는지 확인)"
            return "%d가지" % len(times)

        self._check("seed 에 따른 변동", seed_variation, required=False)

        def triggers() -> str:
            thresholds = sorted(d.trigger_supported, reverse=True) or [0.5]
            bt_params = [p for p in d.classes[cls].params.values() if p.group == "bt"]
            reply = {bt_params[0].name: bt_params[0].default} if bt_params else {}
            src = _RecordingSource({}, thresholds, reply)
            r = c.run_episode(EpisodeRequest(cls, CHECK_SEED), src)
            idx = [s.index for s in src.seen]
            assert idx and idx[0] == 0, "첫 트리거는 index 0 (판 시작) 이어야 함: %s" % idx
            assert idx == list(range(len(idx))), "index 는 0,1,2,... 연속: %s" % idx
            assert len(idx) <= len(thresholds) + 1, "트리거 횟수 초과: %s" % idx
            assert r.triggers_fired == len(idx), "result.triggers_fired(%d) != 받은 트리거 수(%d)" % (r.triggers_fired, len(idx))
            for s in src.seen:
                missing = [f for f in d.state_features if f not in s.state]
                assert not missing, "trigger.state 에 %s 없음" % missing
                if d.totals_fields:
                    miss_t = [f for f in d.totals_fields if f not in s.totals]
                    assert not miss_t, "trigger.totals 에 %s 없음" % miss_t
                bad = {k: v for k, v in s.state.items() if not (isinstance(v, (int, float)) and math.isfinite(v))}
                assert not bad, "state 값이 숫자가 아님: %s" % bad
            if r.cleared:
                assert len(idx) == len(thresholds) + 1, "클리어했는데 모든 경계 트리거를 받지 못함: %s" % idx
            return "index=%s" % idx

        self._check("결정 트리거 왕복", triggers)

        def totals() -> str:
            assert d.supports_segment_rewards, "describe.triggers.totals 에 %s 필요 (v1.1, IMPALA 구간 보상)" % (d.REQUIRED_TOTALS,)
            src = _RecordingSource({}, sorted(d.trigger_supported, reverse=True) or [0.5], {})
            r = c.run_episode(EpisodeRequest(cls, CHECK_SEED + 2), src)
            el = [float(s.totals["elapsed"]) for s in src.seen]
            assert el[0] <= 1e-6, "index 0 의 elapsed 는 0 이어야 함: %s" % el[0]
            assert el == sorted(el), "elapsed 가 단조 증가하지 않음: %s" % el
            assert el[-1] <= r.elapsed + 1e-6, "마지막 트리거 elapsed > result.elapsed"
            for key in ("deaths", "consumables_used"):
                seq = [float(s.totals[key]) for s in src.seen] + [float(getattr(r, key))]
                assert seq == sorted(seq), "%s 누적값이 감소함: %s" % (key, seq)
            return "elapsed=%s" % el

        self._check("trigger.totals 누적값 (v1.1, IMPALA 용)", totals, required=False)

        def stalled_field() -> str:
            raw = {}

            def tap(direction, msg):
                if direction == "recv" and msg.get("type") == P.EPISODE_RESULT:
                    raw.update(msg.get("result", {}))

            c.tap = tap
            try:
                r = c.run_episode(EpisodeRequest(cls, CHECK_SEED + 3), StaticParamSource({}))
            finally:
                c.tap = None
            assert "stalled" in raw, ("result.stalled 없음 (v1.2). 멈춘 판을 invalid 로 보내면 학습 쪽이 사유 접두어 "
                                      "'stalled' 로만 구분한다 — docs/PROTOCOL.md 4.5")
            assert isinstance(raw["stalled"], bool), "result.stalled 는 bool"
            if raw["stalled"]:
                assert not raw.get("cleared") and not raw.get("invalid"), "stalled 판은 cleared=false, invalid=false"
            return "stalled=%s" % r.stalled

        self._check("result.stalled 필드 (v1.2, 멈춘 판 = 실패)", stalled_field, required=False)

        self._check("unknown_param 오류", lambda: self._expect_error(
            "unknown_param", EpisodeRequest(cls, 1), StaticParamSource({"__no_such_param__": 1.0})))
        p0 = next(iter(d.classes[cls].params.values()))
        self._check("param_out_of_range 오류", lambda: self._expect_error(
            "param_out_of_range", EpisodeRequest(cls, 1), StaticParamSource({p0.name: p0.high + abs(p0.span) + 1})))
        self._check("unknown_class 오류", lambda: self._expect_error(
            "unknown_class", EpisodeRequest("__no_such_class__", 1), StaticParamSource({})))
        self._check("unknown_scenario 오류", lambda: self._expect_error(
            "unknown_scenario", EpisodeRequest(cls, 1, scenario="__no_such_scenario__"), StaticParamSource({})))

        def alive_after_errors() -> str:
            c.run_episode(EpisodeRequest(cls, 2), StaticParamSource({}))
            return "오류 후에도 같은 연결로 계속 사용 가능"

        self._check("오류 후 연결 유지", alive_after_errors)

        def scenarios() -> str:
            for sc in d.scenarios:
                c.run_episode(EpisodeRequest(cls, 3, scenario=sc), StaticParamSource({}))
            return "%d개" % len(d.scenarios)

        self._check("모든 scenario 실행", scenarios)
        return self.results

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results if r.required)
