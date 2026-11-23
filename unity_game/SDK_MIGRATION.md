# BT-QA Game SDK 도입 (0.7.0, 프로토콜 1.3) — Unity 에이전트 필독

> 2026-11-23, 학습 쪽 세션이 사용자 요청으로 **직접 반영**했다 (이번만 예외로 `unity_game/` 을 학습 쪽이 수정).
> 이 문서는 무엇이 바뀌었고 앞으로 어떻게 작업하는지 Unity 에이전트에게 알리는 기록이다. 다음 작업 전에 읽는다.
> 전체 설명: `../docs/SDK.md`, 계약: `../docs/PROTOCOL.md` v1.3 (계약 사본, 원본은 SDK 레포).

## 1. 왜

이 구조를 SDK 로 만든다 (사용자 결정). SDK 의 핵심 규칙:

**학습(CMA-ES·IMPALA)이 정하는 값은 BT 전략 선택 노드의 블록 가중치 w 뿐이다.**
- 게임은 BT 를 설계하고 블록과 그 가중치를 `classes[].blocks` 로 선언한다.
- `potion_hp`, `resource_reserve`, `min_commit`, `charge_distance`, `kite_distance` 같은 **가중치가 아닌 BT 값은 학습하지 않는다**
  — 정의서 default(손 튜닝)가 그대로 쓰이고, 페르소나가 덮어쓸 수 있다.
- 이전 학습(0.6.2 까지)은 `potion_hp`·`resource_reserve` 등도 학습했다. 그래서 **손 튜닝 default 의 의미가 더 커졌다** — 이 값들이 이제 학습으로 보정되지 않는다.

## 2. 바뀐 것

| 항목 | 이전 (0.6.2) | 지금 (0.7.0) |
|---|---|---|
| 서버·세션 | `Assets/QA/Protocol/QaServer.cs`, `QaSession.cs` (게임 코드) | **SDK 패키지** `com.btqa.game` 의 `Btqa.Game.QaServer`, `QaSession` (두 파일 삭제) |
| 판 실행 | `CombatEpisodeRunner : IEpisodeRunner` | `Assets/QA/Protocol/QaArenaHost.cs` : `Btqa.Game.IEpisodeHost` (`Declare()` + `RunEpisode()`) |
| `CombatEpisodeRunner` | 판 실행 + 트리거 도우미 | 플레이 모드용 정적 도우미만 (`CheckTriggerResponse`, `ParseTriggers` → SDK 로 위임) |
| `ProtocolException`, `JsonLine`, `IMessageChannel` | `Qa.Protocol` | `Btqa.Game` (사용하는 파일에 `using Btqa.Game;` 추가됨) |
| `P.*` 상수 | 값 정의 | `Btqa.Game.Wire.*` 의 별칭 + 이 게임 고유 값(`TriggerType`, `TriggerStateFeatures`, `TriggerTotalsFields`, `ResultFields`) |
| describe | `params[].optimize` = 정의서 값(생략 시 group==bt) | **`classes[].blocks` 추가**, `optimize` 는 SDK 가 채움 (가중치만 true) |
| 블록 목록 | `BTAgent.Build` 안 문자열 | `BTAgent.StrategyBlocks` (이름·가중치·설명). Build 와 describe 가 같은 목록을 쓴다 |
| `ParamDef` | — | `ExplicitOptimize` (정의서에 optimize 를 적었을 때만) — SDK 가 "가중치 아닌 값에 optimize=true" 를 거부 |
| 요청 검증 | 세션 + CombatSim | SDK 가 먼저 (같은 오류 코드), CombatSim 은 그대로 |
| 프로토콜 / 게임 버전 | 1.2 / 0.6.2 | **1.3 / 0.7.0** (`game.json`) |
| 패키지 | — | **embedded 사본 `Packages/com.btqa.game`** (manifest 항목 없음, lock 은 `source: embedded`). 원본은 별도 SDK 레포 |
| compilecheck | `Assets/**/*.cs` | + `Packages/com.btqa.game/Runtime/**/*.cs` |

전투 로직(`Sim/`, `BT/` 의 동작)·데이터 수치·플레이 모드 동작은 **바꾸지 않았다**.

## 3. 확인한 것 (2026-11-23)

| 검사 | 결과 |
|---|---|
| `QaTools~/compilecheck` `dotnet build` | 오류 0, 경고 0 |
| `QaTools~/build.ps1 -check` | 빌드 성공, `check-game` 16/16 PASS (새 항목 "블록 가중치 선언" 포함), `edge_cases.py` 37/37 |
| T1 회귀: `balance_snapshot.py diff` (0.6.2 빌드로 SDK 도입 직전 저장한 스냅샷) | **21/21 바이트 단위 동일** |
| `python -m play_agent check-play --exe Build/QaArena.exe --loadout reports/20261123-003306` | 106/106 PASS |
| `run/run_full_cycle.py` (GAME_CMD = UNITY) | 6단계 PASS (`reports/20261123-193621`) |

## 4. 앞으로의 작업 규칙 (Unity 에이전트)

1. **SDK 는 학습 플랫폼 쪽 소유 — 원본(별도 SDK 레포)도, 프로젝트 안 사본 `Packages/com.btqa.game/` 도 수정하지 않는다** (4.6).
   SDK 의 검사 도구도 쓸 수 있다: `venv\Scripts\python.exe -m btqa_game check --game 127.0.0.1:7777` (`check-game` 과 같은 항목).
   SDK 에 버그나 필요한 기능이 있으면 `PROTOCOL_CHANGE_REQUEST.md` 에 적고 사용자에게 알린다.
2. 프로토콜 메시지 처리·요청 검증·트리거 왕복은 SDK 가 한다. 게임은 `QaArenaHost` 의 `Declare()` / `RunEpisode()` 만 바꾼다.
3. **새 전략 블록을 추가하면** `BTAgent.StrategyBlocks` 에 (이름, 가중치 파라미터, 설명)을 넣고, 그 가중치를 모든 직업 정의서 `params` 에
   `range` 0 이상·`unit: "weight"`·`group` 생략(bt) 으로 추가한다. 기동 시 `Declare().Validate()` 가 규칙을 검사한다.
4. 정의서 `params` 에 **`optimize` 를 적지 않는다** (SDK 가 정함). 가중치가 아닌 값에 `optimize: true` 를 쓰면 기동이 실패한다.
5. 가중치가 아닌 BT 값(물약 체력 등)은 학습이 보정하지 않으므로 **손 튜닝 default 를 신중히** 정한다. 페르소나별로 달라야 하는 값이면 사용자에게
   "페르소나 `params` 로 옮길지" 를 제안한다 (페르소나 파일은 학습 쪽 `qa_specs/personas.json`).
6. 데이터·로직 변경 후 검증 순서는 그대로: compilecheck → `build.ps1 -check` → T1 스냅샷 diff → `check-play` → 전체 사이클.
   T1 기준선 파일은 0.7.0 에서 다시 만들어도 된다 (`balance_snapshot.py save 127.0.0.1:7777 QaTools~/t1_baseline_0.7.0.json`) — 0.5.0 기준선과도 아직 21/21 동일.

## 4.5 SDK 위치 변경 (같은 날 후속)

SDK 를 별도 레포로 관리하려고 한 폴더 `../btqa_sdk/` 로 모았다: 계약 `docs/PROTOCOL.md`, Unity 패키지 `unity/com.btqa.game`, Python `python/btqa_game`.
`Packages/manifest.json`·compilecheck 경로를 그에 맞췄고, 다시 빌드해 check-game 16/16·edge 37/37·T1 21/21 동일을 확인했다.
(→ 4.7 에서 SDK 는 별도 GitHub 레포가 되고, 이 저장소는 사본만 쓰게 됐다.)

## 4.6 Unity 는 SDK 를 복사본으로 씀 (같은 날, 사용자 결정)

경로 참조(`file:../../btqa_sdk/...`) 대신 **패키지를 프로젝트 안 `Packages/com.btqa.game` 으로 통째로 복사**했다 (Unity embedded package).
Unity 프로젝트가 `unity_game/` 밖에 의존하지 않고 혼자 열리고 빌드된다.
- `Packages/manifest.json` 에서 `com.btqa.game` 항목 삭제 (embedded 는 자동 포함), lock 은 Unity 가 `"source": "embedded"` 로 다시 씀. `.meta` GUID 는 원본과 같다.
- **사본을 고치지 않는다.** 학습 쪽이 원본을 고친 뒤 `venv\Scripts\python.exe run/run_sync_sdk.py` 로 복사한다. `tests/sdk/test_unity_copy.py` 가 원본과 다르면 실패한다.
- 확인: compilecheck 0/0, `build.ps1 -check` 16/16·37/37, 두 번째 빌드 로그에서 `com.btqa.game@file:...unity_game\Packages\com.btqa.game` 만 해석, T1 21/21 동일, check-play 106/106.

## 4.7 SDK 는 별도 레포, 이 저장소는 사본만 (같은 날, 사용자 결정)

SDK 원본(`btqa_sdk`)은 별도 GitHub 레포로 관리한다. 이 저장소는 원본을 참조하지 않고 사본 3개만 쓴다:
`btqa_game/`(Python), `unity_game/Packages/com.btqa.game`(Unity), `docs/PROTOCOL.md`(계약). 사본 갱신은 학습 쪽이 `run/run_sync_sdk.py` 로 한다.
Unity 에이전트가 할 일은 바뀌지 않는다 — `Packages/com.btqa.game` 은 읽기 전용. 원본 폴더를 숨긴 상태로 빌드·check-game·edge·check-play 모두 PASS 확인.

## 5. 학습 쪽에서 같이 바뀐 것 (참고)

- 학습 대상: `balance_qa` 의 CMA-ES·ES 정책·IMPALA 모두 블록 가중치 3개만 (`ClassInfo.learnable_space()`). IMPALA 행동 차원 5 → 3.
- 페르소나 `qa_specs/personas.json`: `params` 묶음 (가중치가 아닌 값만, 예 θ·φ). 원문 8장과 완전히 같을 필요 없음.
- `run_episode.triggers` 키 = `describe.triggers.type` (하드코딩 제거).
- 플레이 모드 계약(`PLAY_PROTOCOL.md` v0.2)은 바뀌지 않았다. `set_loadout` 의 트리거 키는 그대로 `boss_hp_below`.
