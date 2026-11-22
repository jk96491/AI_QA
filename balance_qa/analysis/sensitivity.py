"""민감도 분석 (문서 6장: 어떤 값을 열지는 데이터로 결정).

OAT(One-At-a-Time): 기준 파라미터에서 하나씩 범위 전체를 흔들어 결과 변화를 측정.
상호작용은 보지 못하므로, 상위 파라미터 선별(스크리닝) 용도로 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence

import numpy as np

from balance_qa.analysis.evaluator import Evaluator
from balance_qa.control.param_source import StaticParamSource
from balance_qa.reward.reward import RewardFunction
from balance_qa.spec.param import ParamSpace


@dataclass
class SensitivityRow:
    param: str
    values: List[float]
    mean_time: List[float]
    mean_reward: List[float]
    time_range: float        # max - min (초)
    time_range_pct: float    # 기준 시간 대비 %
    best_value: float

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class OATSensitivity:
    def __init__(self, evaluator: Evaluator) -> None:
        self.evaluator = evaluator

    def run(
        self,
        class_name: str,
        scenario: str,
        base_params: Mapping[str, float],
        space: ParamSpace,
        reward_fn: RewardFunction,
        seeds: Sequence[int],
        levels: int = 5,
    ) -> List[SensitivityRow]:
        base = dict(base_params)
        base_summary = self.evaluator.evaluate("base", class_name, scenario, StaticParamSource(base), seeds, reward_fn)
        base_time = base_summary.effective_time.estimate
        rows: List[SensitivityRow] = []
        for d in space.defs:
            values = list(np.linspace(d.low, d.high, levels))
            times, rewards = [], []
            for v in values:
                params = dict(base)
                params[d.name] = float(v)
                s = self.evaluator.evaluate(
                    "%s=%.3f" % (d.name, v), class_name, scenario, StaticParamSource(params), seeds, reward_fn
                )
                times.append(s.effective_time.estimate)
                rewards.append(s.reward.estimate)
            rng = float(max(times) - min(times))
            rows.append(
                SensitivityRow(
                    param=d.name,
                    values=[round(float(v), 4) for v in values],
                    mean_time=[round(t, 2) for t in times],
                    mean_reward=[round(r, 4) for r in rewards],
                    time_range=round(rng, 2),
                    time_range_pct=round(100.0 * rng / base_time, 2),
                    best_value=round(float(values[int(np.argmax(rewards))]), 4),
                )
            )
        rows.sort(key=lambda r: -r.time_range)
        return rows

    def patch_effects(
        self,
        class_name: str,
        scenarios: Sequence[str],
        params: Mapping[str, float],
        reward_fn: RewardFunction,
        seeds: Sequence[int],
        base_key: str = "base",
    ) -> Dict[str, float]:
        """같은 파라미터로 패치 시나리오별 평균 소요 시간 변화율(%)."""
        times = {
            name: self.evaluator.evaluate(name, class_name, name, StaticParamSource(params), seeds, reward_fn)
            .effective_time.estimate
            for name in scenarios
        }
        base = times[base_key]
        return {k: round(100.0 * (v - base) / base, 2) for k, v in times.items()}
