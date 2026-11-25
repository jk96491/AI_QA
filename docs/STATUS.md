# 현재 상태 · 이어서 할 일 (2026-11-24 기준)

> 새 세션은 이 문서부터 읽는다 — **먼저 5장 맨 위 "다음 세션 할 일"**. 구조·규칙은 `../CLAUDE.md`, 게임 계약은 `PROTOCOL.md`(**v1.4**), **SDK 는 `SDK.md`**(0.2.0), 플레이 모드 계약은 `PLAY_PROTOCOL.md`(**v0.3**), 밴딧 설계 `BANDIT_IMPALA_DESIGN.md`, LLM 연결 `LLM_SETUP.md`.
> 현재 Unity 빌드 **QaArena 0.8.3** (2026-11-24 20:34, `unity_game/REPORT_0.8.3.md`): 밸런스 **1.4 `initial_state` 반영**, 플레이 `play_description` 에 행동 설명·스키마·`pilot_guide`·`progress_keys` **게임 선언** (외부 스펙 없이 동작), 화면 H1·H3·H4. 밸런스 데이터 변경 없음 (T1 21/21) → 재학습 불필요. 플레이 0.4·0.3 hello 둘 다 받음.

## 1. 지금 어디까지 왔나

| 영역 | 상태 |
|---|---|
| **BT-QA SDK 0.3.0** (2026-11-24) | **별도 GitHub 레포 https://github.com/jk96491/btqa_sdk** (0.1.0 = `5627219`, 0.2.0 = `6c71e4c`, 0.3.0 = `42ab358` `btqa_play` 추가, 푸시됨). 로컬 clone `btqa_sdk/` (git 제외). **Python 은 btqa_sdk 직접 참조** (venv 편집 설치 `pip install --no-deps --no-build-isolation -e ./btqa_sdk`, 사용자 결정 2026-11-24 — 루트 `btqa_game/`·`btqa_play/` 사본 없앰). 사본은 Unity 패키지·`docs/PROTOCOL.md`·`docs/PLAY_PROTOCOL.md` 3개만 (`run/run_sync_sdk.py`). **학습 대상 = 블록 가중치뿐** (CMA-ES 포함). `docs/SDK.md` |
| **BT-QA Play SDK `btqa_play` (SDK 0.3.0, 2026-11-24)** | LLM 플레이어 클라이언트를 SDK 로 옮김 (`btqa_sdk/python/btqa_play`, 직접 참조): PlayClient·LLM 도구(게임 선언 → **외부 스펙** → 일반형, **SDK 에 게임 내용 없음** — 사용자 지적·결정 2026-11-24)·시스템 프롬프트(SDK 공통 = 도구 사용 방식만 + `pilot_guide`)·`PlaySpec`(`btqa-play-spec/1`, QaArena = `play_agent/specs/qa_arena.play.json`)·진척 `progress_keys`·LlmPilot·PilotRelay(`prepare`/`run_meta` 확장)·LLM 백엔드·`python -m btqa_play tools`. 계약 `PLAY_PROTOCOL.md` 원본도 SDK 레포로 (0.3 + **선택 필드 4.2.1**, hello 버전 유지). `play_agent` = SDK + 로드아웃·응답기·check-play(T-D 추가). 테스트: 메인 120 OK, SDK 26 OK, **check-play 127/127** (0.8.2, 행동 6개 모두 QaArena 스펙에서). |
| 학습 플랫폼 `balance_qa` | 완료: 평가·CMA-ES·ES 정책·**IMPALA**(Beta Actor-Critic, V-trace, torch CPU)·민감도·리포트 |
| IMPALA 액터 | 로컬 다중 프로세스(기본) / threads / external(클라우드 대비). 클라우드 보강 항목은 `DISTRIBUTED.md` 4장 |
| 게임 대역 `game_sim` | 참조 구현 + 테스트용 (지우지 않음). 프로토콜 1.3, 버전 0.5.0 (`btqa_game` 위에서 동작) |
| 실제 게임 `unity_game` (QaArena) | 다른 에이전트가 제작. **0.7.0** (SDK 도입은 학습 쪽 세션이 직접 반영 — `unity_game/SDK_MIGRATION.md`): 적합성 16/16, edge 37/37, 판 결과 0.6.2 와 21/21 동일, check-play 126/126 (0.7.1) + **플레이 모드**(`-qaPlay`, P1~P4) |
| 플레이 클라이언트 `play_agent` | 2026-11-23 구현: PlayClient·LoadoutBuilder·CombatResponder(IMPALA numpy)·LlmPilot·`check-play`. **check-play 126/126** (0.7.1, play v0.3: T-P 물약·T-N 메모 포함, T9 = 학습 결과로 필드 늑대왕 처치 + 밸런스 결과 일치). LLM 은 각자 고른다(`play_agent/llm/`, `docs/LLM_SETUP.md`); 실제 플레이는 `relay`(Claude Code 세션) 로 2회 — API·로컬 LLM 실제 실행은 아직 |
| 화면 보기 | `--view N` / PyCharm `00b 전체 사이클 (Unity 화면)` — 창 4개, `-qaFollow -qaViewSpeed 8` 자동 |
| 전체 사이클 | Unity **0.7.0** 으로 6단계 PASS (`reports/20261123-193621`, IMPALA 출력 = 가중치 3개) |
| 저장소 | https://github.com/jk96491/AI_QA (main). 제안서 PDF·`reports/`·venv·Unity 빌드 산출물은 `.gitignore` 로 제외 |
| 테스트 | 106개 통과 (`tests/sdk`: 가중치만 학습 규칙, SDK 사본 검사 — 원본 없으면 비교 1개 건너뜀) + SDK 레포 자체 9개 (`venv\Scripts\python.exe -m unittest discover -s tests -t .`, `tests/play` 포함) |

사용자 우선순위: **성능보다 전체 사이클이 끊김 없이 도는 것.** 단계별로 하나씩 수정.

## 2. 결정 대기 (사용자에게 물어볼 것)

### (해결) 안정형 전사가 학습할수록 클리어를 포기함 — A + C 결정 (2026-11-22)
- **A 반영**: 보상에 페르소나 공통 클리어 실패 벌점 `− fail_penalty·[실패]` (30분, `qa_specs/personas.json` 최상위). 원문 8장과 다른 점으로 `CLAUDE.md`·설계 문서에 기록. 테스트 `tests/learner/test_reward.py`.
- 결과 (0.4.0): 전사 CMA-ES 클리어 0% → **92%**, IMPALA 0% → **96%** (사망 2.1~2.2). 3장 표 참고.
- **C 요청서 작성**: `unity_game/WARRIOR_BALANCE_REQUEST.md` (전사 손튜닝 클리어 ≥60%·사망 ≤1.5). **사용자가 Unity 에이전트에게 전달 필요.**
- 남은 점: 학습 후에도 사망 ~2회 — 부활을 쓰는 클리어가 여전히 최적. C 반영 빌드에서 다시 측정.

### (해결) 학습 쪽 하드코딩 제거 — SDK 로 해결 (2026-11-23)
- 사용자 결정: **RL 은 오직 블록 가중치만 학습**, **페르소나는 원문과 완전히 같을 필요 없음**. CMA-ES 도 가중치만, w 크기 중복은 한계로 기록(정규화 안 함) — 둘 다 권장안 채택.
- 정책 출력 목록(`DEFAULT_POLICY_OUTPUTS`) 제거 → 게임이 선언한 `classes[].blocks` 가중치. 트리거 키 = `describe.triggers.type`. 페르소나 = `params`(가중치가 아닌 값) + λ, 이름은 페르소나 파일에만 있음.

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
| **0.7.0 (1.3) + 가중치만 학습** | SDK 도입 (게임 동작 동일, 21/21). 학습 대상 5~9개 → **블록 가중치 3개** (CMA-ES·IMPALA) | 62%, 사망 1.01 | 62%, 사망 2.75 | 100%, 329s | 전사 CMA **100%**(사망 0.52, 362s)·IMPALA **99%**(0.49, 405s) / 마법사 CMA **89%**(2.06, 434s) |
| 0.6.2 (1.2) | 0.5.0 전사 방어력 0.6·손튜닝 재조정(결정 C 반영) + 늑대왕 시나리오 + 플레이 모드 | **62%, 사망 1.01** (C 목표 ≥60%·≤1.5 충족) | 62%, 사망 2.75 | 100%, 329s | 전사 CMA **100%**(사망 0.67, 367s)·IMPALA **100%**(0.63, 371s) / 마법사 CMA 90%(1.70, 460s) |

| **0.8.1 (1.3) 보스 패턴 + 스킬·BT 확장** | 늑대왕 2D 아레나·낙석·장판·탄막·돌진, 직업 스킬 6~7, **블록 5개**(+`w_evade`·`w_setup`), 새 BT 상수 `combo_window`·`evade_cancel_danger`. default 보스도 결과 바뀜 | **100%**, 사망 0.21, 425s | 81%, 사망 2.25, 390s | 100%, 265s | 전사 CMA 100%(0.30, **260s**)·IMPALA 100%(0.23, 262s) / 마법사 CMA **99%**(1.29, 369s) |
멈춘 판: 0.3.0 이후 모든 조건 0%.
0.8.1 측정: `reports/20261123-230344` (base 시나리오). 스킬 확장으로 default 보스가 쉬워짐 — 손튜닝이 전사·궁수 100% 라 base 는 변별력이 낮다 (학습 이득은 소요 425→260s). **늑대왕(forest_wolf_king) 0.8.1, 전사/stable, n=300**: 손튜닝 50% [45,56]·583s·사망 2.74 → **CMA-ES 3000판 100%·295s·사망 0.86** (`reports/20261123-230419`, w_evade 0.99·w_burst 0.70·w_dps 0.31·w_setup 0.36·w_survival 0.03 — 회피 블록이 결정적) / IMPALA 8000판(트리거 구간 모드) 100%·301s·사망 0.99 (`reports/20261123-230437`). check-play 126/126 (0.8.1 + 이 CMA 로드아웃, 23:0x 빌드). 재플레이 1차는 Unity 세션 build.ps1 이 모든 QaArena 를 종료해 끊김 → 포트 분리(학습 쪽 7800~7809, Unity 7810~7819) 후 **7801 에서 재플레이 완료** `reports/relay-20261123-231158`: 5개 완료, 늑대왕 304s·사망 1, 물약 3→사용 3. 빌드는 play 0.4·0.3 둘 다 받음 (0.4 = computer use, 사용자 판단 대기, 계약은 0.3).
   - **0.8.2** (Unity 보고): 밸런스 변화 없음(T1 21/21 동일 → 재학습 불필요), 월드 이름표(화면만), H2 물약 설명 "필드 30% / 결계 전투 40%" 로 해결, v0.4 raw 입력(0.4 hello 만). 학습 쪽 확인: **check-play 126/126** (0.3 접속, 0.8.1 CMA 로드아웃 그대로).
   - **0.8.2 재플레이 (2026-11-23 23:57, relay + 메모)** `reports/relay-20261123-235751/` (+스크린샷 3장): 5개 완료, 늑대왕 304s·사망 1, 물약 4→3 가져가 3 사용. 이름표·H2 확인. 화면 후속 3건 → `unity_game/UI_FOLLOWUP_0.8.2.md` (H1 대화창 겹침 계속, H3 전투 로그 ↔ QA 패널 겹침, H4 스킬 바 긴 이름 ↔ 쿨 숫자 겹침).
0.7.0 측정: `reports/20261123-193733` (20초). 0.6.2 대비: 전사 CMA 는 같거나 낫고(사망 0.67→0.52), IMPALA 는 소요 371→405s 로 느려짐, 마법사 사망 1.70→2.06 — 물약 체력·자원 비축을 더 이상 학습하지 않는 영향으로 보임 (가중치만 학습의 비용). 단일 실행이라 확정 아님.
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
| `PLAY_PROTOCOL_0.3_REQUEST.md` | pilot_note 표시·전투 물약 = 인벤토리·경비병 안내 (+4장 H1·H2) | 반영됨 (0.7.1~0.8.2). **H1(메모 패널 ↔ 대화창 겹침) 미반영** |
| `BOSS_PATTERN_REQUEST.md` | 늑대왕 2D 아레나·낙석·장판·탄막·돌진 | 반영됨 (0.8.0, `BOSS_PATTERN_REPORT.md`) |
| `PLAYER_SKILL_BT_REQUEST.md` | 스킬 6~7·블록 5개(`w_evade`·`w_setup`)·스킬 바 | 반영됨 (0.8.1, `SKILL_BT_REPORT.md`) |
| `PROTOCOL_UPDATE_1.4.md` | 밸런스 1.4 `initial_state` (QaArenaHost 선언 2줄 + `SetStartHpRatio`) | 반영됨 (0.8.3) |
| `UI_FOLLOWUP_0.8.2.md` | 화면 H1·H3·H4 | 반영됨 (0.8.3, 스크린샷 `QaTools~/shots_0.8.3/`) |
| (Unity → 학습) `PLAY_PROTOCOL_0.4_COMPUTER_USE_REQUEST.md` | 비전 없는 computer use (좌표·raw 입력) — 빌드엔 이미 들어감 (0.4 hello 만) | **사용자 결정 대기** — 계약은 0.3 유지 |
| **`HANDOFF_0.8.3.md`** | 전달용 묶음: 1.4 + PLAY_SDK_DECLARATION + UI_FOLLOWUP_0.8.2 → 0.8.3 한 빌드 | **반영됨 (0.8.3, `REPORT_0.8.3.md`)**. 학습 쪽 확인 (최종 빌드): `btqa_game check` PASS(v1.4 4항목), `check-game` PASS, `play_agent tools --spec none` 6개 모두 game/game·선언 검사 통과, **check-play 127/127** |
| `PLAY_SDK_DECLARATION_REQUEST.md` | 플레이 행동·안내 선언 (4.2.1) | 반영됨 (0.8.3). Unity 가 고친 점: wait 사건 이름(`quest_update` 없음 → 실제 kind), 퀵슬롯 2칸 (스펙 파일도 고침) |
| `SDK_MIGRATION.md` | SDK 도입 (0.7.0) 기록 — 바뀐 파일, 검증, **앞으로 SDK 패키지 수정 금지·블록 추가 방법** | 학습 쪽이 직접 반영 완료. **Unity 에이전트가 다음 작업 전에 읽도록 사용자가 알려 줄 것** |

Unity 에이전트에게 지시할 때는 사용자가 직접 전달한다 (학습 쪽은 `unity_game/` 코드를 고치지 않음).
Unity 쪽은 **별도 Claude Code 세션**(이름 `unity-game-1b`)이 맡고, 세션끼리 메시지를 주고받는다. **포트 약속: 학습 쪽 7800~7809, Unity 쪽 7810~7819.** Unity 의 `build.ps1` 은 모든 QaArena 를 종료하므로 빌드 전에 알려 주기로 했다.

## 5. 다음 세션 시작 방법

### 다음 세션 할 일 (2026-11-25 밤 저장)

**오늘(2026-11-25) 끝난 상태**: 두 레포 모두 커밋·푸시 완료 (SDK `5ab5b04`, AI_QA `8ffd25b`). 돌고 있는 게임·학습·Ollama 모델 없음.
- 증류 최종 = **r8 CPU** (`qa-qwen1.5b-r8`, 5/5). GPU 변형 `qa-qwen1.5b-r8-gpu` 는 1/5. DAgger 4 → **r12** (`qa-qwen1.5b-r12`, `-gpu`) GPU 3/5 — 상인 장면(상인 앞에서 인벤토리 열기 → 닫힌 창 '닫기' 반복)에서 막힘, **CPU 는 미평가**. 모델은 `distill_out/r*` 와 Ollama 에만 (커밋 금지).
- 증류 코드는 SDK 훅 구조로 정리 (`docs/DISTILL.md` 3장 "증류 한 바퀴"): `btqa_play dataset --prep --correction-weight` / `pairs` / `approve`, `btqa_distill export/gpu-variant/rft`. `play_agent` 는 함수만 (`distill_prep`, `distill_reward`).
- 녹화: `reports/recordings/r8_cpu_seed1{.mp4,_skip.mp4,.gif}` (git 제외), README GIF `docs/media/distilled_play.gif`. README 에 증류 장·Limitations 현행화.
- **녹화 다시 할 때 ffmpeg 필요**: 오늘 쓴 ffmpeg 는 세션 임시 폴더라 사라진다 → `winget install Gyan.FFmpeg` (PATH) 또는 3.9+ venv 에 `pip install imageio-ffmpeg` 후 그 exe 를 환경변수 `FFMPEG` 로. `run/run_record_play.py` 는 FFMPEG → PATH → imageio_ffmpeg 순서로 찾는다.

**다음 후보 (증류, 선택)**: ① r12 CPU 평가 (`play_agent batch ... --model qa-qwen1.5b-r12 --seeds 1-5`, 7801) — CPU 5/5 를 유지하면 r12 가 CPU·GPU 모두 나은 모델 ② GPU 학생(r12-gpu)으로 DAgger 5: 상인 앞(가까움)·창 없음 → talk, 닫힌 인벤토리에서 '닫기' 실패 직후 → 상인 talk. **승인은 `btqa_play approve 1` 로 하나씩** (몰아서 승인하다 두 번 라벨을 고쳤다) → `btqa_play dataset ... --correction-weight 3 --prep play_agent.distill_prep:prep_sample` → r13 ③ 다른 직업(궁수·마법사)으로 평가 ④ 0.5B 비교. 그 밖의 일은 아래 1~6.

00. **증류 — 완료 (2026-11-25, `docs/DISTILL.md` 6·7장)**: **Qwen2.5-1.5B LoRA `qa-qwen1.5b-r8` (Q4_K_M, CPU ~8s/호출) 가 튜토리얼 5개를 seed 1~5 모두 완주** (원본 0/5). 경로: SFT(교사 7판) → 상황 읽기 thought 접두 → DAgger 3회(교정 15) → 입력에서 옮겨 적는 단서 4종(대상 보임/없음·거리·목표 글=버튼·창 버튼 글=id, `play_agent/distill_prep.py`). DPO(r9, 쌍 18개)는 강·약 모두 1/5 로 후퇴 (실패 사례로 기록), RFT(r10, GRPO, 게임 채점기)는 보상 해킹(창 안 반복 클릭 +0.2)으로 3/5 → 보상 수정 후 r11 은 0/5 로 붕괴 (DPO 와 같이 작은 정책 변화에 갈림길이 뒤집힘). **최종 = r8**. 학습 loss 답 구간 logits 만(`logits_to_keep`)으로 3060 메모리 넘침 해소. 데이터 백업 `distill_data/` (모델은 커밋 금지). 재생 `run/run_play_local.py` (PyCharm 16), 녹화 `run/run_record_play.py` (PyCharm 17, mp4·대기 제거 mp4·gif → `reports/recordings/`). **GPU 추론 주의**: 같은 r8 가중치가 GPU 에서는 1/5 (갈림길이 뒤집혀 반복) → DAgger 4 (GPU 학생) → r12 는 GPU 3/5 (상인 장면에서 막힘, CPU 미평가) — 최종은 r8 CPU 유지. 정리 (2026-11-25): 게임 고유 처리(전처리·보상·판 준비)는 `play_agent` 함수, SDK 명령에 `'모듈:함수'` 훅으로 (`dataset --prep --correction-weight`, `pairs`, `approve`, `btqa_distill export/gpu-variant/rft`) — `play_agent` 는 torch·`btqa_distill` 을 import 하지 않는다 (`play_agent/distill_run.py` 제거). 다음(선택): r12 CPU 평가, 상인 장면 DAgger 5 (GPU), 다른 직업 교사 판, 0.5B 비교.
   이전 기록: : 1단계 완료 — SDK 0.4.0 `btqa_play` 단계 형식(`stateless`)·`JsonActionBackend`(`tool_mode json`)·`StepRecorder`(+grounding)·`observation_drop`, relay `--record`, `play_agent batch`. 실제 0.8.3 에서 교사 기록 4단계 확인 (`reports/distill/smoke_teacher.jsonl`, grounding 0, step 입력 1.1~1.7천 자). **기준선 완료**: `qwen2.5-1.5b-cpu`(CPU 전용 변형) seed 1~3 → 퀘스트 0/5, 형식 오류 0%, 호출당 4.2s (상인 대화창에서 talk 반복 → no_progress). SDK 0.4.0 에 평가(`btqa_play batch`)·데이터셋(`btqa_play dataset`)·**선택 패키지 `btqa_distill`**(LoRA·GGUF·Ollama CPU) 추가 (사용자: SDK 본연의 역할). **모델 파일 커밋 금지** (.gitignore·테스트·pre-commit hook). **0.8.4 (시야 밖 퀘스트 대상 `known: marker`) 반영·확인** — id 이동만으로 튜토리얼 완료, grounding 0. **교사 데이터 7판** `reports/distill/teacher.jsonl` (전사 s1·s4 완료, 궁수 s3 완료·s5 2연패 막힘, 마법사 s2·s6 2연패 막힘, 확인 플레이 1판 포함 219단계) → `distill_out/data/v1` train 185 / val 32, 행동 충돌 0, 생각 문장 변형 93. `venv_distill`(torch 2.6 cu124·transformers·peft, RTX 3060 OK) + llama.cpp b12675(`distill/llama.cpp`, 변환 의존성) 설치 완료. 로컬 LLM 화면 보기 `run/run_play_local.py`(PyCharm 16). 다음: 첫 LoRA 학습(1.5B, 217샘플) → GGUF → Ollama CPU → batch 비교, 그다음 교정(DAgger) 데이터.

0. **(2026-11-24 저녁) 플레이 클라이언트 SDK화 후속**: SDK 레포(`btqa_sdk/`, 0.3.0) 커밋·푸시 + 메인 저장소 커밋 (사용자 확인 후). `unity_game/PLAY_SDK_DECLARATION_REQUEST.md` 전달 → 빌드가 오면 `python -m btqa_play tools --game ...` 로 출처가 전부 `game/game` 인지, check-play T-D. 다음 단계 후보: MCP 래퍼(`GameTools` → MCP 도구), 게임 쪽 플레이 서버 SDK(Unity C#), 공용 플레이 적합성 검사 (`btqa_sdk/docs/PLAY_SDK.md` 7장).

1. **Unity 1.4 반영 확인 — 완료 (0.8.3, 2026-11-24)**. 남은 것:
   `python -m btqa_game check --game ...` + `venv\Scripts\python.exe -m balance_qa check-game --game-cmd ...` (initial_state 항목 PASS) →
   **E8 을 늑대왕으로**: `venv\Scripts\python.exe -m experiments.e8_bandit --workers 8 --game-cmd "unity_game/Build/QaArena.exe -batchmode -nographics -qaPort {port}" --combos warrior:forest_wolf_king` (첫 판은 `--quick`, 본 실행은 칸당 판수·예산을 키워서). 결론 전 `/bt-sim-balance-review`.
   game_sim E8 결과(밴딧 이득 없음)는 아래 기록 — Unity 에서 다시 판정.
2. **`unity_game/UI_FOLLOWUP_0.8.2.md` 전달** (사용자 → Unity 세션): H1·H3·H4 화면 겹침.
3. **사용자 결정 대기**: 플레이 v0.4 computer use 진행 여부 (진행하면 `PLAY_PROTOCOL.md` 0.4 로 올리고 `play_agent` 클라이언트 대응), 2장의 잘못된 `trigger_response` 처리.
4. 플레이 모드 재플레이는 `relay` 방식 (Claude Code 세션이 플레이어, API 과금 없음 — 사용자 결정): 창 게임 `QaArena.exe -qaPlay -qaPort 7800 -qaPlaySpeed 4` + `python -m play_agent relay --game 127.0.0.1:7800 --loadout reports/20261123-230419` (0.8.1 CMA 늑대왕) + `step <tool> '<json>' --think "..." --kind plan|thought|finding`. PowerShell 은 JSON 따옴표를 망가뜨리니 Bash 로. 화면 확인은 창 스크린샷 (전투 중엔 지연 캡처).
5. 최신 학습 결과 (0.8.1, 0.8.2 도 밸런스 동일): 늑대왕 전사 CMA `reports/20261123-230419` (100%, 295s, w_evade 0.99), IMPALA 구간 모드 `reports/20261123-230437` (100%, 301s). base: `reports/20261123-230344`.
6. 남은 큰 일: 포트폴리오 문서 (`docs/PORTFOLIO_PLAN.md`), 로컬·API LLM 실제 실행(아직 가짜 전송 테스트만), 밴딧 컨텍스트에 페르소나 λ·플레이 기록 분포(`ContextSampler`) — 설계 9장.

### 처음 시작할 때

1. `AI_QA` 폴더에서 Claude Code 시작 (기억 파일이 이 폴더 기준).
   - **다음 작업 = 포트폴리오 문서** (사용자 결정 2026-11-22): `docs/PORTFOLIO_PLAN.md` 부터 읽는다.
2. 새 빌드 측정 요청이 오면: `venv\Scripts\python.exe run/run_measure_build.py` → 결과를 3장 표에 한 줄 추가.
3. 사이클 확인: `venv\Scripts\python.exe run/run_full_cycle.py` (맨 위 `GAME_CMD = UNITY`), 화면은 `run/run_full_cycle_view.py` (학습하면서) / **`run/run_watch.py` (저장된 결과만 재생, PyCharm `00c`)**, 플레이 모드(마을부터)는 **`run/run_watch_play.py` (PyCharm `00d`)** — 0.7.0 forest_wolf_king 학습 결과: CMA `reports/20261123-203248` (클리어 60→100%), IMPALA `reports/20261123-203257` (99%, 341s).
4. 플레이 모드 확인: `venv\Scripts\python.exe -m play_agent check-play --exe unity_game/Build/QaArena.exe [--loadout reports/<run>]` (PyCharm `13 플레이 모드 검사`).
5. **LLM 플레이 — 첫 실제 실행 완료 (2026-11-23, API 대신 Claude Code 세션이 플레이어)**: 사용자 결정 = API 추가 비용 없이 정액제 Claude Code 가 직접 플레이. `python -m play_agent relay --game 127.0.0.1:7800 --loadout reports/20261123-003306` (3.8 venv, 연결 유지) + 매 행동 `python -m play_agent step <tool> '<json>'`, `finish` 로 기록 저장. 결과 `reports/relay-20261123-215152`: 튜토리얼 5개 전부 완료, 행동 76, 늑대왕 학습 BT 클리어(308s, 사망 1). 발견 3건 (버그 아님·개선): ① npc_guard 위치 안내 없음 (일지·대화·hint_targets 모두 id 뿐, 마을 (34,-22) 은 탐색으로 못 찾아 world.json 을 보고 감) ② 상점 구매 버튼 interactable 규칙 불일치 (20G 일 때 25G 버튼 true·80G 버튼 false; 클릭하면 purchase_failed 로 안전) ③ 전투 중 사망 1회인데 퀵슬롯 물약 4개 그대로 — 계약 6장 결정(조우 시작 full, 물약은 학습 판 기준)대로지만 화면 설명이 없음 (②는 코드상 의도된 함정 `WorldState.cs:395`).
   - **Unity 에 전달할 요청 `unity_game/PLAY_PROTOCOL_0.3_REQUEST.md`** (사용자 요청 2026-11-23): 플레이어 생각을 게임 화면에 표시하는 `pilot_note` (PLAY_PROTOCOL **v0.3** 4.10, 패널·말풍선·토스트) + G1 경비병 위치 안내 + G3 결계 안내 문구. 학습 쪽은 구현 완료: `PlayClient.note()`, `step --think "..." --kind thought|plan|finding`, LlmPilot 텍스트→thought, hello 0.3→0.2→0.1. 0.7.0 은 아직 play 0.1 만 받아 메모는 `run.json.pilot_notes` 에만 남는다.
   - **사용자 결정 2026-11-23: 전투에서 인벤토리 물약을 쓴다** → 계약 v0.3 4.7·6장, 요청서 3장 C1~C5 (퀵슬롯 물약 `carried=min(보유, cap)`, 회복량은 전투 규칙, 사용분 차감). `PlayClient` 전투 요약에 `potions`·`potions_used`·`out_of_training_dist`.
     후속(학습 쪽): carried<cap 전투는 학습 분포 밖 → 밸런스 프로토콜 `run_episode.initial_state.potions`(SDK 원본 레포) + 시작 물약을 섞은 재학습.
   - **0.7.1 재플레이 (2026-11-23 22:18, relay + 생각 메모)** `reports/relay-20261123-221805/` (+`play_notes.png`): 5개 완료, 행동 43(첫 판 76), 메모 35개 전부 화면 표시, 경비병을 안내만으로 찾음, 전투 물약 4→carried 3→사용 3→잔여 1, 클리어 324s·사망 1. 후속 H1(메모 패널이 대화창 글자와 겹침)·H2(물약 30%↔40%) → 요청서 4장. `play_agent/check.py` v0.3 반영 완료 (T-P 물약·T-N 메모 이식, T5·T9 는 carried == cap 조우만 밸런스 비교, T9 도 물약 준비) → **check-play 126/126 PASS** (0.7.1, CMA 로드아웃).
   - **보스 패턴 고도화 요청 (사용자 요청 2026-11-23)** `unity_game/BOSS_PATTERN_REQUEST.md`: 늑대왕만, 1D 거리 → 2D 아레나, 낙석(경고 원)·독 장판·부채꼴 탄막·돌진 띠·페이즈 조합, 피하기 = 생존 블록 필요도에 `danger` (학습 대상은 가중치 그대로), 프로토콜 v1.3 불변, 0.8.0. 받으면 학습 쪽 재측정·재학습.
   - **컨텍스트 밴딧 구현 (사용자 요청 2026-11-23 "밴딧 설계대로 구현")**: 프로토콜 **v1.4** `run_episode.initial_state` (SDK 원본 `btqa_sdk` 0.2.0 = `6c71e4c` 푸시됨 → 사본 동기화), game_sim 선언·적용(hp_ratio·potions_ratio), balance_qa 전송·검사·`optimize(initial_state/_fn)`, **`bandit` 명령**(PyCharm `06b`), **E8** (`experiments/e8_bandit.py`), play_agent `BanditPolicy`(numpy = torch 테스트). 테스트 118개. Unity 반영 요청 `unity_game/PROTOCOL_UPDATE_1.4.md` (QaArenaHost 선언 2줄 + `SetStartHpRatio`). 결정: 시작 트리거 없음(가중치를 params 로), resource_ratio 제외 — 설계 9장.
     **E8 첫 결과 (game_sim, warrior·mage/base, stable, 칸 18개 × 60판, 단일 실행)** `reports/20261123-234123`: 칸 평균 보상 손튜닝 −9.08 / CMA-가득 −8.43 / **CMA-전역 −7.97** / CMA-칸별 −7.89 (10,800판) / **IMPALA 밴딧 −8.45** (3,000판, 갱신 93회). 칸별 개선 중 얻은 몫(중앙값): CMA-전역 80%, 밴딧 38%. → **이 게임에서는 밴딧 이득 없음**: 같은 판 수의 CMA-전역(가중치 하나)이 이긴다. 시작 상태별 최적 가중치 차이가 작고(전역이 칸별의 80%), 밴딧은 3,000판으로 덜 배웠다. game_sim 은 2D 패턴·스킬 확장이 없는 단순 대역이라 결론은 Unity 늑대왕(1.4 반영 후)에서 다시. 칸당 60판이라 CI 가 넓다 (CMA-칸별이 CMA-전역보다 나쁜 칸 = 칸당 600판 예산 부족·잡음).
   - **IMPALA = 컨텍스트 밴딧 (사용자 결정 2026-11-23, 판 시작 1회 결정)** 설계 `docs/BANDIT_IMPALA_DESIGN.md`: 컨텍스트 = 조합 원-핫·페르소나 λ·시작 상태(PROTOCOL v1.4 `run_episode.initial_state` 제안), E8 = CMA-전역/CMA-셀별 대비. 순서: Unity 보스 패턴 → 스킬·BT → v1.4(SDK 원본) → 밴딧 모드.
   - **스킬·BT 확장 요청** `unity_game/PLAYER_SKILL_BT_REQUEST.md` (보스 패턴 작업 뒤, 같은 0.8.0 권장): 직업당 스킬 6~7(역할 Mobility·Setup 추가), 블록 3→5(`w_evade`·`w_setup`), 블록 안 스킬 점수·콤보·시전 취소, 표시 전용 스킬 바(쿨 쓸기). 측정: 평타 비중 전사 80%·마법사/궁수 64%, 전사 돌진 0%(game_sim default).
   - Unity 가 보낸 요청 `unity_game/PLAY_PROTOCOL_0.4_COMPUTER_USE_REQUEST.md` (비전 없는 computer use) — 학습 쪽 검토 대기.
   - **LLM 은 각자 고른다 (사용자 요청 2026-11-23)**: 안내 `docs/LLM_SETUP.md`, 코드 `play_agent/llm/` (`LlmBackend` → `AnthropicBackend` / `OpenAICompatBackend`: 로컬 Ollama·LM Studio·llama.cpp·vLLM·호환 클라우드), 설정 `llm.json`(git 제외, 예시 `play_agent/llm.example.json`), `play --llm ...`, PyCharm `14` = `run/run_play.py`. 로컬·클라우드 백엔드는 가짜 전송 테스트만 — 실제 LLM 으로는 아직 안 돌림.
   - 아래는 API(`play_agent play`) 로 돌릴 때의 준비 — `venv_play` 는 **2026-11-24 삭제** (relay 로 충분 — 사용자 결정; API 를 쓸 때 `docs/LLM_SETUP.md` C 로 다시 만들고 `pip install -e ./btqa_sdk`), 키는 미설정 (API 는 정액제와 별도 과금이라 보류). 기존 기록 (2026-11-23 세션 끝) — 사용자가 1~3 준비 후 알려 주면 4 를 실행하고 결과 정리:
   1. Python 3.12 설치: `winget install Python.Python.3.12` (또는 Anaconda `conda create -n play_agent python=3.12`)
   2. `py -3.12 -m venv venv_play` → `venv_play\Scripts\python.exe -m pip install anthropic numpy` (`venv_play/` 는 .gitignore 에 있음)
   3. console.anthropic.com 에서 API 키 → `setx ANTHROPIC_API_KEY "sk-ant-..."` (새 터미널·PyCharm 재시작). 키는 채팅에 붙이지 않는다
   4. 창 모드 게임 `unity_game\Build\QaArena.exe -qaPlay -qaPort 7800 -qaPlaySpeed 4` + `venv_play\Scripts\python.exe -m play_agent play --game 127.0.0.1:7800 --loadout reports/20261123-003306 --effort low --max-actions 40` (첫 실행은 짧게) → `reports/play-<시각>/run.json`·`play_log.json`
   - 첫 실제 API 실행이라 `pilot.py` 가 SDK 와 어긋나면(예: `output_config`·`cache_control` 인자, strict 스키마 400) 그 자리에서 고친다. 가짜 API 테스트만 통과한 상태.
6. 사용자에게 남은 것: 2장 결정 대기(잘못된 `trigger_response`), 늑대왕 마법사 손튜닝 0% 조사 여부 (0.8.1 에서도 0% — Unity 보고), 포트폴리오 문서. (`PLAY_PROTOCOL_0.2_FOLLOWUP.md` 는 0.3 요청으로 대체·반영됨)

## 6. 미구현·알려진 한계

- SDK 다음 단계 (`SDK.md` 7장): 결과 지표(metrics) 일반화, C# 정책 실행기, JSON Schema·공용 적합성 케이스, 두 번째 게임으로 일반성 검증, 배포(PyPI·UPM)
- w 크기 중복: 블록 선택이 점수 순서만 보므로 가중치 전체 배율이 무의미 (3개 중 실효 2). 정규화하지 않고 한계로 둠
- 이전 `policy.json`(0.7.0 전, 출력 5개)은 play_agent 로 여전히 불러 쓸 수 있지만, 새로 학습하면 출력은 가중치 3개

- 정책 다시 불러오기: IMPALA `policy.json` 은 `play_agent` 가 numpy 로 불러 쓴다 (2026-11-23 이후 파일만). 학습 쪽(`balance_qa`)에서 불러와 평가·이어 학습하는 명령, ES `policy.json` 불러오기는 아직 없음
- 학습 체크포인트·재개, 액터 재접속, TLS (클라우드 전 필요 — `DISTRIBUTED.md`)
- E1~E7 본 실행은 아직 안 함 (축소 실행만)
- 블랙보드 공통 성향값(원문 6장), 목표 난이도 역산(E8) 미구현
