# 현재 상태 · 이어서 할 일 (2026-11-22 기준)

> 새 세션은 이 문서부터 읽는다. 구조·규칙은 `../CLAUDE.md`, 게임 계약은 `PROTOCOL.md`(v1.2).

## 1. 지금 어디까지 왔나

| 영역 | 상태 |
|---|---|
| 학습 플랫폼 `balance_qa` | 완료: 평가·CMA-ES·ES 정책·**IMPALA**(Beta Actor-Critic, V-trace, torch CPU)·민감도·리포트 |
| IMPALA 액터 | 로컬 다중 프로세스(기본) / threads / external(클라우드 대비). 클라우드 보강 항목은 `DISTRIBUTED.md` 4장 |
| 게임 대역 `game_sim` | 참조 구현 + 테스트용 (지우지 않음). 프로토콜 1.2, 버전 0.4.0 |
| 실제 게임 `unity_game` (QaArena) | 다른 에이전트가 제작. **0.4.0** 빌드: 적합성 15/15 PASS, 판당 1~2 ms |
| 화면 보기 | `--view N` / PyCharm `00b 전체 사이클 (Unity 화면)` — 창 4개, `-qaFollow -qaViewSpeed 8` 자동 |
| 전체 사이클 | Unity 0.4.0 으로 6단계 PASS (`run/run_full_cycle.py`, `GAME_CMD = UNITY`) |
| 저장소 | https://github.com/jk96491/AI_QA (main). 제안서 PDF·`reports/`·venv·Unity 빌드 산출물은 `.gitignore` 로 제외 |
| 테스트 | 79개 통과 (`venv\Scripts\python.exe -m unittest discover -s tests -t .`) |

사용자 우선순위: **성능보다 전체 사이클이 끊김 없이 도는 것.** 단계별로 하나씩 수정.

## 2. 결정 대기 (사용자에게 물어볼 것)

### (해결) 안정형 전사가 학습할수록 클리어를 포기함 — A + C 결정 (2026-11-22)
- **A 반영**: 보상에 페르소나 공통 클리어 실패 벌점 `− fail_penalty·[실패]` (30분, `qa_specs/personas.json` 최상위). 원문 8장과 다른 점으로 `CLAUDE.md`·설계 문서에 기록. 테스트 `tests/learner/test_reward.py`.
- 결과 (0.4.0): 전사 CMA-ES 클리어 0% → **92%**, IMPALA 0% → **96%** (사망 2.1~2.2). 3장 표 참고.
- **C 요청서 작성**: `unity_game/WARRIOR_BALANCE_REQUEST.md` (전사 손튜닝 클리어 ≥60%·사망 ≤1.5). **사용자가 Unity 에이전트에게 전달 필요.**
- 남은 점: 학습 후에도 사망 ~2회 — 부활을 쓰는 클리어가 여전히 최적. C 반영 빌드에서 다시 측정.

### 학습 쪽 하드코딩 제거 여부 (포트폴리오 전, 2026-11-22 제안)
- 핵심 주장 "학습할 대상은 필요한 쪽(게임)이 정의서로 선언, RL 은 그것만 학습" 과 어긋나는 하드코딩이 남아 있다 (6장): 페르소나 파라미터 이름(θ, φ), 정책 출력 파라미터 목록, 트리거 종류 `boss_hp_below`.
- 제안: 포트폴리오 전에 describe 로 받게 고친다 (권장) / 또는 포트폴리오에 한계로 적는다. **사용자 미결정.**

## 3. 빌드별 측정 이력 (stable, 평가 시드)

측정 도구: `run/run_measure_build.py` (PyCharm `12 빌드 측정`).

| 빌드 | 바뀐 점 | 전사 손튜닝 | 마법사 손튜닝 | 궁수 손튜닝 | 학습 후 |
|---|---|---|---|---|---|
| 0.2.0 (프로토콜 1.1) | 최초 | 클리어 57%, 사망 0.07 | 99%, 사망 0.60 | 100%, 321s | 전사 IMPALA 86%, **멈춘 판 3%** (생존 블록에서 못 빠져나옴) |
| 0.3.0 (1.2) | stalled 필드, 생존 블록 최대 12초, 회복 0.8%/s·7초 | 23%, 사망 3.77 | 0%, 사망 4.00 | 100%, 335s | 전사 CMA 98%·IMPALA 94% 이지만 **사망 2~3회 = 부활을 회복으로 이용** |
| 0.4.0 (1.2) | 부활 체력 50%·대기 25초, 회복 1.2%/s·6초, 손튜닝 재조정 | **55%**, 사망 3.06 | **62%**, 사망 2.75 | 100%, 329s | 마법사 CMA 89%(사망 1.75) / **전사 CMA·IMPALA 클리어 0%** (2장 문제) |
| 0.4.0 + 보상 A | (학습 쪽) 클리어 실패 벌점 30분 | 55%, 사망 3.06 | 62%, 사망 2.75 | 100%, 329s | 전사 CMA **92%**(사망 2.14, 451s)·IMPALA **96%**(2.21, 431s) / 마법사 CMA 90%(1.70) |

멈춘 판: 0.3.0 이후 모든 조건 0%.
0.4.0 + 보상 A 측정: `reports/20261122-182126`. 0.4.0 측정 리포트: `reports/20261122-181822` (run_measure_build.py), 전체 사이클: `reports/20261122-181455`.

## 4. Unity 쪽 요청 현황 (`unity_game/`)

| 문서 | 내용 | 상태 |
|---|---|---|
| `AGENT_GUIDE.md`, `CLAUDE.md` | 제작 규칙 | 유지 |
| `PROTOCOL_UPDATE_1.2.md` | stalled 필드, 생존 블록 최대 유지 | 반영됨 (0.3.0) |
| `VIEWER_REQUEST.md` | `-qaFollow`, `-qaViewSpeed`, `-qaPanel` | 반영됨 |
| (구두) 회복·부활 조정 | 0.3.0, 0.4.0 에서 반영 | 반영됨 |
| `WARRIOR_BALANCE_REQUEST.md` | 전사가 적게 죽고 깨도록 (결정 C) | **전달 대기** |

Unity 에이전트에게 지시할 때는 사용자가 직접 전달한다 (학습 쪽은 `unity_game/` 코드를 고치지 않음).

## 5. 다음 세션 시작 방법

1. `AI_QA` 폴더에서 Claude Code 시작 (기억 파일이 이 폴더 기준).
   - **다음 작업 = 포트폴리오 문서** (사용자 결정 2026-11-22): `docs/PORTFOLIO_PLAN.md` 부터 읽는다.
2. 새 빌드 측정 요청이 오면: `venv\Scripts\python.exe run/run_measure_build.py` → 결과를 3장 표에 한 줄 추가.
3. 사이클 확인: `venv\Scripts\python.exe run/run_full_cycle.py` (맨 위 `GAME_CMD = UNITY`), 화면은 `run/run_full_cycle_view.py`.
4. C 반영 빌드(0.5.0 예상)가 오면 측정 → 전사 손튜닝 클리어 ≥60%·사망 ≤1.5 인지, 학습 후 사망이 줄었는지 확인.

## 6. 미구현·알려진 한계

- 정책 다시 불러오기(ES `policy.json`, IMPALA `impala_model.pt`) 로 평가·이어 학습하는 명령 없음
- 학습 체크포인트·재개, 액터 재접속, TLS (클라우드 전 필요 — `DISTRIBUTED.md`)
- 학습 쪽 하드코딩: 페르소나 파라미터 이름(θ, φ), 정책 출력 파라미터, 트리거 종류 `boss_hp_below`
- E1~E7 본 실행은 아직 안 함 (축소 실행만)
- 블랙보드 공통 성향값(원문 6장), 목표 난이도 역산(E8) 미구현
