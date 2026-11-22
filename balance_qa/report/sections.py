"""자주 쓰는 리포트 섹션 (CLI·실험 스크립트 공용)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

from balance_qa.analysis.evaluator import EvaluationSummary
from balance_qa.analysis.stats import Stats
from balance_qa.report.report import ReportBuilder

if TYPE_CHECKING:
    from balance_qa.session import OptimizationOutcome


def summary_table(rb: ReportBuilder, summaries: Sequence[EvaluationSummary], heading: str = "평가 결과") -> None:
    rb.section(heading, "값은 평균 [95% CI]. 시간 단위 초. effective_time 은 실패 판을 중도절단 처리한 값.")
    rb.dict_table([s.row() for s in summaries])
    rb.data(heading, [s.to_dict() for s in summaries])


def behavior_table(rb: ReportBuilder, summaries: Sequence[EvaluationSummary]) -> None:
    rb.section("행동 분포 (블록 점유율)")
    blocks = sorted({b for s in summaries for b in s.block_share})
    rb.table(
        ["label"] + blocks + ["gimmick_ok", "segments(s)"],
        [
            [s.label]
            + ["%.1f%%" % (100 * s.block_share.get(b, 0.0)) for b in blocks]
            + ["%.0f%%" % (100 * s.gimmick_success_rate), " / ".join("%.0f" % t for t in s.segment_time_mean)]
            for s in summaries
        ],
    )


def comparison(rb: ReportBuilder, a: EvaluationSummary, b: EvaluationSummary) -> None:
    t, df, p = Stats.welch(a.raw_effective_times, b.raw_effective_times)
    d = Stats.cohen_d(a.raw_effective_times, b.raw_effective_times)
    diff = a.effective_time.estimate - b.effective_time.estimate
    rb.text(
        "- **%s − %s**: %.1fs (%.1f%%), Welch t=%.2f, p≈%.3g, Cohen d=%.2f"
        % (a.label, b.label, diff, 100 * diff / b.effective_time.estimate, t, p, d)
    )


def outcome_section(rb: ReportBuilder, outcome: "OptimizationOutcome", baseline: Optional[EvaluationSummary] = None) -> None:
    tr = outcome.training
    rb.section("학습 상태 (%s/%s, %s)" % (outcome.class_name, outcome.persona_id, outcome.method))
    rb.text(
        "- 사용 판수: %d, 세대: %d, 수렴 판정: %s" % (tr.episodes_used, tr.generations, "예" if tr.converged else "아니오(예산 소진)")
    )
    rb.curve("세대 평균 보상", [h.gen_mean_reward for h in tr.history])
    rb.curve("세대 최고 보상", [h.gen_best_reward for h in tr.history])
    rb.data("history", tr.history_dicts())
    if outcome.params is not None:
        rb.section("학습된 파라미터")
        rb.table(["param", "value"], [[k, "%.4f" % v] for k, v in sorted(outcome.params.items())])
        rb.data("params", outcome.params)
    else:
        rb.data("source", outcome.source.describe())
    rows = [outcome.evaluation] if baseline is None else [baseline, outcome.evaluation]
    summary_table(rb, rows, "평가 (평가용 시드, 학습 시드와 분리)")
    behavior_table(rb, rows)
    if baseline is not None:
        rb.section("기준선 대비")
        comparison(rb, outcome.evaluation, baseline)
