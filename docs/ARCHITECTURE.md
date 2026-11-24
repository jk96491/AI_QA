# 아키텍처

## 0. 큰 그림: 게임과 학습 플랫폼의 분리

```
┌──────────────────────────────┐   TCP JSON Lines    ┌───────────────────────────────────┐
│ 게임 (game_sim → 추후 Unity)  │ ◀── docs/PROTOCOL.md ──▶ │ 학습 플랫폼 (balance_qa)            │
│                              │                     │                                   │
│  server/  프로토콜 서버       │  run_episode        │  game_api/  클라이언트·풀·실행기    │
│  sim/     전투 (seed 결정론)  │  trigger ↔ response │  optim/     CMA-ES·ES (torch CPU)  │
│  bt/      BT (S = N × w)     │  episode_result     │  policy/    MLP 정책 (torch CPU)   │
│                              │  (trigger.totals)   │  rl/        IMPALA (torch CPU)     │
│  spec/    직업·보스·시나리오   │  describe(정의서)    │  reward/ analysis/ report/        │
│  data/    게임 데이터 JSON    │                     │  qa_specs/  페르소나               │
└──────────────────────────────┘                     └───────────────────────────────────┘
   numpy, torch 금지·학습 코드 금지                        game_sim import 금지
```

- **SDK (2026-11-23, `docs/SDK.md`)**: 게임 쪽 프로토콜 처리는 Game SDK(Python `btqa_game` = 별도 레포 btqa_sdk 직접 참조 / Unity `Packages/com.btqa.game` 사본)가 하고, 게임은 `EpisodeHost`(정의서·판 실행)만 구현한다.
  **학습 대상 = 게임이 `classes[].blocks` 로 선언한 블록 가중치뿐** (`ClassInfo.learnable_space()`, CMA-ES·IMPALA 공통).
- **게임 쪽**은 BT 와 전투, 직업·스킬·보스 수치를 가진다. 학습 쪽에는 **정의서(파라미터 이름·범위·기본값)** 만 공개한다.
- **학습 쪽**은 파라미터 숫자를 정해 보내고 결과를 받는다. 스킬·스탯을 모른다.
- 두 패키지는 서로 import 하지 않는다 (`tests/test_independence.py`). 연결은 프로세스·포트로만.
- 게임 인스턴스 1개 = 서버 1개 = 동시 연결 1개. 병렬은 인스턴스 수로 (원문 11장 VM 풀).

## 1. 원문 ↔ 코드 대응

| 원문 개념 | 쪽 | 코드 |
|---|---|---|
| 게임 빌드 + QA API | 게임 | `game_sim/server` (`GameServer`, `GameSession`) |
| 정의서 (파라미터·트리거·입력값) | 게임 → 학습 | `describe` 응답 / `game_sim/data/classes/*.json` → `balance_qa.spec.GameDescription` |
| 전투 전용 BT, 점수 기반 선택 노드 | 게임 | `game_sim.bt.BTAgent`, `UtilitySelector`, `*Need`, `*Block` |
| 정의서 검증 | 양쪽 | 게임: `game_sim.spec.SpecValidator` (기동 시) / 학습: `ConformanceChecker` (연결 시) |
| 페르소나 = N 설정값 + λ | 학습 | `qa_specs/personas.json`, `balance_qa.spec.Persona` |
| 보상 | 학습 | `balance_qa.reward.RewardFunction` |
| 판당 1회 결정 | 학습 | `StaticParamSource` → `run_episode.params` |
| 결정 트리거 + 정책 (ES) | 학습 | `PolicyParamSource` (`trigger` → `trigger_response`) + `MLPPolicy` |
| 짧은 에피소드 RL (IMPALA) | 학습 | `balance_qa.rl`: `ActorCritic`, `ActorWorker`, `ImpalaLearner`, `vtrace` |
| 구간별 보상 | 게임 → 학습 | `trigger.totals` (v1.1) → `rl.SegmentRewards` |
| 에피소드 실행 API | 학습 | `balance_qa.runner.EpisodeRunner` ← `game_api.GamePool` |
| VM 풀 / 환경 에이전트(기동·스모크) | 학습 | `game_api.LocalSimLauncher`, `CommandLauncher`, `ConformanceChecker` |
| 학습 에이전트 | 학습 | `balance_qa.optim.Trainer` |
| 리포트 | 학습 | `balance_qa.analysis`, `balance_qa.report` |

범위 밖: 진행 모드(LLM), LLM 에이전트 오케스트레이션, 대련 AI.

## 2. 실행 백엔드

| 영역 | 라이브러리 |
|---|---|
| 게임 (`game_sim`) | numpy / 순수 파이썬. torch 금지 |
| 프로토콜 | 표준 라이브러리 `socket`, `json` (양쪽 각자 구현) |
| 최적화기·Trainer | **PyTorch CPU float64**, `torch.Generator` 로 시드 고정 |
| 정책 `MLPPolicy` | **PyTorch `nn.Module` CPU float32** — 학습 쪽 프로세스에서 트리거 때 추론 |
| IMPALA `ActorCritic`·`ImpalaLearner` | **PyTorch CPU float32**, Beta 정책 + 가치 헤드, Adam, V-trace |
| 평가·통계·리포트 | numpy |

## 3. 학습 데이터 흐름

```
QASession
  ├─ launcher (LocalSimLauncher / CommandLauncher)  … 게임 인스턴스 N개 기동
  ├─ GamePool(endpoints)                            … 연결 N개, 스레드 N개
  │    └─ describe → GameDescription (클래스·파라미터·트리거 상태 키·제한 시간)
  └─ Trainer.train(optimizer, decoder)
       loop:
         xs = optimizer.ask()                          torch (pop, d)
         sources = decoder.decode(x)                   StaticParamSource | PolicyParamSource
         jobs = sources × TRAIN_SEEDS.batch(gen, k)    (공통 난수)
         results = GamePool.run(jobs)                  → 게임: run_episode / trigger ↔ response
         rewards = RewardFunction.mean(...)            무효 판 제외
         optimizer.tell(xs, −rewards)
       → recommendation → Evaluator (EVAL_SEEDS) → ReportBuilder
```

## 3.5 IMPALA (`balance_qa/rl`)

```
액터 i (스레드, 게임 인스턴스 i 전담)                         학습기 (메인 스레드)
  판 시작: 파라미터 서버에서 최신 가중치(버전 v) 확인
  run_episode(triggers) ─▶ 게임
  trigger(state, totals) ─▶ Beta 정책 샘플 u, log μ(u) 기록
  ◀─ trigger_response(params = decode(u))
  episode_result ─▶ SegmentRewards(totals 차분) ─▶ Trajectory ─▶ 큐 ─▶ batch_size 개 모이면
                                                                    V-trace(ρ̄=c̄=1, γ=1)
                                                                    loss = pg + ½·value − c·entropy
                                                                    Adam, grad clip → 게시(v+1)
```

| 구성 | 클래스 | 비고 |
|---|---|---|
| 정책·가치 | `ActorCritic` | 관측 = state_features + 트리거 진행도, 출력 = 파라미터별 Beta(α,β) + V. 초기 평균 = 정의서 default (또는 init_params) |
| 액터 | `ActorWorker`, `ActorParamSource` | 게임 연결 1개씩, 행동 샘플 rng = (seed, 판 seed) |
| 궤적 | `Step`, `Trajectory`, `TrajectoryBatch` | 판당 스텝 ≤ 1 + 경계 수, 패딩 + mask |
| 보상 | `SegmentRewards` | Σ 구간 보상 = `RewardFunction` 판 보상 (중도절단 벌점은 마지막 구간) |
| 보정 | `vtrace` | 마지막 유효 스텝은 종료 → 부트스트랩 없음 |
| 갱신 | `ImpalaLearner` | 진단: entropy, V, ρ 평균·잘림 비율, policy lag, grad norm |
| 동기화 | `ParameterServer` | 버전 번호로 가중치 게시/가져가기 |
| 평가 | `ImpalaTrainer.eval_source()` | Beta 평균 = 결정론적 정책, 평가 시드 |

비동기라 같은 설정이어도 학습 경로는 실행마다 조금 다르다. 평가는 결정론적이다.

**액터 위치**(`--actors`): processes(기본, 로컬 액터 프로세스) / threads / external(원격 접속). processes·external 은 같은 `LearnerServer`(TCP)와 `RemoteActor` 를 쓰므로 로컬 구조가 그대로 클라우드로 간다 → `docs/DISTRIBUTED.md`.

## 4. 게임 쪽 한 판 (`game_sim.sim.CombatSim`)

1 스텝 = 0.3초 (BT 결정 주기).

1. `params` = 정의서 default ← 요청 params 덮어쓰기 (검증) → `BTAgent.set_params`
2. 트리거 요청 시: index 0 트리거 → 응답 params 덮어쓰기
3. 매 스텝: `Player.tick` → (사망/시전/BT 결정) → 보스 체력 경계 통과 시 트리거 → `Boss.update` → 사망 처리 → 무효 판 감지
4. `EpisodeResult.to_dict()` → `episode_result.result`

### BT 구조

```
Root (Selector)
├─ Sequence: 기믹 경고? → [강제] GimmickBlock
└─ UtilitySelector  (S = N × w, S > 0 인 후보 중 최댓값, min_commit 동안 유지)
   ├─ BurstBlock    N = 0.8 (버스트 준비) / 제외
   ├─ DpsBlock      N = 0.5·min(1, hp/φ)   / 사거리 밖이면 제외
   ├─ SurvivalBlock N = max(0, (θ−hp)/θ)
   └─ (후보 없음) ApproachBlock
```

## 5. 확장 지점

| 하고 싶은 것 | 쪽 | 방법 |
|---|---|---|
| 직업 추가 | 게임 | `game_sim/data/classes/<name>.json` (학습 쪽 수정 없음) |
| 패치 시나리오 | 게임 | `game_sim/data/scenarios.json` |
| BT 블록 / 필요도 식 | 게임 | `game_sim.bt` (`Block`, `NeedFunction`) + 정의서 파라미터 |
| 트리거 상태 키 추가 | 게임 | `TRIGGER_STATE_FEATURES` + `CombatSim.trigger_state` (정책 입력 차원이 자동으로 바뀜) |
| 페르소나 | 학습 | `qa_specs/personas.json` |
| 최적화 알고리즘 | 학습 | `balance_qa.optim.Optimizer` 상속 |
| RL 알고리즘 변형 (IMPALA 설정·손실) | 학습 | `balance_qa.rl` (`LearnerConfig`, `ImpalaLearner.update`) |
| 새 파라미터 공급 방식 | 학습 | `ParamSource` + `CandidateDecoder` |
| **Unity 게임 연결** | 게임 | `docs/PROTOCOL.md` 구현 → `check-game` 통과 → `--game` / `--game-cmd` |

## 6. 알려진 한계

- 장난감 환경: 1:1 보스전, 1차원 거리, 단일 보스. 수치는 경향 비교용.
- OAT 민감도는 상호작용을 보지 못함. p-값은 정규 근사.
- 블랙보드 공통 성향값(원문 6장)과 목표 난이도 역산(E8)은 미구현.
- 게임 1개가 동시 연결 1개만 처리 → 병렬은 인스턴스 수로만.
- 마법사 정의서 default 는 E1 용으로 의도적으로 나쁜 값.
