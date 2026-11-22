---
name: bt-sim-run
description: 학습 플랫폼(balance_qa)으로 게임(game_sim 대역 또는 Unity)에 접속해 평가·최적화(CMA-ES)·트리거 정책 학습(ES)·민감도 분석·실험(E0~E7)을 실행하고 리포트를 해석한다. "돌려줘", "최적화해줘", "실험 실행", "직업 비교", "페르소나 매트릭스" 같은 요청에 사용.
---

# balance_qa 실행과 결과 해석

프로젝트 루트(`AI_QA/`)에서 실행한다. Python 3.8 + numpy + PyTorch(CPU) 환경.
학습 스레드가 부족하거나 과하면 `--torch-threads N` 으로 조정.

게임 연결 (명령 앞에 붙임):
- 기본: `--workers N` → 파이썬 게임 대역 N개 자동 실행 (= 병렬 판 수)
- 이미 떠 있는 게임(Unity 등): `--game 127.0.0.1:7777,127.0.0.1:7778`
- 명령으로 실행: `--workers N --game-cmd "Game.exe -batchmode -qaPort {port}"`

- 화면으로 보기: `--view 1` (Unity `--game-cmd` 와 함께). 창에서 '학습 판 자동 따라보기' 를 켜야 보인다.

실제 게임에 붙이기 전에는 반드시 `python -m balance_qa check-game --game HOST:PORT` (자세한 건 `/game-protocol`).

PyCharm 사용자는 `run/*.py` 의 설정 블록을 고쳐 ▶ Run 해도 같다 (`run/README.md`). 사용자에게 안내할 때는 해당 스크립트와 고칠 변수명을 함께 알려준다.

## 1. 먼저 확인

```bash
python -m unittest discover -s tests -t .   # 실패하면 실행하지 말고 원인부터
python -m balance_qa check-game             # 게임 프로토콜 적합성 (대역 또는 --game)
python -m balance_qa list                   # 게임 describe(직업·파라미터·시나리오·트리거) + 페르소나
```

## 2. 요청 → 명령 매핑

| 요청 | 명령 |
|---|---|
| 현재(손 튜닝) 성능 | `python -m balance_qa --workers 4 evaluate --cls <c...> --persona <p...> -n 300` |
| 파라미터 최적화 | `python -m balance_qa --workers 4 optimize --cls <c> --persona <p> --budget 3000` |
| 구간별 전략 학습 (ES) | `python -m balance_qa --workers 4 policy --cls <c> --persona <p> --budget 6000 --init-params reports/<id>/params.json` |
| 구간별 전략 학습 (IMPALA) | `python -m balance_qa --workers 8 impala --cls <c> --persona <p> --budget 8000 --init-params reports/<id>/params.json` |
| 어떤 값을 열지 | `python -m balance_qa --workers 4 sensitivity --cls <c> --persona <p> -n 100` |
| 패치 영향 | 위 명령에 `--scenario patch_boss_hp_up5` 등 |
| 가설 검증 | `python -m experiments.e<N>_<name> --workers 4` (먼저 `--quick` 으로 동작 확인) |

- `--workers` 는 CPU 코어 수 이하 (게임 인스턴스 = 프로세스). 대역 기준 1판 ≈ 20~40ms, 4개면 3,000판 ≈ 15~30초.
- 실제 게임은 판당 시간이 다르다. 먼저 `evaluate -n 20` 으로 처리량을 재고 예산을 정한다.
- 예산 가이드: 파라미터 7개 기준 CMA-ES 3,000판(k=10) 이면 대체로 충분. 정책(가중치 ~200개)은 6,000판 이상.
- 오래 걸리는 실험(E5, E6 full)은 백그라운드로 실행.

### IMPALA 액터 모드

- 기본 `--actors processes`: `--workers N` 게임마다 로컬 액터 프로세스 1개 (완료 줄에 `액터별 {...}` 판수 표시 → 고르게 나뉘는지 확인)
- `--actors external --listen HOST:PORT --token T`: 학습기는 대기, `python -m balance_qa actor --learner HOST:PORT --token T` 를 원하는 만큼 실행
- 액터 실패 시 학습기가 '액터가 모두 종료됨' 과 액터 stderr 를 보여 준다. external 은 `--idle-timeout` 초 동안 판이 없으면 중단

### IMPALA 로그 읽기

`upd | 판 | 평균 return | 최고 | V | ent | ρ(clip) | lag | 무효`
- **평균 return** 이 오르는지 (행동 정책 샘플 기준이라 평가값보다 낮게 나오는 게 정상)
- **ent**(Beta 엔트로피, 음수 가능): 거의 그대로면 lr 이 작아 정책이 안 움직이는 것, 급락하면 너무 큼 (기본 3e-3)
- **V** 가 평균 return 근처로 수렴하는지 (스텝 평균이라 판 return 보다 절댓값이 작음)
- **ρ clip** 이 높고 **lag** 가 크면 액터가 학습기보다 많이 뒤처짐 → batch 를 키우거나 액터(게임) 수 조정
- 비동기라 실행마다 학습 경로가 다르다. 결론은 평가(결정론적 Beta 평균) 결과와 반복 실행으로.

## 3. 리포트 읽는 순서

`reports/<run_id>/report.md` (사람용), `summary.json` (기계용), `params.json`/`policy.json` (재사용).

1. **학습 상태**: `수렴 판정`이 "아니오(예산 소진)"이고 세대 평균 곡선이 아직 오르는 중이면 예산 부족 → budget 증가 후 재실행.
2. **평가 표**: 반드시 평가 시드 결과(`평가 (평가용 시드…)`)로 말한다. 학습 중 `세대최고` 값은 운 좋은 후보라 과대평가됨.
3. **CI 겹침**: 두 조건의 95% CI 가 겹치면 차이를 주장하지 않는다. 필요한 판수는 `Stats.required_n(cv, delta)`.
4. **행동 분포**: 결과 차이를 블록 점유율(burst/dps/survival)로 설명한다. 예: 안정형은 survival 비율↑.
5. **무효 판 비율**: 0% 가 아니면 `invalid_reasons` 를 먼저 보고한다 (stalled = BT 가 멈춘 파라미터 조합, connection = 게임 연결 문제 → `/game-protocol`).
   리포트 meta 의 `game` 버전도 함께 적는다 (빌드가 바뀌면 결과 비교 불가).
6. **범위 끝 파라미터**: 학습값이 정의서 range 끝에 붙어 있으면 "범위가 결과를 제한"했을 수 있음을 함께 보고.

## 4. 결과 보고 형식

- 수치 + 95% CI + 판수(n) 를 같이 적는다. 예: `마법사 안정형 315.2s [314.3, 316.1], n=300`
- "장난감 환경 수치이며 경향 비교용"임을 한 줄 명시.
- 밸런스 결론(직업 A가 B보다 강하다 등)을 내기 전에는 `/bt-sim-balance-review` 체크리스트를 따른다.
