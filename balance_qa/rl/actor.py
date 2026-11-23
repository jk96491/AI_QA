"""IMPALA 액터 구성요소.

- ActorParamSource : 트리거마다 Actor-Critic 정책으로 파라미터를 정하고 (관측, 행동, 로그확률, 누적값) 기록
- ActorCore        : 게임 연결 1개로 판 1개를 돌려 Trajectory 를 만드는 핵심 로직
                     (스레드 액터·프로세스 액터·원격 액터가 모두 이것을 쓴다)
- ParameterServer  : 학습기가 가중치를 게시하고 액터가 버전으로 가져감
- ActorWorker      : 학습기 프로세스 안의 스레드 액터 (actors="threads")
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import torch
from torch.nn.utils import vector_to_parameters

from balance_qa.backend import POLICY_DTYPE
from balance_qa.control.param_source import ParamSource
from balance_qa.core.types import GameError, TriggerState
from balance_qa.game_api.client import EpisodeRequest, GameClient
from balance_qa.rl.bandit import BanditParamSource, BanditSetup
from balance_qa.rl.model import U_EPS, ActorCritic
from balance_qa.rl.spec import ActorSpec
from balance_qa.rl.trajectory import SegmentRewards, Step, Trajectory
from balance_qa.spec.param import ParamSpace

if TYPE_CHECKING:
    from balance_qa.rl.backends import ActorContext


def observation(state: TriggerState, n_boundaries: int) -> np.ndarray:
    """정책 입력 = 게임 state_features (0~1) + 트리거 진행도 (index / 경계 수)."""
    return np.concatenate([state.to_vector(), [state.index / max(1, n_boundaries)]])


class ActorParamSource(ParamSource):
    """Actor-Critic 정책으로 트리거에 응답하는 파라미터 공급자.

    rng 가 있으면 샘플링(학습용 행동 정책), 없으면 Beta 평균(평가용, 결정론적).
    """

    def __init__(
        self,
        model: ActorCritic,
        space: ParamSpace,
        fixed: Mapping[str, float],
        thresholds: Sequence[float],
        rng: Optional[np.random.Generator] = None,
        record: bool = True,
        state_features: Optional[Sequence[str]] = None,
    ) -> None:
        self.model = model
        self.state_features = tuple(state_features) if state_features is not None else None
        self.space = space
        self.fixed = dict(fixed)
        self.trigger_thresholds = tuple(sorted(thresholds, reverse=True))
        self.rng = rng
        self.record = record
        self.steps: List[Step] = []

    def base_params(self) -> Dict[str, float]:
        return dict(self.fixed)

    def on_trigger(self, state: TriggerState) -> Dict[str, float]:
        obs = observation(state, len(self.trigger_thresholds))
        u, logp, value = self.model.act(obs, self.rng)
        if self.record:
            self.steps.append(Step(state.index, obs, u, logp, dict(state.totals), value))
        return self.space.decode(u)

    def describe(self) -> Dict[str, object]:
        """policy.json 의 source. 다시 불러와 쓰는 쪽(play_agent 의 numpy 순전파)이 필요한 것을 모두 싣는다:
        출력 범위(정규화 해제), 판 시작 고정 파라미터, 관측 순서, 모델 구조. policy_theta 는 torch
        parameters_to_vector 순서 (torso Linear 들 → pi_head → v_head, 각 weight(out×in 행 우선) 다음 bias)."""
        d: Dict[str, object] = {
            "type": "impala-actor-critic",
            "mode": "sample" if self.rng is not None else "mean",
            "model": repr(self.model),
            "outputs": self.space.names,
            "thresholds": list(self.trigger_thresholds),
            "output_ranges": [[p.low, p.high] for p in self.space.defs],
            "fixed": dict(self.fixed),
            "obs_dim": self.model.obs_dim,
            "hidden": list(self.model.hidden),
            "activation": "tanh",
            "u_eps": U_EPS,
        }
        if self.state_features is not None:
            d["state_features"] = list(self.state_features)
        return d


class ParameterServer:
    """학습기가 가중치를 올리고 액터가 가져가는 곳 (스레드 안전)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.version = -1
        self._state: Dict[str, torch.Tensor] = {}
        self._flat: Optional[np.ndarray] = None

    def publish(self, model: ActorCritic) -> int:
        state = model.snapshot()
        flat = model.flat().numpy().astype(np.float32)
        with self._lock:
            self.version += 1
            self._state = state
            self._flat = flat
            return self.version

    def fetch(self, known_version: int) -> Tuple[int, Optional[Dict[str, torch.Tensor]]]:
        """(현재 버전, state_dict 또는 None=변경 없음) — 같은 프로세스 액터용."""
        with self._lock:
            if self.version == known_version:
                return self.version, None
            return self.version, self._state

    def fetch_flat(self, known_version: int) -> Tuple[int, Optional[np.ndarray]]:
        """(현재 버전, 평탄 가중치 또는 None) — 원격 액터 전송용."""
        with self._lock:
            if self.version == known_version:
                return self.version, None
            return self.version, self._flat


class InvalidEpisode:
    """결과를 학습에 쓸 수 없는 판 (연결 실패·게임 판정 무효·트리거 없음)."""

    def __init__(self, seed: int, reason: str) -> None:
        self.seed = seed
        self.reason = reason


EpisodeItem = Union[Trajectory, InvalidEpisode]


class ActorCore:
    """게임 연결 1개로 판을 돌려 Trajectory 를 만든다. 가중치는 load_state / load_flat 으로 교체."""

    def __init__(self, client: GameClient, spec: ActorSpec) -> None:
        self.client = client
        self.spec = spec
        self.model = spec.new_model()
        self.model.eval()
        self.space = spec.space()
        self.rewards = SegmentRewards(spec.reward_fn())
        self.bandit = BanditSetup.from_wire(spec.extra["bandit"]) if spec.extra.get("bandit") else None
        self.version = -1
        self.episodes = 0
        self.invalid = 0

    def load_state(self, version: int, state: Dict[str, torch.Tensor]) -> None:
        self.model.load_state_dict(state)
        self.version = version

    def load_flat(self, version: int, flat: np.ndarray) -> None:
        with torch.no_grad():
            vector_to_parameters(torch.as_tensor(flat, dtype=POLICY_DTYPE), self.model.parameters())
        self.version = version

    def run(self, seed: int) -> EpisodeItem:
        """판 1개. GameError(요청 자체 오류)는 호출부로 올린다."""
        if self.bandit is not None:
            return self._run_bandit(seed)
        rng = np.random.default_rng([self.spec.sample_seed, int(seed)])
        src = ActorParamSource(self.model, self.space, self.spec.fixed, self.spec.thresholds, rng=rng)
        try:
            result = self.client.run_episode(EpisodeRequest(self.spec.class_name, seed, self.spec.scenario), src)
        except GameError:
            raise
        except (OSError, ConnectionError, ValueError) as exc:
            self.invalid += 1
            try:
                self.client.connect()
            except OSError:
                pass
            return InvalidEpisode(seed, "connection: %s" % exc)
        self.episodes += 1
        traj = self.rewards.build(src.steps, result, self.version)
        if traj is None:
            self.invalid += 1
            return InvalidEpisode(seed, result.invalid_reason or "no triggers")
        return traj


    def _run_bandit(self, seed: int) -> EpisodeItem:
        """컨텍스트 밴딧: seed 로 컨텍스트를 뽑고, 정책이 고른 가중치로 판 1개 (트리거 없음) → 길이 1 궤적."""
        assert self.bandit is not None
        rng = np.random.default_rng([self.spec.sample_seed, int(seed)])
        cell = self.bandit.sampler.sample(rng)
        src = BanditParamSource(self.model, self.space, self.bandit, cell, rng=rng)
        req = EpisodeRequest(cell.class_name, seed, cell.scenario, initial_state=cell.state_dict())
        try:
            result = self.client.run_episode(req, src)
        except GameError:
            raise
        except (OSError, ConnectionError) as exc:
            self.invalid += 1
            try:
                self.client.connect()
            except OSError:
                pass
            return InvalidEpisode(seed, "connection: %s" % exc)
        self.episodes += 1
        traj = self.rewards.build([src.step], result, self.version)
        if traj is None:
            self.invalid += 1
            return InvalidEpisode(seed, result.invalid_reason or "invalid")
        return traj


class ActorWorker(threading.Thread):
    """학습기 프로세스 안의 스레드 액터 (actors="threads")."""

    def __init__(self, actor_id: int, core: ActorCore, ctx: "ActorContext") -> None:
        super().__init__(name="impala-actor-%d" % actor_id, daemon=True)
        self.core = core
        self.ctx = ctx

    def run(self) -> None:
        # 주의: torch.set_num_threads 는 프로세스 전역이라 여기서 바꾸지 않는다 (학습기 스레드 수에 영향)
        while True:
            seed = self.ctx.next_seed()
            if seed is None:
                return
            version, state = self.ctx.params.fetch(self.core.version)
            if state is not None:
                self.core.load_state(version, state)
            try:
                item = self.core.run(seed)
            except GameError as exc:  # 요청 자체가 잘못됨 → 학습 중단
                self.ctx.put(exc)
                return
            if not self.ctx.put(item):
                return
