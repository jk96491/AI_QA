# AI_QA — BT 파라미터 최적화 밸런스 QA 프로토타입

원문 제안서 `밸런스 QA를 위한 BT 파라미터 최적화 프로세스.pdf`의 주장을 검증한다.
**새 세션은 `docs/STATUS.md`(현재 상태·결정 대기·빌드별 측정 이력·다음 할 일)부터 읽는다.** 작업이 끝나면 그 문서를 갱신한다.
설계 `시뮬레이션_프로토타입_설계.md`, 구조 `docs/ARCHITECTURE.md`, **게임 연동 계약 `docs/PROTOCOL.md`**.
플레이 모드(LLM 비전투 + 학습 BT 전투) 계약 `docs/PLAY_PROTOCOL.md` v0.2 (밸런스 계약과 별개), 클라이언트 `play_agent/`.

## 구조 (가장 중요)

| 패키지 | 역할 | 금지 |
|---|---|---|
| `game_sim/` | **게임 대역**: BT·전투·직업/보스 데이터·TCP 프로토콜 서버. 추후 **Unity 빌드로 교체** | `balance_qa`, `torch` import |
| `balance_qa/` | **학습 플랫폼**: 프로토콜 클라이언트·최적화(torch)·보상·평가·리포트 | `game_sim` import |
| `docs/PROTOCOL.md` | 둘 사이의 유일한 계약 (TCP JSON Lines v1.2) | — |
| `play_agent/` | **플레이 모드 클라이언트**: PlayClient·LoadoutBuilder·CombatResponder(IMPALA numpy)·LlmPilot(Claude API)·check-play. 학습 결과 파일만 읽음 | `game_sim`, `balance_qa`, `torch` import |
| `unity_game/` | **실제 테스트 게임 (Unity 프로젝트, 다른 에이전트가 제작 중)**. 제작 규칙 `unity_game/AGENT_GUIDE.md` | 학습 쪽 코드에서 import·경로 의존 금지 (`--game` / `--game-cmd` 로만 연결) |

- `game_sim/` 은 Unity 게임이 생긴 뒤에도 **참조 구현 + 테스트용 가짜 게임**으로 유지한다 (사용자 결정). 지우지 않는다.

- 두 패키지는 프로세스·포트로만 연결된다. `tests/test_independence.py` 가 import 를 검사한다.
- 게임 데이터(`game_sim/data/`)는 학습 쪽이 직접 읽지 않는다. `describe` 응답으로만 받는다.
- 페르소나(`qa_specs/personas.json`)는 퍼블리셔 쪽 정의라 학습 쪽에 있다.
- 프로토콜을 바꾸면: `docs/PROTOCOL.md` → `game_sim/server/*` → `balance_qa/game_api/*` → `ConformanceChecker` 순서로 모두 맞추고 버전 규칙(PROTOCOL 8장)을 지킨다.

## 환경 제약

- **Python 3.8**, 의존성 **numpy + PyTorch 1.8.1 CPU** 뿐 (scipy·pytest·pyyaml·cma·matplotlib 없음).
  - 프로젝트 인터프리터: **`venv\Scripts\python.exe`** (PyCharm 연결용, `requirements.txt` 로 numpy 1.22.4 + torch 1.8.1+cpu 고정).
    명령은 이 인터프리터로 실행한다 (예: `venv\Scripts\python.exe -m unittest discover -s tests -t .`).
  - `X | None`, `list[int]` 등 3.10+ 문법 금지. 모듈 맨 위 `from __future__ import annotations`.
  - torch 1.8 API: `torch.inference_mode` 없음 → `torch.no_grad()`. `torch.linalg.eigh/norm`, `torch.outer` 사용 가능.
- **학습 부분은 PyTorch CPU**: `balance_qa/optim/*`, `balance_qa/policy/mlp.py`, `balance_qa/rl/*` (IMPALA). 장치·dtype 은 `balance_qa/backend.py` (DEVICE=cpu, 최적화기 float64, 정책 float32). `.cuda()` 금지.
- 게임 쪽 BT·시뮬레이터는 numpy/순수 파이썬.
- 예외: `play_agent/pilot.py` 의 LLM 실행만 anthropic SDK 1.x(Python ≥3.10) 별도 venv. 나머지 `play_agent` 는 3.8 + numpy 로 돈다 (anthropic 은 실행 시점에만 import).
- 정의서·데이터는 **JSON**.
- Windows 콘솔 한글: 진입점에서 `sys.stdout.reconfigure(encoding="utf-8")` (cli, game_sim `__main__`, experiments/common 에 있음).

## 명령

```bash
python -m unittest discover -s tests -t .              # 전체 테스트 (game / learner / integration / independence)
python -m game_sim validate                             # 게임 데이터 검사
python -m game_sim serve --port 7777                    # 게임 대역 서버 단독 실행
python -m balance_qa check-game [--game 127.0.0.1:7777] # 프로토콜 적합성 검사 (Unity 연결 전 필수)
python -m balance_qa list                               # describe 정보 + 페르소나
python -m balance_qa --workers 4 evaluate --cls mage --persona stable -n 300
python -m balance_qa --workers 4 optimize --cls mage --persona stable --budget 3000
python -m balance_qa --workers 4 policy   --cls warrior --persona stable --budget 6000
python -m balance_qa --workers 8 impala   --cls warrior --persona stable --budget 8000   # IMPALA, 액터=게임 인스턴스
python -m balance_qa --game 127.0.0.1:7777,127.0.0.1:7778 optimize ...       # 이미 떠 있는 게임(Unity)
python -m balance_qa --workers 8 --game-cmd "Game.exe -batchmode -qaPort {port}" optimize ...
python -m play_agent check-play --exe unity_game/Build/QaArena.exe [--loadout reports/<run>]  # 플레이 모드 적합성 (LLM 없음)
python -m play_agent play --game 127.0.0.1:7800 --loadout reports/<run>   # LLM 플레이 — Python ≥3.10 + anthropic venv 전용
python -m experiments.e1_tuning_bias --workers 4 [--quick] [--game ...]       # E0~E7
```

**새 Unity 빌드 측정**: `venv\Scripts\python.exe run/run_measure_build.py` (적합성 + 손튜닝 기준선 + CMA-ES + IMPALA 표) → `docs/STATUS.md` 3장 표에 한 줄 추가.
**전체 사이클 점검**: `venv\Scripts\python.exe run/run_full_cycle.py` (적합성→describe→기준선→CMA-ES→params 재사용→IMPALA→리포트). 현재 최우선 목표는 성능이 아니라 이 사이클이 끊김 없이 도는 것 (사용자 우선순위).
PyCharm 실행: `run/*.py` (맨 위 설정 블록 → `balance_qa.cli.main(argv)` / `runpy` 호출) + `.idea/runConfigurations/*.xml` (QA 폴더, 01~10).
CLI 옵션을 추가·변경하면 해당 `run/*.py` 설정 블록도 같이 맞춘다.

`--view N` (+ `--game-cmd`): 인스턴스 중 앞의 N개를 Unity 창 모드로 실행 (전투 뷰어가 학습 판을 표본 재생). PyCharm `00b 전체 사이클 (Unity 화면)` 은 사이클 후 같은 seed 로 손 튜닝→CMA-ES→IMPALA 를 창에 보여 준다. 창 모드에는 `-qaFollow -qaViewSpeed 8` 이 자동으로 붙는다 (`launcher.VIEWER_FLAGS`, Unity 반영 완료).

`--workers N` = 게임 인스턴스 N개 = 병렬 판 수. 학습 연산 스레드는 `--torch-threads N`.
리포트: `reports/<run_id>/report.md` + `summary.json` (+ `params.json` / `policy.json`, 게임 버전 포함).

## 코드 규칙

- 모듈별 폴더 + 객체지향. 확장 지점은 추상 클래스:
  게임 `NeedFunction`, `Block` / 학습 `ParamSource`, `Optimizer`, `CandidateDecoder`, `EpisodeRunner`.
- CLI·실험 스크립트는 `balance_qa.session.QASession` 만 거쳐서 쓴다.
- **게임 결정성**: 판의 모든 난수는 `CombatSim.rng`(seed) 하나. 전역 난수 금지. 같은 seed·params·트리거 응답 → 같은 결과.
- 최적화기 난수는 `backend.generator(seed)` 의 `torch.Generator` 만.
- 학습 시드(`TRAIN_SEEDS`)와 평가 시드(`EVAL_SEEDS`)를 섞지 않는다. 최종 성능은 평가 시드로.
- 클라이언트는 판 진행 중 다른 요청을 끼워 넣지 않는다 (예: `describe` 는 `run_episode` 전에 확보).
- `tests/game/test_need.py`(문서 7장 61%/16% 재현)가 깨지면 N 식이나 선택 로직을 잘못 바꾼 것.

## 설계 결정 (원문과 다른 점)

- 페르소나 = N 설정값(θ, φ) + 보상 λ, w 는 최적화 출력. θ·φ 는 게임 정의서에 `group: persona` 로 선언.
- 보상 `R = −분 − λ_death·사망 − λ_consumable·소모품 − F_fail·[클리어 실패]`. F_fail = `qa_specs/personas.json` 최상위 `fail_penalty`(30분, 페르소나 공통·덮어쓰기 가능) — **원문 8장에 없는 항** (사용자 결정 A, 2026-11-22: 없으면 안정형이 '안 죽고 시간 초과'로 클리어를 포기). 구간 보상에서는 마지막 구간에 들어간다.
- 실패 판 소요 시간 = 경과 + 남은 보스 체력 비율 × 제한 시간 (중도절단).
- **멈춘 판(stalled, v1.2) = 실패**, 벌점은 시간 초과와 같게 `제한 시간 + 남은 체력 × 제한 시간` (사용자 결정 2026-11-22). `invalid` 는 환경 오류(통신·게임 예외)만 — 학습·평가에서 제외. v1.1 게임의 `invalid` + 사유 `stalled...` 는 `EpisodeResult.from_dict` 가 stalled 로 변환.
- S = 0 블록은 후보 제외. 비전투 체력 회복(피격 4초 후 2%/s).
- 트리거 index 0 = 판 시작 결정, 트리거 응답 params 는 부분 덮어쓰기.
- 마법사 정의서 default 는 E1 용으로 **의도적으로 덜 다듬은 값**.

## RL = IMPALA (사용자 결정)

- RL 은 **IMPALA** 로 한다 (`balance_qa/rl`). REINFORCE/PPO 등 다른 RL 을 새로 추가하지 않는다.
- 액터 = 게임 인스턴스 1개 전담. 위치는 `--actors`: **processes**(기본, 로컬 액터 프로세스 N개) / threads / **external**(학습기 `--listen` 대기, 액터는 `python -m balance_qa actor --learner ...` 로 접속 — 클라우드 대비). 상세 `docs/DISTRIBUTED.md`.
- 액터 실행 로직은 `rl/actor.py: ActorCore` 하나로 모든 모드가 공유한다. 학습기 ↔ 액터 메시지는 `rl/wire.py` (게임 프로토콜과 별개).
- 최종 목표는 클라우드 (사용자 계획). 지금은 로컬에서 돌리되, 학습기·액터를 같은 프로세스 메모리에 묶는 코드를 새로 만들지 않는다.
- 구간 보상은 `trigger.totals`(프로토콜 v1.1) 차분. 게임이 totals 를 안 보내면 `train_impala` 가 거부한다.
- `torch.set_num_threads` 는 프로세스 전역 — 액터 스레드에서 바꾸지 않는다.
- 기본 하이퍼파라미터: lr 3e-3, batch 16, hidden (64,64), γ 1.0, ρ̄=c̄=1, entropy 3e-3, Beta 초기 집중도 10.
  (warrior/stable 1,600판: 448→362s. lr 5e-4 는 정책이 거의 안 움직였고 1e-2 는 엔트로피가 빠르게 붕괴)

## 스킬

- `/bt-sim-run` — 평가·최적화·실험 실행과 결과 해석
- `/bt-sim-extend` — 직업·보스·페르소나·시나리오·BT 블록·알고리즘 추가
- `/bt-sim-balance-review` — 밸런스 결론 전 통계 점검
- `/game-protocol` — 게임(Unity) 연동: 프로토콜 구현·적합성 검사·연결
