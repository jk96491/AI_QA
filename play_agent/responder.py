"""전투 트리거 응답기 — LLM 을 거치지 않고 즉답한다.

- FixedResponder  : 항상 None (로드아웃 params 그대로, CMA-ES 결과용)
- ImpalaPolicy    : policy.json(IMPALA Actor-Critic) 을 numpy 로 순전파. 학습 쪽 torch 모델 평가 모드(Beta 평균)와 같은 값
- BanditPolicy    : policy.json(IMPALA 컨텍스트 밴딧) — (class, scenario, 판 시작 상태) → 가중치. 트리거 index 0 에만 답한다
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


class BetaMlp:
    """ActorCritic 정책 부분의 numpy 순전파 (ImpalaPolicy·BanditPolicy 공용).

    theta = torch parameters_to_vector 순서: torso Linear_i (weight out×in 행 우선, bias) … → pi_head → v_head(무시).
    """

    def __init__(self, theta: Sequence[float], obs_dim: int, hidden: Sequence[int], n_out: int, u_eps: float = 1e-4) -> None:
        self.obs_dim, self.hidden, self.n_out, self.u_eps = int(obs_dim), [int(h) for h in hidden], int(n_out), float(u_eps)
        theta = np.asarray(theta, dtype=np.float32)
        sizes, prev = [], self.obs_dim
        for h in self.hidden:
            sizes.append((h, prev))
            prev = h
        sizes += [(2 * self.n_out, prev), (1, prev)]
        need = sum(o * i + o for o, i in sizes)
        if theta.size != need:
            raise PolicyFileError("policy_theta 길이 %d ≠ 구조 %s 의 %d" % (theta.size, sizes, need))
        self.layers, k = [], 0
        for o, i in sizes:
            w = theta[k:k + o * i].reshape(o, i)
            k += o * i
            self.layers.append((w, theta[k:k + o]))
            k += o
        self.layers = self.layers[:-1]

    def unit_action(self, obs: np.ndarray) -> np.ndarray:
        h = np.asarray(obs, dtype=np.float32)
        for w, b in self.layers[:-1]:
            h = np.tanh(h @ w.T + b)
        w, b = self.layers[-1]
        raw = h @ w.T + b
        d = self.n_out
        alpha = _softplus(raw[:d]) + np.float32(1.0)
        beta = _softplus(raw[d:]) + np.float32(1.0)
        u = alpha.astype(np.float64) / (alpha.astype(np.float64) + beta.astype(np.float64))
        return np.clip(u, self.u_eps, 1.0 - self.u_eps)


class BanditPolicy:
    """IMPALA 컨텍스트 밴딧 (학습 쪽 balance_qa/rl/bandit.py, docs/BANDIT_IMPALA_DESIGN.md).

    관측 = [직업 원-핫] + [시나리오 원-핫] + [시작 상태 (context.states 순서, 없으면 default)].
    플레이 모드: 필드 전투의 트리거 index 0 state(예: potions_ratio = carried / cap)로 시작 상태를 읽어 가중치를 정한다.
    """

    def __init__(self, theta: Sequence[float], obs_dim: int, hidden: Sequence[int], outputs: Sequence[str],
                 output_ranges: Sequence[Sequence[float]], context: Mapping[str, Any],
                 fixed_by_class: Mapping[str, Mapping[str, float]], u_eps: float = 1e-4, label: str = "") -> None:
        self.outputs = list(outputs)
        self.ranges = np.asarray(output_ranges, dtype=np.float64).reshape(len(self.outputs), 2)
        self.classes = list(context["classes"])
        self.scenarios = list(context["scenarios"])
        self.states = [(str(s["name"]), float(s["default"])) for s in context["states"]]
        self.fixed_by_class = {k: dict(v) for k, v in fixed_by_class.items()}
        self.label = label
        if len(self.classes) + len(self.scenarios) + len(self.states) != int(obs_dim):
            raise PolicyFileError("context 차원 ≠ obs_dim %d" % obs_dim)
        self.net = BetaMlp(theta, obs_dim, hidden, len(self.outputs), u_eps)

    @property
    def combos(self) -> List[Key]:
        return [(c, s) for c in self.classes for s in self.scenarios]

    def observation(self, cls: str, scenario: str, state: Optional[Mapping[str, float]] = None) -> np.ndarray:
        x = np.zeros(len(self.classes) + len(self.scenarios) + len(self.states), dtype=np.float32)
        x[self.classes.index(cls)] = 1.0
        x[len(self.classes) + self.scenarios.index(scenario)] = 1.0
        off = len(self.classes) + len(self.scenarios)
        st = state or {}
        for i, (name, dflt) in enumerate(self.states):
            x[off + i] = float(st.get(name, dflt))
        return x

    def weights(self, cls: str, scenario: str, state: Optional[Mapping[str, float]] = None) -> Dict[str, float]:
        u = self.net.unit_action(self.observation(cls, scenario, state))
        lo, hi = self.ranges[:, 0], self.ranges[:, 1]
        return {n: float(v) for n, v in zip(self.outputs, lo + np.clip(u, 0.0, 1.0) * (hi - lo))}

    def bind(self, cls: str, scenario: str) -> "BanditBinding":
        return BanditBinding(self, cls, scenario)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], label: str = "") -> "BanditPolicy":
        src = d.get("source") or {}
        if src.get("type") != "impala-bandit" or "policy_theta" not in d:
            raise PolicyFileError("%s: 밴딧 policy.json 이 아님 (source.type=%r)" % (label, src.get("type")))
        return cls(d["policy_theta"], src["obs_dim"], src["hidden"], src["outputs"], src["output_ranges"], src["context"],
                   src["fixed_by_class"], u_eps=float(src.get("u_eps", 1e-4)), label=label)


class BanditBinding:
    """밴딧 정책을 (class, scenario) 하나에 묶은 것 — LoadoutEntry.policy 자리에 들어간다.

    - fixed: 로드아웃 params = 직업 판 파라미터 + 가득 찬 시작에서의 가중치 (트리거 0 응답 전 값)
    - thresholds: 트리거 index 0 이 오도록 경계 하나 ([0.5]). 이후 트리거에는 {} (가중치 그대로)
    """

    START_ONLY_THRESHOLDS = [0.5]

    def __init__(self, policy: BanditPolicy, cls: str, scenario: str) -> None:
        self.policy, self.cls, self.scenario = policy, cls, scenario
        self.thresholds = list(self.START_ONLY_THRESHOLDS)
        self.fixed = dict(policy.fixed_by_class.get(cls, {}), **policy.weights(cls, scenario))
        self.state_features: Optional[List[str]] = None   # 관측은 이름으로 읽으므로 순서 비교 안 함

    def params(self, trigger: Mapping[str, Any]) -> Dict[str, float]:
        if int(trigger.get("index", 0)) != 0:
            return {}
        return self.policy.weights(self.cls, self.scenario, trigger.get("state") or {})

    def __call__(self, trigger: Mapping[str, Any]) -> Dict[str, float]:
        return self.params(trigger)


def _softplus(x: np.ndarray) -> np.ndarray:
    # torch.nn.functional.softplus(beta=1, threshold=20) 와 같게
    x = np.asarray(x, dtype=np.float32)
    return np.where(x > 20.0, x, np.log1p(np.exp(np.minimum(x, 20.0)))).astype(np.float32)


class CombatResponder:
    """조우마다 (class, scenario) 정책을 골라 trigger 에 답한다. 정책이 없는 조우는 None(로드아웃 그대로)."""

    def __init__(self, policies: Optional[Mapping[Key, Any]] = None) -> None:
        self.policies: Dict[Key, Any] = dict(policies or {})   # ImpalaPolicy 또는 BanditBinding
        self._current: Optional[Any] = None
        self._encounter: Optional[str] = None
        self.answered = 0

    def add(self, cls: str, scenario: str, policy: Any) -> None:
        self.policies[(cls, scenario)] = policy

    def policy_for(self, cls: str, scenario: str) -> Optional[Any]:
        return self.policies.get((cls, scenario))

    def on_combat_started(self, msg: Mapping[str, Any]) -> None:
        self._encounter = str(msg.get("encounter_id"))
        self._current = self.policy_for(str(msg.get("class")), str(msg.get("scenario")))

    def __call__(self, trigger: Mapping[str, Any]) -> Optional[Dict[str, float]]:
        self.answered += 1
        if self._current is None:
            return None
        return self._current.params(trigger)

