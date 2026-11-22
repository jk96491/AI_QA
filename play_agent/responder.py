"""전투 트리거 응답기 — LLM 을 거치지 않고 즉답한다.

- FixedResponder  : 항상 None (로드아웃 params 그대로, CMA-ES 결과용)
- ImpalaPolicy    : policy.json(IMPALA Actor-Critic) 을 numpy 로 순전파. 학습 쪽 torch 모델 평가 모드(Beta 평균)와 같은 값
- CombatResponder : (class, scenario) → 정책. 조우의 combat_started 로 고르고 trigger 마다 답한다

numpy 만 쓴다 (torch 금지 — play_agent 는 학습 쪽 코드를 import 하지 않는다).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

Key = Tuple[str, str]   # (class, scenario)


class PolicyFileError(ValueError):
    pass


class ImpalaPolicy:
    """ActorCritic(obs-h1-h2-[Beta×d | V]) 의 정책 부분.

    policy_theta = torch parameters_to_vector 순서:
      torso Linear_i (weight out×in 행 우선, bias) … → pi_head (weight 2d×h, bias) → v_head (무시)
    α = softplus(raw_a)+1, β = softplus(raw_b)+1, u = clip(α/(α+β), ε, 1−ε), 값 = low + u·(high−low)
    관측 = state_features 순서의 trigger.state + [index / 경계 수].
    """

    def __init__(self, theta: Sequence[float], obs_dim: int, hidden: Sequence[int], outputs: Sequence[str],
                 output_ranges: Sequence[Sequence[float]], state_features: Sequence[str], thresholds: Sequence[float],
                 fixed: Optional[Mapping[str, float]] = None, u_eps: float = 1e-4, label: str = "") -> None:
        self.obs_dim = int(obs_dim)
        self.hidden = [int(h) for h in hidden]
        self.outputs = list(outputs)
        self.ranges = np.asarray(output_ranges, dtype=np.float64).reshape(len(self.outputs), 2)
        self.state_features = list(state_features)
        self.thresholds = sorted((float(t) for t in thresholds), reverse=True)
        self.fixed = dict(fixed or {})
        self.u_eps = float(u_eps)
        self.label = label
        if len(self.state_features) + 1 != self.obs_dim:
            raise PolicyFileError("state_features %d개 + 1 ≠ obs_dim %d" % (len(self.state_features), self.obs_dim))
        self.layers = self._unflatten(np.asarray(theta, dtype=np.float32))

    def _unflatten(self, theta: np.ndarray) -> List[Tuple[np.ndarray, np.ndarray]]:
        sizes = []
        prev = self.obs_dim
        for h in self.hidden:
            sizes.append((h, prev))
            prev = h
        sizes.append((2 * len(self.outputs), prev))   # pi_head
        sizes.append((1, prev))                        # v_head
        need = sum(o * i + o for o, i in sizes)
        if theta.size != need:
            raise PolicyFileError("policy_theta 길이 %d ≠ 구조 %s 의 %d" % (theta.size, sizes, need))
        layers, k = [], 0
        for o, i in sizes:
            w = theta[k:k + o * i].reshape(o, i)
            k += o * i
            b = theta[k:k + o]
            k += o
            layers.append((w, b))
        return layers[:-1]   # 가치 머리는 응답에 필요 없음

    # ------------------------------------------------------------------ 순전파
    def observation(self, trigger: Mapping[str, Any]) -> np.ndarray:
        state = trigger.get("state") or {}
        x = [float(state.get(k, 0.0)) for k in self.state_features]
        x.append(float(trigger.get("index", 0)) / max(1, len(self.thresholds)))
        return np.asarray(x, dtype=np.float32)

    def unit_action(self, obs: np.ndarray) -> np.ndarray:
        h = np.asarray(obs, dtype=np.float32)
        for w, b in self.layers[:-1]:
            h = np.tanh(h @ w.T + b)
        w, b = self.layers[-1]
        raw = h @ w.T + b
        d = len(self.outputs)
        alpha = _softplus(raw[:d]) + np.float32(1.0)
        beta = _softplus(raw[d:]) + np.float32(1.0)
        u = alpha.astype(np.float64) / (alpha.astype(np.float64) + beta.astype(np.float64))
        return np.clip(u, self.u_eps, 1.0 - self.u_eps)

    def params(self, trigger: Mapping[str, Any]) -> Dict[str, float]:
        u = self.unit_action(self.observation(trigger))
        lo, hi = self.ranges[:, 0], self.ranges[:, 1]
        vals = lo + np.clip(u, 0.0, 1.0) * (hi - lo)
        return {n: float(v) for n, v in zip(self.outputs, vals)}

    def __call__(self, trigger: Mapping[str, Any]) -> Dict[str, float]:
        return self.params(trigger)

    # ------------------------------------------------------------------ 파일
    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "ImpalaPolicy":
        path = Path(path)
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(d, label=str(path))

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], label: str = "") -> "ImpalaPolicy":
        src = d.get("source") or {}
        if src.get("type") != "impala-actor-critic" or "policy_theta" not in d:
            raise PolicyFileError("%s: IMPALA policy.json 이 아님 (source.type=%r)" % (label, src.get("type")))
        missing = [k for k in ("output_ranges", "fixed", "state_features", "obs_dim", "hidden") if k not in src]
        if missing:
            raise PolicyFileError(
                "%s: 정책을 다시 불러올 정보가 없음 %s — 학습 쪽이 이 정보를 싣기 전(2026-11-23 이전)에 만든 파일. "
                "IMPALA 를 다시 돌려 새 policy.json 을 만들 것" % (label, missing))
        return cls(d["policy_theta"], src["obs_dim"], src["hidden"], src["outputs"], src["output_ranges"],
                   src["state_features"], src.get("thresholds", ()), fixed=src.get("fixed"),
                   u_eps=float(src.get("u_eps", 1e-4)), label=label)


def _softplus(x: np.ndarray) -> np.ndarray:
    # torch.nn.functional.softplus(beta=1, threshold=20) 와 같게
    x = np.asarray(x, dtype=np.float32)
    return np.where(x > 20.0, x, np.log1p(np.exp(np.minimum(x, 20.0)))).astype(np.float32)


class CombatResponder:
    """조우마다 (class, scenario) 정책을 골라 trigger 에 답한다. 정책이 없는 조우는 None(로드아웃 그대로)."""

    def __init__(self, policies: Optional[Mapping[Key, ImpalaPolicy]] = None) -> None:
        self.policies: Dict[Key, ImpalaPolicy] = dict(policies or {})
        self._current: Optional[ImpalaPolicy] = None
        self._encounter: Optional[str] = None
        self.answered = 0

    def add(self, cls: str, scenario: str, policy: ImpalaPolicy) -> None:
        self.policies[(cls, scenario)] = policy

    def policy_for(self, cls: str, scenario: str) -> Optional[ImpalaPolicy]:
        return self.policies.get((cls, scenario))

    def on_combat_started(self, msg: Mapping[str, Any]) -> None:
        self._encounter = str(msg.get("encounter_id"))
        self._current = self.policy_for(str(msg.get("class")), str(msg.get("scenario")))

    def __call__(self, trigger: Mapping[str, Any]) -> Optional[Dict[str, float]]:
        self.answered += 1
        if self._current is None:
            return None
        return self._current.params(trigger)

