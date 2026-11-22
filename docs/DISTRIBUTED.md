# 분산 IMPALA — 로컬 다중 액터와 클라우드 확장

현재는 **로컬에서 액터 여러 개**를 띄워 돌린다. 구조는 처음부터 클라우드(액터가 다른 머신)를 전제로 만들었고,
로컬에서 쓰는 학습기 서버·액터 프로세스·전송 형식이 클라우드에서도 **그대로** 쓰인다.

## 1. 구성

```
           ┌──────────────── 학습기 머신 (1대) ────────────────┐
           │ python -m balance_qa ... impala                    │
           │  ├ ImpalaLearner  (V-trace, Adam, torch CPU)       │
           │  ├ ParameterServer (가중치 버전)                    │
           │  ├ LearnerServer  (TCP, --listen)  ◀───────┐       │
           │  └ 평가용 게임 연결 (--game / --workers)    │       │
           └─────────────────────────────────────────────│──────┘
                                                         │ 학습기 ↔ 액터 프로토콜 (balance_qa/rl/wire.py)
     ┌──────────── 액터 i (프로세스, 로컬 N개 / 클라우드 머신 N대) ──┴───────────┐
     │ python -m balance_qa --game <게임> actor --learner <학습기 주소>            │
     │  ├ RemoteActor: register → config(ActorSpec) → work(seed, 가중치) 반복     │
     │  ├ ActorCore:   Actor-Critic 추론(torch 스레드 1) + 궤적·구간 보상        │
     │  └ 게임 1개 (game_sim 대역 또는 Unity 헤드리스 빌드) ── docs/PROTOCOL.md   │
     └───────────────────────────────────────────────────────────────────────────┘
```

- **액터 1개 = 게임 인스턴스 1개 전담.** 액터는 게임과 같은 머신에 두는 것이 원칙 (게임 통신이 트리거마다 왕복하므로).
- 학습기 ↔ 액터 통신은 판당 2회 (작업 요청, 궤적 전송) + 가중치 바뀌었을 때만 가중치(~22KB). 지연에 둔감하다.
- 예산은 학습기가 **받은** 판 기준. 액터가 죽거나 늦게 붙어도 학습은 계속된다 (남은 액터가 채움).

## 2. 액터 모드

| `--actors` | 실행 | 액터 위치 | 게임 |
|---|---|---|---|
| `processes` (기본) | `python -m balance_qa --workers 8 impala ...` | 로컬 프로세스 8개 (자동) | 세션 게임 8개를 액터에 넘김 (학습 중 세션 연결은 잠시 놓음) |
| `threads` | `... impala --actors threads` | 학습기 프로세스 안 스레드 | 세션 게임 |
| `external` | `... impala --actors external --listen 0.0.0.0:7000 --token T` | 어디서든 `actor` 명령으로 접속 | 액터가 각자 가진 게임. 세션 게임은 평가 전용 |

## 3. 로컬에서 클라우드 구조 미리 돌려 보기 (external)

```bash
# 터미널 1: 학습기 (게임 1개는 평가용)
venv\Scripts\python.exe -m balance_qa --workers 1 impala --cls warrior --persona stable --budget 4000 ^
    --actors external --listen 127.0.0.1:7000 --token abc

# 터미널 2, 3, ...: 액터 (게임 미지정 시 파이썬 대역 1개를 자동 실행)
venv\Scripts\python.exe -m balance_qa actor --learner 127.0.0.1:7000 --token abc --actor-id A
venv\Scripts\python.exe -m balance_qa actor --learner 127.0.0.1:7000 --token abc --actor-id B
```

PyCharm: `run_impala.py` (`ACTORS="external"`) → `run_actor.py` 를 여러 번 실행.

## 4. 클라우드로 옮길 때 (현재 미적용 — 체크리스트)

코드 변경 없이 되는 것:
- 학습기: `--listen 0.0.0.0:<port> --token <비밀값> --actors external`
- 액터 머신마다: Unity 헤드리스 빌드 + 이 저장소 + venv → `python -m balance_qa --game-cmd "Game -batchmode -nographics -qaPort {port}" actor --learner <학습기IP>:<port> --token <비밀값>`
- 액터 수 = 실행한 액터 명령 수 (머신당 코어 수만큼 띄워도 됨)

클라우드 전에 보강이 필요한 것 (지금은 구현하지 않음):
| 항목 | 현재 | 필요 |
|---|---|---|
| 보안 | 평문 TCP + 공유 토큰 | VPC 내부망 또는 TLS/SSH 터널, 토큰은 비밀 저장소 |
| 학습기 장애 | 중단 시 처음부터 | 체크포인트 저장·재개 (모델·옵티마이저·버전·받은 판 수) |
| 액터 장애 | 해당 판만 유실, 학습 계속 | 자동 재시작 (프로세스 매니저/컨테이너 재시작 정책) |
| 액터 재접속 | 학습기 연결이 끊기면 액터 종료 | 재접속 재시도 루프 |
| 모니터링 | 학습기 콘솔 로그, 리포트 | 액터별 처리량·무효율 수집 (`episodes_by_actor` 는 리포트에 있음) |
| 배포 | 수동 | 컨테이너 이미지(액터 = Unity 빌드 + 파이썬), 오토스케일 |
| 학습기 처리량 | 단일 스레드 갱신 | 액터 수가 매우 많으면 batch 키우기·학습기 GPU 검토 |

## 5. 관련 코드

| 파일 | 역할 |
|---|---|
| `balance_qa/rl/backends.py` | `ActorContext`, `ThreadActorBackend`, `RemoteActorBackend`, `LearnerServer`, `ActorProcessLauncher` |
| `balance_qa/rl/remote_actor.py` | `RemoteActor` (액터 프로세스 메인 루프), `check_compatible` |
| `balance_qa/rl/actor.py` | `ActorCore` (판 1개 실행, 모든 모드 공용), `ParameterServer` |
| `balance_qa/rl/wire.py` | 학습기 ↔ 액터 메시지, 궤적·가중치 직렬화 |
| `balance_qa/rl/spec.py` | `ActorSpec` (액터가 필요한 설정 전부) |
| `balance_qa/cli.py` | `impala --actors/--listen/--token`, `actor` 명령 |
| `tests/integration/test_protocol_e2e.py` | threads / processes / external(토큰 거부 포함) 통합 테스트 |
