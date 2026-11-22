"""IMPALA (Espeholt et al. 2018) — 비동기 액터-학습기 + V-trace, PyTorch CPU.

결정 트리거마다 BT 파라미터를 정하는 Actor-Critic 정책을 학습한다 (원문 9장 '짧은 에피소드 RL').
액터 = 게임 인스턴스 전담 실행 단위. 위치는 백엔드로 고른다:
  threads (학습기 프로세스 안) / processes (로컬 프로세스 N개) / external (원격 머신, 클라우드)
"""
from balance_qa.rl.actor import ActorCore, ActorParamSource, ActorWorker, InvalidEpisode, ParameterServer, observation
from balance_qa.rl.backends import (
    ActorBackend,
    ActorContext,
    ActorProcessLauncher,
    LearnerServer,
    RemoteActorBackend,
    ThreadActorBackend,
)
from balance_qa.rl.impala import ImpalaConfig, ImpalaResult, ImpalaTrainer
from balance_qa.rl.learner import ImpalaLearner, LearnerConfig
from balance_qa.rl.model import ActorCritic
from balance_qa.rl.remote_actor import RemoteActor, check_compatible
from balance_qa.rl.spec import ActorSpec
from balance_qa.rl.trajectory import SegmentRewards, Step, Trajectory, TrajectoryBatch
from balance_qa.rl.vtrace import VTraceReturns, vtrace

__all__ = [
    "ActorCore",
    "ActorParamSource",
    "ActorWorker",
    "InvalidEpisode",
    "ParameterServer",
    "observation",
    "ActorBackend",
    "ActorContext",
    "ActorProcessLauncher",
    "LearnerServer",
    "RemoteActorBackend",
    "ThreadActorBackend",
    "ImpalaConfig",
    "ImpalaResult",
    "ImpalaTrainer",
    "ImpalaLearner",
    "LearnerConfig",
    "ActorCritic",
    "RemoteActor",
    "check_compatible",
    "ActorSpec",
    "SegmentRewards",
    "Step",
    "Trajectory",
    "TrajectoryBatch",
    "VTraceReturns",
    "vtrace",
]
