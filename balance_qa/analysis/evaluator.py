"""평가기: 고정된 파라미터(또는 정책)를 평가 시드로 여러 판 돌려 요약 통계를 만든다."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from balance_qa.analysis.stats import Interval, Stats
from balance_qa.control.param_source import ParamSource
from balance_qa.core.types import EpisodeResult
from balance_qa.reward.reward import RewardFunction
from balance_qa.runner.episode_runner import EpisodeJob, EpisodeRunner


@dataclass
class EvaluationSummary:
    label: str
    n: int
    n_valid: int
    clear_rate: Interval
    clear_time: Interval          # 클리어한 판만 (초)
    effective_time: Interval      # 중도절단 포함 (초)
    deaths: Interval
    consumables: Interval
    reward: Interval
    reward_breakdown: Dict[str, float]
    block_share: Dict[str, float]
    segment_time_mean: List[float]
    gimmick_success_rate: float
    stall_rate: Interval
    invalid_ratio: float
    invalid_reasons: Dict[str, int]
    time_cv: float
    raw_effective_times: List[float] = field(default_factory=list, repr=False)
    raw_rewards: List[float] = field(default_factory=list, repr=False)

    def row(self) -> Dict[str, str]:
        return {
            "label": self.label,
            "n": str(self.n_valid),
            "clear_rate": self.clear_rate.fmt(2),
            "clear_time_s": self.clear_time.fmt(1),
            "effective_time_s": self.effective_time.fmt(1),
            "stalled": self.stall_rate.fmt(2),
            "deaths": self.deaths.fmt(2),
            "consumables": self.consumables.fmt(2),
            "reward": self.reward.fmt(3),
        }

    def to_dict(self) -> dict:
        d = {k: (v.as_dict() if isinstance(v, Interval) else v) for k, v in self.__dict__.items()}
        d.pop("raw_effective_times", None)
        d.pop("raw_rewards", None)
        return d


class Evaluator:
    def __init__(self, runner: EpisodeRunner) -> None:
        self.runner = runner

    def run(self, class_name: str, scenario: str, source: ParamSource, seeds: Sequence[int]) -> List[EpisodeResult]:
        return self.runner.run([EpisodeJob(class_name, scenario, s, source) for s in seeds])

    def summarize(self, label: str, results: Sequence[EpisodeResult], reward_fn: RewardFunction) -> EvaluationSummary:
        tl = reward_fn.time_limit
        valid = [r for r in results if not r.invalid]
        cleared = [r for r in valid if r.cleared]
        eff = [r.effective_time(tl) for r in valid]
        rewards = [reward_fn(r) for r in valid]

        block_tot: Counter = Counter()
        for r in valid:
            block_tot.update(r.block_time)
        total_bt = sum(block_tot.values()) or 1.0

        n_seg = max((len(r.segment_times) for r in cleared), default=0)
        seg_mean = [
            float(np.mean([r.segment_times[i] for r in cleared if len(r.segment_times) > i])) for i in range(n_seg)
        ]
        g_ok = sum(r.gimmick_success for r in valid)
        g_ng = sum(r.gimmick_fail for r in valid)
        reasons = Counter((r.invalid_reason or "").split(":")[0] for r in results if r.invalid)

        return EvaluationSummary(
            label=label,
            n=len(results),
            n_valid=len(valid),
            clear_rate=Stats.wilson(len(cleared), len(valid)),
            clear_time=Stats.bootstrap_mean([r.clear_time for r in cleared]),
            effective_time=Stats.bootstrap_mean(eff),
            deaths=Stats.bootstrap_mean([r.deaths for r in valid]),
            consumables=Stats.bootstrap_mean([r.consumables_used for r in valid]),
            reward=Stats.bootstrap_mean(rewards),
            reward_breakdown=reward_fn.mean_breakdown(valid),
            block_share={k: round(v / total_bt, 4) for k, v in sorted(block_tot.items())},
            segment_time_mean=[round(s, 2) for s in seg_mean],
            gimmick_success_rate=g_ok / max(1, g_ok + g_ng),
            stall_rate=Stats.wilson(sum(r.stalled for r in valid), len(valid)),
            invalid_ratio=(len(results) - len(valid)) / max(1, len(results)),
            invalid_reasons=dict(reasons),
            time_cv=Stats.cv(eff),
            raw_effective_times=eff,
            raw_rewards=rewards,
        )

    def evaluate(
        self,
        label: str,
        class_name: str,
        scenario: str,
        source: ParamSource,
        seeds: Sequence[int],
        reward_fn: RewardFunction,
    ) -> EvaluationSummary:
        return self.summarize(label, self.run(class_name, scenario, source, seeds), reward_fn)
