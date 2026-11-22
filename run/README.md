# PyCharm 실행 스크립트

각 파일 맨 위 `===== 설정 =====` 블록만 고치고 PyCharm 에서 **▶ Run** (또는 우클릭 → Run).
안에서 `python -m balance_qa ...` / `python -m experiments...` 를 그대로 호출하므로 cmd 실행과 결과가 같다.
실행할 때 실제 명령이 첫 줄에 `$ python -m ...` 로 찍힌다.

상단 실행 목록(`QA` 폴더)에도 같은 이름으로 등록되어 있다 (`.idea/runConfigurations`).

| 실행 구성 | 파일 | 하는 일 |
|---|---|---|
| **00 전체 사이클 점검** | `run_full_cycle.py` | 적합성 → describe → 기준선 → CMA-ES → params 저장·재사용 → IMPALA → 리포트 (작은 예산, 끊김 없이 도는지만) |
| **00b 전체 사이클 (Unity 화면)** | `run_full_cycle_view.py` | Unity 빌드 4개(1개 창) 로 같은 점검 + 마지막에 같은 seed 로 손 튜닝 → CMA-ES → IMPALA 판을 창에 재생 |
| 01 테스트 전체 | `run_tests.py` | 전체 단위·통합 테스트 |
| **12 빌드 측정** | `run_measure_build.py` | 새 Unity 빌드: 적합성 + 손튜닝 기준선(직업×페르소나) + CMA-ES + IMPALA 결과 표 |
| 02 게임 적합성 검사 | `run_check_game.py` | 프로토콜 검사 (`GAME` = Unity 빌드 주소) |
| 03 게임·페르소나 목록 | `run_list.py` | describe 정보 + 페르소나 |
| 04 평가 | `run_evaluate.py` | 고정 파라미터 평가 (`PARAMS_FILE` 로 학습 결과 평가) |
| 05 최적화 (CMA-ES) | `run_optimize.py` | 판당 1회 파라미터 최적화 → `params.json` |
| 06 IMPALA 학습 | `run_impala.py` | 트리거 정책 IMPALA (`INIT_PARAMS` 에 05 결과 권장) |
| 07 트리거 정책 (ES) | `run_policy_es.py` | 비교용 ES 정책 |
| 08 민감도 분석 | `run_sensitivity.py` | OAT |
| 09 실험 E0~E7 | `run_experiment.py` | `EXPERIMENT`, `QUICK` 선택 |
| 10 게임 대역 서버 | `run_game_server.py` | 게임 대역을 포트에 띄워 둠 (■ 로 정지) |
| 11 IMPALA 액터 | `run_actor.py` | external 모드 학습기에 접속하는 액터 1개 (여러 번 실행 가능) |

## Unity 빌드로 실행 / 화면으로 보기

```python
GAME_CMD = UNITY   # unity_game/Build/QaArena.exe 를 헤드리스로 WORKERS 개 실행
VIEW = 1           # 그중 1개를 창 모드로 → 전투 뷰어
```
창이 뜨면 오른쪽 패널의 **'학습 판 자동 따라보기'** 를 켠다 (속도 숫자키 1~6, Tab 패널).
학습 판은 1~2 ms 마다 끝나므로 창에는 "재생이 끝날 때마다 가장 최근 판" 이 표본으로 보인다. 학습 속도는 그대로다.

## 게임 연결 설정 (공통)

```python
GAME = None        # None: 파이썬 게임 대역을 WORKERS 개 자동 실행
                   # "127.0.0.1:7777,127.0.0.1:7778": 이미 떠 있는 게임(Unity 빌드)에 접속
WORKERS = 4        # 게임 인스턴스 수 = 병렬 판 수 (IMPALA 는 = 액터 수)
GAME_CMD = None    # "Build/Game.exe -batchmode -nographics -qaPort {port}": 명령으로 WORKERS 개 실행
```

## 흔한 흐름

1. `05 최적화` → 결과 경로 `reports/<run_id>/params.json` 확인
2. `06 IMPALA` 의 `INIT_PARAMS = "reports/<run_id>/params.json"` 로 설정 후 실행
3. `04 평가` 의 `PARAMS_FILE` 로 다른 시나리오(`SCENARIO`)에서 재평가

Unity 연결 테스트를 파이썬 대역으로 미리 해 보려면: `10 게임 대역 서버` 실행 → 다른 스크립트에서 `GAME = "127.0.0.1:7777"`.

## IMPALA 액터 구성

| `run_impala.py` ACTORS | 액터 위치 | 언제 |
|---|---|---|
| `"processes"` (기본) | 게임마다 로컬 액터 프로세스 자동 실행 | 로컬에서 여러 액터 |
| `"threads"` | 학습기 프로세스 안 스레드 | 가볍게 확인 |
| `"external"` | `run_actor.py` 를 따로 실행해 접속 | 다른 PC·클라우드 구조 미리 확인 |

external 예: `run_impala.py` 에 `ACTORS="external"`, `LISTEN="127.0.0.1:7000"`, `TOKEN="abc"` → 실행 →
`run_actor.py` 에 `LEARNER="127.0.0.1:7000"`, `TOKEN="abc"` 로 2~3번 실행.
