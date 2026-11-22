"""게임 데이터(직업·보스·시나리오) 저장소와 검증기. 게임 서버 기동 시 한 번 검사한다."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from game_sim.spec.boss_spec import BossSpec
from game_sim.spec.class_spec import ClassSpec
from game_sim.spec.scenario import Scenario
from game_sim.spec.param import PARAM_GROUPS
from game_sim.spec.skill_def import SkillRole

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 모든 직업 BT가 공통으로 요구하는 파라미터
REQUIRED_CLASS_PARAMS = (
    "survival_hp_threshold",
    "dps_hp_floor",
    "w_burst",
    "w_dps",
    "w_survival",
    "potion_hp",
    "resource_reserve",
    "min_commit",
)
RANGED_REQUIRED_PARAMS = ("kite_distance",)


class SpecError(ValueError):
    def __init__(self, source: str, problems: List[str]) -> None:
        self.source = source
        self.problems = problems
        super().__init__("%s: %s" % (source, "; ".join(problems)))


class SpecValidator:
    """정의서 규격 검사. 문제를 모아 한 번에 반려한다."""

    def validate_class(self, spec: ClassSpec) -> List[str]:
        problems: List[str] = []
        for key in REQUIRED_CLASS_PARAMS:
            if key not in spec.params:
                problems.append("필수 파라미터 누락: %s" % key)
        if spec.ranged:
            for key in RANGED_REQUIRED_PARAMS:
                if key not in spec.params:
                    problems.append("원거리 필수 파라미터 누락: %s" % key)
        for p in spec.params.values():
            if p.low >= p.high:
                problems.append("%s: range 하한 >= 상한" % p.name)
            elif not (p.low <= p.default <= p.high):
                problems.append("%s: default %.3f 가 범위 밖" % (p.name, p.default))
        for p in spec.params.values():
            if p.group not in PARAM_GROUPS:
                problems.append("%s: group 은 %s 중 하나" % (p.name, PARAM_GROUPS))
        n_opt = sum(1 for p in spec.params.values() if p.optimize)
        if not (1 <= n_opt <= 20):
            problems.append("최적화 파라미터 수 %d (권장 5~20)" % n_opt)
        if not spec.skills_by_role(SkillRole.BASIC):
            problems.append("basic 역할 스킬이 최소 1개 필요")
        names = [s.name for s in spec.skills]
        if len(names) != len(set(names)):
            problems.append("스킬 이름 중복")
        for s in spec.skills:
            if s.damage < 0 or s.cooldown < 0 or s.cost < 0 or s.cast_time < 0:
                problems.append("%s: 음수 수치" % s.name)
            if s.cost > spec.stats.max_resource:
                problems.append("%s: 비용이 최대 자원보다 큼" % s.name)
        if not (0.0 <= spec.stats.armor < 1.0):
            problems.append("armor 는 [0, 1)")
        return problems

    def validate_boss(self, spec: BossSpec) -> List[str]:
        problems: List[str] = []
        n = len(spec.phase_thresholds)
        if list(spec.phase_thresholds) != sorted(spec.phase_thresholds, reverse=True):
            problems.append("phase_thresholds 는 내림차순")
        if len(spec.phase_damage_mult) != n + 1 or len(spec.phase_speed_mult) != n + 1:
            problems.append("phase_*_mult 길이는 phase_thresholds + 1")
        if spec.gimmick_window <= 0:
            problems.append("gimmick_window > 0 필요")
        return problems


class SpecRepository:
    """specs/ 폴더의 JSON 정의서를 로드·검증·캐시한다.

    game_sim/data/
      classes/<name>.json
      bosses/<name>.json
      scenarios.json
    """

    def __init__(self, root: Union[str, Path] = DATA_DIR, validator: Optional[SpecValidator] = None) -> None:
        self.root = Path(root)
        self.validator = validator or SpecValidator()
        self._classes: Dict[str, ClassSpec] = {}
        self._bosses: Dict[str, BossSpec] = {}
        self._scenarios: Optional[Dict[str, Scenario]] = None

    @staticmethod
    def _read(path: Path) -> Any:
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    # ----- 직업 -----
    def class_names(self) -> List[str]:
        return sorted(p.stem for p in (self.root / "classes").glob("*.json"))

    def load_class(self, name: str) -> ClassSpec:
        if name not in self._classes:
            path = self.root / "classes" / ("%s.json" % name)
            spec = ClassSpec.from_dict(self._read(path))
            problems = self.validator.validate_class(spec)
            if problems:
                raise SpecError(str(path), problems)
            self._classes[name] = spec
        return self._classes[name]

    # ----- 보스 -----
    def load_boss(self, name: str = "default") -> BossSpec:
        if name not in self._bosses:
            path = self.root / "bosses" / ("%s.json" % name)
            spec = BossSpec.from_dict(self._read(path))
            problems = self.validator.validate_boss(spec)
            if problems:
                raise SpecError(str(path), problems)
            self._bosses[name] = spec
        return self._bosses[name]

    # ----- 시나리오 -----
    def scenarios(self) -> Dict[str, Scenario]:
        if self._scenarios is None:
            data = self._read(self.root / "scenarios.json")
            self._scenarios = {k: Scenario.from_dict(k, v) for k, v in data["scenarios"].items()}
        return self._scenarios

    def boss_for(self, scenario: Optional[str] = None) -> BossSpec:
        if not scenario or scenario == "base":
            return self.load_boss("default")
        sc = self.scenarios()[scenario]
        return sc.apply(self.load_boss(sc.boss))

    def validate_all(self) -> None:
        """서버 기동 시 전체 데이터 검사 (문제가 있으면 SpecError)."""
        for name in self.class_names():
            self.load_class(name)
        for sc in self.scenarios():
            self.boss_for(sc)
