"""IMPALA 학습기: 궤적 배치 → V-trace → 정책·가치·엔트로피 손실 → 가중치 갱신 (torch CPU)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import torch

from balance_qa.rl.model import ActorCritic
from balance_qa.rl.trajectory import TrajectoryBatch
from balance_qa.rl.vtrace import vtrace


@dataclass
class LearnerConfig:
    lr: float = 3e-3
    gamma: float = 1.0           # 판이 짧고(≤4 스텝) 보상이 시간 비용이라 할인 없음
    rho_bar: float = 1.0
    c_bar: float = 1.0
    baseline_coef: float = 0.5
    entropy_coef: float = 3e-3
    grad_clip: float = 40.0


class ImpalaLearner:
    def __init__(self, model: ActorCritic, config: LearnerConfig) -> None:
        self.model = model
        self.cfg = config
        self.optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)
        self.updates = 0

    def update(self, batch: TrajectoryBatch, current_version: int) -> Dict[str, float]:
        cfg = self.cfg
        self.model.train()
        dist, values = self.model.distribution(batch.obs)
        target_logp = self.model.log_prob(dist, batch.actions)
        vt = vtrace(batch.behavior_logp, target_logp.detach(), batch.rewards, values.detach(), batch.mask,
                    gamma=cfg.gamma, rho_bar=cfg.rho_bar, c_bar=cfg.c_bar)
        n = batch.mask.sum().clamp(min=1.0)
        pg_loss = -(target_logp * vt.pg_advantages * batch.mask).sum() / n
        v_loss = 0.5 * (((vt.vs - values) ** 2) * batch.mask).sum() / n
        entropy = (dist.entropy().sum(-1) * batch.mask).sum() / n
        loss = pg_loss + cfg.baseline_coef * v_loss - cfg.entropy_coef * entropy

        self.optimizer.zero_grad()
        loss.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(self.model.parameters(), cfg.grad_clip)
        self.optimizer.step()
        self.updates += 1

        valid = batch.mask > 0
        lag = (current_version - batch.versions).float()
        return {
            "loss": float(loss),
            "pg_loss": float(pg_loss),
            "v_loss": float(v_loss),
            "entropy": float(entropy),
            "grad_norm": float(grad_norm),
            "rho_mean": float(vt.rhos[valid].mean()),
            "rho_clip_frac": float((vt.rhos[valid] > cfg.rho_bar + 1e-3).float().mean()),  # 부동소수 오차 제외
            "policy_lag": float(lag.mean()),
            "value_mean": float(values[valid].mean()),
        }
