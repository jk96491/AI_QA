"""학습 결과(reports/<run>/params.json · policy.json) → set_loadout 항목 + 트리거 응답기.

- CMA-ES 등 고정 파라미터(source.type == "static"): params = source.params, 트리거 없음
- IMPALA(source.type == "impala-actor-critic"): params = source.fixed(판 시작값), triggers = source.thresholds,
  트리거 응답 = ImpalaPolicy (CombatResponder 에 등록)
- 키 = (class, scenario). 같은 키가 두 번 오면 나중 것이 이긴다 (notes 에 기록)

학습 쪽 코드를 import 하지 않고 파일만 읽는다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from play_agent.responder import CombatResponder, ImpalaPolicy

Key = Tuple[str, str]
RESULT_FILES = ("policy.json", "params.json")


@dataclass
class LoadoutEntry:
    cls: str
    scenario: str
    params: Dict[str, float]
    triggers: Optional[List[float]] = None
    trigger_type: str = "boss_hp_below"   # 결과 파일의 trigger_type (게임 describe.triggers.type). 없으면 예전 기본값
    source: str = ""
    method: str = ""
    persona: str = ""
    game_version: str = ""
    policy: Optional[ImpalaPolicy] = None

    @property
    def key(self) -> Key:
        return (self.cls, self.scenario)

    def to_wire(self, boss: Optional[str] = None) -> Dict[str, Any]:
        d: Dict[str, Any] = {"class": self.cls, "scenario": self.scenario, "params": dict(self.params), "source": self.source}
        if boss:
            d["boss"] = boss
        if self.triggers:
            d["triggers"] = {self.trigger_type: list(self.triggers)}
        return d


@dataclass
class LoadoutBuilder:
    entries: Dict[Key, LoadoutEntry] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------ 읽기
    def add_file(self, path: Union[str, Path]) -> LoadoutEntry:
        path = Path(path)
        if path.is_dir():
            for name in RESULT_FILES:
                if (path / name).exists():
                    return self.add_file(path / name)
            raise FileNotFoundError("%s 에 %s 없음" % (path, " / ".join(RESULT_FILES)))
        d = json.loads(path.read_text(encoding="utf-8"))
        entry = self.entry_from_dict(d, label=_label(path))
        if entry.key in self.entries:
            self.notes.append("%s/%s: %s 를 %s 로 덮어씀" % (entry.cls, entry.scenario, self.entries[entry.key].source, entry.source))
        self.entries[entry.key] = entry
        return entry

    @staticmethod
    def entry_from_dict(d: Mapping[str, Any], label: str = "") -> LoadoutEntry:
        src = d.get("source") or {}
        kind = src.get("type")
        method = str(d.get("method", ""))
        common = dict(cls=str(d["class"]), scenario=str(d.get("scenario") or "base"),
                      source="%s (%s)" % (label, method) if label else method, method=method,
                      persona=str(d.get("persona", "")), game_version=str((d.get("game") or {}).get("version", "")),
                      trigger_type=str(d.get("trigger_type") or "boss_hp_below"))
        if kind == "static":
            return LoadoutEntry(params={k: float(v) for k, v in src["params"].items()}, **common)
        if kind == "impala-actor-critic":
            pol = ImpalaPolicy.from_dict(d, label=label)
            return LoadoutEntry(params=dict(pol.fixed), triggers=list(pol.thresholds), policy=pol, **common)
        raise ValueError("%s: 모르는 source.type %r (static / impala-actor-critic 만)" % (label, kind))

    # ------------------------------------------------------------------ 찾기
    @staticmethod
    def find_latest(reports_dir: Union[str, Path], cls: str, scenario: str = "base",
                    method: Optional[str] = None, persona: Optional[str] = None) -> Optional[Path]:
        """reports/ 에서 조건에 맞는 가장 최근 결과 파일 (run_id 는 시각 순)."""
        best = None
        for run in sorted(Path(reports_dir).iterdir()):
            for name in RESULT_FILES:
                f = run / name
                if not f.exists():
                    continue
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if d.get("class") != cls or (d.get("scenario") or "base") != scenario:
                    continue
                if method and d.get("method") != method:
                    continue
                if persona and d.get("persona") != persona:
                    continue
                best = f
        return best

    # ------------------------------------------------------------------ 내보내기
    def check_against(self, description: Mapping[str, Any]) -> List[str]:
        """play_description 과 맞춰 본다: 모르는 class·scenario, 게임 버전 차이, 트리거 관측 키 차이."""
        problems = []
        classes = set(description.get("classes") or [])
        scenarios = {s["name"]: s.get("boss") for s in description.get("scenarios") or []}
        gv = str(description.get("game_version", ""))
        feats = list((description.get("combat") or {}).get("trigger_state_features") or [])
        for e in self.entries.values():
            if classes and e.cls not in classes:
                problems.append("%s/%s: 게임에 class 없음" % e.key)
            if scenarios and e.scenario not in scenarios:
                problems.append("%s/%s: 게임에 scenario 없음" % e.key)
            if gv and e.game_version and e.game_version != gv:
                self.notes.append("%s/%s: 학습 빌드 %s ≠ 플레이 빌드 %s (데이터가 바뀌었으면 다시 학습)" % (e.cls, e.scenario, e.game_version, gv))
            if e.policy is not None and feats and e.policy.state_features != feats:
                problems.append("%s/%s: 정책 관측 키 %s ≠ 게임 trigger_state_features %s" % (e.cls, e.scenario, e.policy.state_features, feats))
        return problems

    def wire_entries(self, description: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
        bosses = {s["name"]: s.get("boss") for s in (description or {}).get("scenarios") or []}
        return [e.to_wire(bosses.get(e.scenario)) for e in self.entries.values()]

    def responder(self) -> CombatResponder:
        r = CombatResponder()
        for e in self.entries.values():
            if e.policy is not None:
                r.add(e.cls, e.scenario, e.policy)
        return r

    def persona(self) -> Optional[str]:
        ps = sorted({e.persona for e in self.entries.values() if e.persona})
        return ",".join(ps) or None


def _label(path: Path) -> str:
    """reports/<run>/params.json → 'reports/<run>'."""
    parts = path.resolve().parts
    if "reports" in parts:
        i = len(parts) - 1 - parts[::-1].index("reports")
        return "/".join(parts[i:-1])
    return str(path.parent)
