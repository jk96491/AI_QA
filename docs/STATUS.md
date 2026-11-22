# 현재 상태 · 이어서 할 일 (2026-11-23 기준)

> 새 세션은 이 문서부터 읽는다. 구조·규칙은 `../CLAUDE.md`, 게임 계약은 `PROTOCOL.md`(v1.2), 플레이 모드 계약은 `PLAY_PROTOCOL.md`(v0.2).

## 1. 지금 어디까지 왔나

| 영역 | 상태 |
|---|---|
| 학습 플랫폼 `balance_qa` | 완료: 평가·CMA-ES·ES 정책·**IMPALA**(Beta Actor-Critic, V-trace, torch CPU)·민감도·리포트 |
| IMPALA 액터 | 로컬 다중 프로세스(기본) / threads / external(클라우드 대비). 클라우드 보강 항목은 `DISTRIBUTED.md` 4장 |
| 게임 대역 `game_sim` | 참조 구현 + 테스트용 (지우지 않음). 프로토콜 1.2, 버전 0.4.0 |
| 실제 게임 `unity_game` (QaArena) | 다른 에이전트가 제작. **0.6.2** 빌드: 밸런스 적합성 15/15, 판당 1~2 ms + **플레이 모드**(`-qaPlay`, P1~P4) |
| 플레이 클라이언트 `play_agent` | 2026-11-23 구현: PlayClient·LoadoutBuilder·CombatResponder(IMPALA numpy)·LlmPilot·`check-play`. 0.6.2 로 **check-play 106/106** (T9 = 학습 결과로 필드 늑대왕 처치 + 밸런스 결과 일치). **LlmPilot 실제 API 실행은 아직** (Python ≥3.10 없음) |
| 화면 보기 | `--view N` / PyCharm `00b 전체 사이클 (Unity 화면)` — 창 4개, `-qaFollow -qaViewSpeed 8` 자동 |
| 전체 사이클 | Unity 0.4.0 으로 6단계 PASS (`run/run_full_cycle.py`, `GAME_CMD = UNITY`). 0.6.2 는 Unity 쪽이 PASS 보고 |
| 저장소 | https://github.com/jk96491/AI_QA (main). 제안서 PDF·`reports/`·venv·Unity 빌드 산출물은 `.gitignore` 로 제외 |
| 테스트 | 94개 통과 (`venv\Scripts\python.exe -m unittest discover -s tests -t .`, `tests/play` 포함) |

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

### (결정 대기) 플레이 모드: 잘못된 `trigger_response` 처리 — 2026-11-23
- 0.6.2: 형식·이름·범위가 틀린 응답이 오면 error 를 보내고 **같은 trigger 를 계속 기다림** (밸런스 모드는 판 중단).
- 권장: **그대로 유지**. 중단으로 바꾸면 클라이언트 버그가 "전투 패배 → 부활" 이라는 게임 결과로 둔갑해 플레이 로그를 오염시킨다. `play_agent` 는 전투 중 error 를 받으면 세션을 끝낸다 (이미 구현).
- 중단을 고르면 `unity_game/PLAY_PROTOCOL_0.2_FOLLOWUP.md` 에 F5 로 추가. **사용자 미결정.**

### 밸런스 발견 후보: 늑대왕(`forest_wolf_king`) 에 마법사 0% — 2026-11-23
- Unity 보고 (손 튜닝 default, stable 200판): warrior 60% / **mage 0%** / archer 97%. 학습 쪽 재측정·학습은 아직 (마법사 CMA-ES 로 0% 가 파라미터 문제인지 보스 설계 문제인지 가르는 것이 다음).
- 주의: `describe.scenarios` 에 `forest_wolf_king` 이 생겼다 — **패치가 아니라 다른 보스**. `experiments` 의 패치 목록(e2 `PATCHES`, e3 `SCENARIOS`)은 이름을 명시해서 영향 없음을 확인. "base 외 시나리오 = 패치" 로 가정하는 코드를 만들지 않는다.

### 플레이 모드 (LLM 비전투 + 학습 BT 전투) — 2026-11-22 착수, 2026-11-23 Unity·학습 쪽 구현
- **두 모드 (사용자 확정)**: 학습 = 전투로 바로(밸런스 모드) / 플레이 = 항상 게임 처음부터(`reset` = 새 게임).
- Unity 0.6.2: P1~P4 완료, 자체 검증 96/96, T5(플레이 조우 result == 밸런스 run_episode) 확인 — `unity_game/PLAY_MODE_REPORT.md`.
- 계약 `docs/PLAY_PROTOCOL.md` **v0.2** 로 확정 (보고서 2장 결정 전부 수용). 0.6.2 미반영 3건 → `unity_game/PLAY_PROTOCOL_0.2_FOLLOWUP.md` (**전달 대기**): F1 버전 "0.2", F2 `unknown_boss`→`boss_mismatch`, F3 보스 결계 `barrier_restore`·`field_state`. `play_agent` 는 그동안 0.1 접속·두 코드 모두 처리.
- `play_agent/` (표준 라이브러리 + numpy, Python 3.8 OK. LlmPilot 만 anthropic SDK 1.x → Python ≥3.10 별도 venv):
  - `PlayClient` (act 중 전투 메시지 수집·trigger 즉답), `LoadoutBuilder` (params.json/policy.json → set_loadout, 키 (class, scenario)), `CombatResponder` (IMPALA 정책 numpy 순전파 — torch 와 1e-5 이내 일치 테스트), `tools.py` (play_description.actions → strict 도구), `LlmPilot` (claude-opus-5-5, effort low, 캐싱, 상한·진척 없음 감지), `check.py` (`python -m play_agent check-play`, PyCharm `13 플레이 모드 검사`).
  - **정책 다시 불러오기**: 학습 쪽 `ActorParamSource.describe()` 가 `output_ranges`·`fixed`·`state_features`·`obs_dim`·`hidden` 을 policy.json 에 싣도록 바꿈 (2026-11-23). 그 전 policy.json 은 다시 불러올 수 없다 (이유를 말하고 거부).
  - 확인 (0.6.2): `check-play --exe ... --loadout reports/20261123-003306` **106/106**. T9: IMPALA(warrior/늑대왕 1,600판, 클리어 60→99%) 정책이 트리거 4회 즉답하며 첫 조우 처치, CMA(`reports/20261123-001010`)도 첫 조우 처치, 둘 다 밸런스 run_episode 와 result 일치.
- 남은 것: LlmPilot 실제 실행 (Python ≥3.10 venv + `ANTHROPIC_API_KEY` 필요 — 사용자 준비), 같은 튜토리얼 N회 배치 실행·실패 지점 통계, MCP 래퍼(선택), v0.3 시작 상태 이어받기(필드 피해원이 생긴 뒤).

## 3. 빌드별 측정 이력 (stable, 평가 시드)

측정 도구: `run/run_measure_build.py` (PyCharm `12 빌드 측정`).

| 빌드 | 바뀐 점 | 전사 손튜닝 | 마법사 손튜닝 | 궁수 손튜닝 | 학습 후 |
|---|---|---|---|---|---|
| 0.2.0 (프로토콜 1.1) | 최초 | 클리어 57%, 사망 0.07 | 99%, 사망 0.60 | 100%, 321s | 전사 IMPALA 86%, **멈춘 판 3%** (생존 블록에서 못 빠져나옴) |
| 0.3.0 (1.2) | stalled 필드, 생존 블록 최대 12초, 회복 0.8%/s·7초 | 23%, 사망 3.77 | 0%, 사망 4.00 | 100%, 335s | 전사 CMA 98%·IMPALA 94% 이지만 **사망 2~3회 = 부활을 회복으로 이용** |
| 0.4.0 (1.2) | 부활 체력 50%·대기 25초, 회복 1.2%/s·6초, 손튜닝 재조정 | **55%**, 사망 3.06 | **62%**, 사망 2.75 | 100%, 329s | 마법사 CMA 89%(사망 1.75) / **전사 CMA·IMPALA 클리어 0%** (2장 문제) |
| 0.4.0 + 보상 A | (학습 쪽) 클리어 실패 벌점 30분 | 55%, 사망 3.06 | 62%, 사망 2.75 | 100%, 329s | 전사 CMA **92%**(사망 2.14, 451s)·IMPALA **96%**(2.21, 431s) / 마법사 CMA 90%(1.70) |
| 0.6.2 (1.2) | 0.5.0 전사 방어력 0.6·손튜닝 재조정(결정 C 반영) + 늑대왕 시나리오 + 플레이 모드 | **62%, 사망 1.01** (C 목표 ≥60%·≤1.5 충족) | 62%, 사망 2.75 | 100%, 329s | 전사 CMA **100%**(사망 0.67, 367s)·IMPALA **100%**(0.63, 371s) / 마법사 CMA 90%(1.70, 460s) |

멈춘 판: 0.3.0 이후 모든 조건 0%.
0.6.2 측정: `reports/20261123-002152` (25초). 0.4.0 + 보상 A 측정: `reports/20261122-182126`. 0.4.0 측정 리포트: `reports/20261122-181822` (run_measure_build.py), 전체 사이클: `reports/20261122-181455`.

## 4. Unity 쪽 요청 현황 (`unity_game/`)

| 문서 | 내용 | 상태 |
|---|---|---|
| `AGENT_GUIDE.md`, `CLAUDE.md` | 제작 규칙 | 유지 |
| `PROTOCOL_UPDATE_1.2.md` | stalled 필드, 생존 블록 최대 유지 | 반영됨 (0.3.0) |
| `VIEWER_REQUEST.md` | `-qaFollow`, `-qaViewSpeed`, `-qaPanel` | 반영됨 |
| (구두) 회복·부활 조정 | 0.3.0, 0.4.0 에서 반영 | 반영됨 |
| `WARRIOR_BALANCE_REQUEST.md` | 전사가 적게 죽고 깨도록 (결정 C) | 반영됨 (0.5.0, 0.6.2 측정으로 확인) |
| `PLAY_MODE_REQUEST.md` | 플레이 모드: 마을·숲 튜토리얼, 구조화 관찰, 고수준 행동, 전투 → `CombatSim`+학습 BT 인계 | 반영됨 (0.6.2, `PLAY_MODE_REPORT.md`) |
| `PLAY_PROTOCOL_0.2_FOLLOWUP.md` | v0.2 미반영 3건: 버전 0.2, `boss_mismatch`, 보스 결계·`field_state` | **전달 대기** (2026-11-23) |

Unity 에이전트에게 지시할 때는 사용자가 직접 전달한다 (학습 쪽은 `unity_game/` 코드를 고치지 않음).

## 5. 다음 세션 시작 방법

1. `AI_QA` 폴더에서 Claude Code 시작 (기억 파일이 이 폴더 기준).
   - **다음 작업 = 포트폴리오 문서** (사용자 결정 2026-11-22): `docs/PORTFOLIO_PLAN.md` 부터 읽는다.
2. 새 빌드 측정 요청이 오면: `venv\Scripts\python.exe run/run_measure_build.py` → 결과를 3장 표에 한 줄 추가.
3. 사이클 확인: `venv\Scripts\python.exe run/run_full_cycle.py` (맨 위 `GAME_CMD = UNITY`), 화면은 `run/run_full_cycle_view.py`.
4. 플레이 모드 확인: `venv\Scripts\python.exe -m play_agent check-play --exe unity_game/Build/QaArena.exe [--loadout reports/<run>]` (PyCharm `13 플레이 모드 검사`).

## 6. 미구현·알려진 한계

- 정책 다시 불러오기: IMPALA `policy.json` 은 `play_agent` 가 numpy 로 불러 쓴다 (2026-11-23 이후 파일만). 학습 쪽(`balance_qa`)에서 불러와 평가·이어 학습하는 명령, ES `policy.json` 불러오기는 아직 없음
- 학습 체크포인트·재개, 액터 재접속, TLS (클라우드 전 필요 — `DISTRIBUTED.md`)
- 학습 쪽 하드코딩: 페르소나 파라미터 이름(θ, φ), 정책 출력 파라미터, 트리거 종류 `boss_hp_below`
- E1~E7 본 실행은 아직 안 함 (축소 실행만)
- 블랙보드 공통 성향값(원문 6장), 목표 난이도 역산(E8) 미구현
