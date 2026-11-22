"""퍼블리셔 쪽 정의 (페르소나) 로드·검증. 게임 데이터는 여기 없다 — describe 로 받는다."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Union

from balance_qa.spec.game_info import ClassInfo
from balance_qa.spec.persona import Persona

QA_SPECS_DIR = Path(__file__).resolve().parent.parent.parent / "qa_specs"


class SpecError(ValueError):
    def __init__(self, source: str, problems: List[str]) -> None:
        self.source = source
        self.problems = problems
        super().__init__("%s: %s" % (source, "; ".join(problems)))


class PersonaRepository:
    """qa_specs/personas.json"""

    def __init__(self, root: Union[str, Path] = QA_SPECS_DIR) -> None:
        self.root = Path(root)
        self._personas: Optional[Dict[str, Persona]] = None

    @staticmethod
    def validate(p: Persona) -> List[str]:
        problems: List[str] = []
        for key in ("survival_hp_threshold", "dps_hp_floor"):
            v = getattr(p, key)
            if not (0.0 < v <= 1.0):
                problems.append("%s: %s 는 (0, 1]" % (p.id, key))
        if p.lambda_death < 0 or p.lambda_consumable < 0:
            problems.append("%s: λ 는 0 이상" % p.id)
        if p.fail_penalty < 0:
            problems.append("%s: fail_penalty 는 0 이상" % p.id)
        return problems

    def all(self) -> Dict[str, Persona]:
        if self._personas is None:
            path = self.root / "personas.json"
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            out: Dict[str, Persona] = {}
            problems: List[str] = []
            common_fail = data.get("fail_penalty")
            for d in data["personas"]:
                d = dict(d)
                if common_fail is not None:
                    d.setdefault("fail_penalty", float(common_fail))
                p = Persona.from_dict(d)
                problems += self.validate(p)
                out[p.id] = p
            if problems:
                raise SpecError(str(path), problems)
            self._personas = out
        return self._personas

    def get(self, pid: str) -> Persona:
        personas = self.all()
        if pid not in personas:
            raise KeyError("unknown persona %r (가능: %s)" % (pid, ", ".join(personas)))
        return personas[pid]

    @staticmethod
    def check_against(persona: Persona, info: ClassInfo) -> List[str]:
        """페르소나 설정값이 게임 정의서 파라미터로 존재하고 범위 안인지."""
        problems = []
        for k, v in persona.need_params().items():
            if k not in info.params:
                problems.append("%s: 게임 class %r 에 페르소나 파라미터 %r 없음" % (persona.id, info.name, k))
            elif not (info.params[k].low <= v <= info.params[k].high):
                problems.append("%s: %s=%g 가 게임 범위 밖" % (persona.id, k, v))
        return problems
