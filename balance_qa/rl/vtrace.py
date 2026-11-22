"""V-trace (Espeholt et al. 2018, IMPALA) — 패딩된 [B, T] 배치용.

v_s = V(x_s) + Σ_{t≥s} γ^{t−s} (Π_{i=s}^{t−1} c_i) δ_t,   δ_t = ρ_t (r_t + γ V(x_{t+1}) − V(x_t))
ρ_t = min(ρ̄, π/μ),  c_i = min(c̄, π/μ)
정책 그래디언트 이점: ρ_pg,t (r_t + γ v_{t+1} − V(x_t))

각 궤적은 마지막 유효 스텝에서 종료(판 끝)하므로 그 다음 V 와 v 는 0 (부트스트랩 없음).
"""
from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass
class VTraceReturns:
    vs: torch.Tensor           # [B, T] 가치 타깃
    pg_advantages: torch.Tensor  # [B, T]
    rhos: torch.Tensor         # [B, T] 잘리기 전 중요도 비율 (진단용)


def _shift_left(x: torch.Tensor) -> torch.Tensor:
    return torch.cat([x[:, 1:], torch.zeros_like(x[:, :1])], dim=1)


def vtrace(
    behavior_logp: torch.Tensor,
    target_logp: torch.Tensor,
    rewards: torch.Tensor,
    values: torch.Tensor,
    mask: torch.Tensor,
    gamma: float = 1.0,
    rho_bar: float = 1.0,
    c_bar: float = 1.0,
    pg_rho_bar: float = 1.0,
) -> VTraceReturns:
    with torch.no_grad():
        log_rhos = (target_logp - behavior_logp) * mask
        rhos = torch.exp(log_rhos)
        clipped_rhos = torch.clamp(rhos, max=rho_bar)
        cs = torch.clamp(rhos, max=c_bar)
        next_mask = _shift_left(mask)               # t+1 이 유효하면 1 (아니면 종료)
        values = values * mask
        next_values = _shift_left(values) * next_mask

        deltas = clipped_rhos * (rewards + gamma * next_values - values) * mask
        acc = torch.zeros_like(rewards[:, 0])
        vs_minus_v = torch.zeros_like(rewards)
        for t in reversed(range(rewards.shape[1])):
            acc = deltas[:, t] + gamma * cs[:, t] * acc * next_mask[:, t]
            vs_minus_v[:, t] = acc
        vs = (values + vs_minus_v) * mask

        next_vs = _shift_left(vs) * next_mask
        pg_rhos = torch.clamp(rhos, max=pg_rho_bar)
        pg_adv = pg_rhos * (rewards + gamma * next_vs - values) * mask
    return VTraceReturns(vs=vs, pg_advantages=pg_adv, rhos=rhos)
