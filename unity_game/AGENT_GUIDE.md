# Unity 테스트 게임 제작 가이드 (게임 제작 에이전트용)

이 폴더(`AI_QA/unity_game/`)에 **밸런스 QA 학습 플랫폼이 접속해서 테스트할 Unity 게임**을 만든다.
이 게임은 사람이 플레이하는 완성품이 아니라 **학습 플랫폼(`AI_QA/balance_qa`)의 실행 환경**이다.
아래 규칙은 학습 플랫폼이 수정 없이 붙기 위한 조건이므로 **반드시** 지킨다.

> 기준 문서: `AI_QA/docs/PROTOCOL.md` (v1.2). 이 가이드와 충돌하면 PROTOCOL.md 가 우선.
> 원문 제안서: `AI_QA/밸런스 QA를 위한 BT 파라미터 최적화 프로세스.pdf`

---

## 0. 작업 범위 (절대 규칙)

| 해도 됨 | 하면 안 됨 |
|---|---|
| `AI_QA/unity_game/` 안의 모든 파일 생성·수정 | `AI_QA/balance_qa/`, `AI_QA/game_sim/`, `AI_QA/tests/`, `AI_QA/docs/`, `AI_QA/qa_specs/` 수정 |
| `AI_QA/game_sim/` 을 **읽고** C# 로 옮길 참고로 쓰기 | 프로토콜(`docs/PROTOCOL.md`) 임의 변경 |
| 학습 플랫폼 명령을 **실행**해 검증 (`python -m balance_qa ...`) | 학습 플랫폼 코드를 게임에 맞춰 고치기 |

- 프로토콜로 표현할 수 없는 요구가 생기면 코드를 고치지 말고 `unity_game/PROTOCOL_CHANGE_REQUEST.md` 에 **무엇이·왜 필요한지** 적고 멈춘다.
- 학습 쪽 파이썬 실행은 `AI_QA` 폴더에서 `venv\Scripts\python.exe -m balance_qa ...` 로 한다.

## 1. 폴더 구성

- Unity 프로젝트 루트 = `AI_QA/unity_game/` (여기에 `Assets/`, `Packages/`, `ProjectSettings/` 가 생김)
- 생성물 폴더 `Library/ Temp/ Logs/ obj/ UserSettings/ Build/ Builds/` 는 PyCharm 색인에서 제외되어 있다. 코드·데이터를 이 폴더들에 두지 않는다.
- 권장 구조:
  ```
  Assets/
    QA/
      Protocol/   QaServer, QaSession, 메시지 DTO, 오류 코드        (game_sim/server 대응)
      Sim/        전투 로직 시뮬레이션 (Unity 컴포넌트와 분리)       (game_sim/sim 대응)
      BT/         행동 트리, 필요도 식, 행동 블록, 블랙보드          (game_sim/bt 대응)
      Data/       직업·보스·시나리오 정의 (ScriptableObject 또는 JSON) (game_sim/data 대응)
      Boot/       헤드리스 진입점 (명령행 인자 파싱 → 서버 시작)
    Presentation/ 화면·애니메이션 (선택, 로직이 여기에 의존하면 안 됨)
  ```
- Unity 버전: LTS (2022.3 LTS 또는 Unity 6 LTS) 권장. 정해져 있지 않으면 사용자에게 확인.
- JSON: `com.unity.nuget.newtonsoft-json` 패키지 사용 (`JsonUtility` 는 Dictionary 미지원).

## 2. 실행 모드 (헤드리스 서버)

- 명령행: `Game.exe -batchmode -nographics -qaPort <port> [-qaHost 127.0.0.1]`
  - `-qaPort` 가 있으면 **QA 서버 모드**: 렌더링 없이 TCP 서버만 돈다.
  - 학습 쪽 실행 예: `--game-cmd "unity_game/Build/Game.exe -batchmode -nographics -qaPort {port}"`
- 시작 후 `LISTENING <port>` 한 줄을 stdout 에 출력 (권장, 기동 확인용).
- **인스턴스 1개 = 포트 1개 = 동시 연결 1개**, 연결 안의 요청은 순차 처리. 병렬은 인스턴스를 여러 개 띄워서 한다.
- 연결이 끊기거나 `bye` 를 받으면 다음 연결을 기다린다 (프로세스는 종료하지 않음).
- 에디터 Play 모드에서도 같은 서버를 켤 수 있으면 디버깅이 쉽다 (선택).

## 3. 프로토콜 (요약 — 상세는 PROTOCOL.md)

전송: TCP, UTF-8(BOM 없음) JSON 객체 1개 + `\n`. 모든 메시지에 `"type"`.

| 받는 메시지 | 응답 |
|---|---|
| `hello` | `hello_ok` (`protocol_version: "1.1"`). 주 버전 다르면 `error(protocol_version)` |
| `describe` | `description` (정의서, 4장) |
| `run_episode` | (`trigger` ↔ `trigger_response`)* → `episode_result` |
| `bye` | 응답 없음, 연결 종료 |
| 그 외 | `error(unknown_type)` |

- 오류 코드: `bad_request, unknown_type, protocol_version, unknown_class, unknown_scenario, unknown_param, param_out_of_range, internal`
- **오류 응답 후에도 연결 유지.** 게임 내부 예외도 `error(internal)` 로 돌려주고 계속 대기.
- `params` 검증은 엄격하게: 모르는 이름 → `unknown_param`, 범위 밖 → `param_out_of_range`. 생략한 파라미터는 정의서 `default`.

### 트리거 규칙 (IMPALA 학습에 필수)
1. `run_episode.triggers.boss_hp_below` 가 있을 때만 보낸다.
2. **index 0 = 판 시작 직후**(첫 BT 결정 전), 이후 보스 체력이 각 경계 아래로 처음 내려갈 때 1, 2, … (연속 번호).
3. 한 틱에 여러 경계를 넘으면 트리거 1번. 보스가 죽었으면 보내지 않음.
4. `trigger_response` 가 올 때까지 **게임 시간 정지** (블로킹 대기).
5. 응답 `params` 는 **부분 덮어쓰기** (준 키만 변경), 검증 규칙은 `run_episode` 와 같음.
6. `state`: `describe.triggers.state_features` 의 모든 키, **0~1 정규화 숫자**.
7. `totals` (v1.1): 판 시작부터 누적 `elapsed`(초), `deaths`, `consumables_used`, `boss_hp_remaining`. index 0 의 elapsed = 0, 단조 증가.
8. episode_id·index 가 안 맞는 응답 → `error(bad_request)` 로 판 중단.

## 4. 정의서 (`describe` 응답) 규칙

- `time_limit`(초), `max_deaths`, `decision_interval`(BT 결정 주기, 권장 0.3초), `classes`, `scenarios`(`"base"` 필수), `triggers`(`type: "boss_hp_below"`, `supported`, `state_features`, `totals`).
- `classes[].params[]` 항목: `name, range[low,high], default, group("bt"|"persona"), optimize, unit, description`
  - `default` = **개발자가 손으로 맞춘 값** (모든 학습 결과의 비교 기준선)
  - `range` = **기획 의도 범위** (최적화는 이 안에서만 탐색)
  - 직업당 학습 대상(`group: bt`) 5~20개. 바꾸면 행동이 눈에 띄게 달라지는 값만 노출.
- 스킬·스탯 수치는 `describe` 에 넣지 않아도 된다 (학습 쪽은 파라미터만 안다).

### 현재 학습 플랫폼이 기대하는 파라미터 이름 (호환 필수)
학습 쪽 페르소나·트리거 정책이 아래 이름을 쓴다. **모든 직업에 같은 이름·같은 의미로** 둔다.

| 이름 | group | 의미 |
|---|---|---|
| `survival_hp_threshold` | persona | θ: 생존 필요도가 오르기 시작하는 체력 비율 (범위에 0.3~0.8 포함) |
| `dps_hp_floor` | persona | φ: 이 체력 아래에서 딜 의지가 줄어듦 (범위에 0.2~0.7 포함) |
| `w_burst`, `w_dps`, `w_survival` | bt | 블록 가중치 [0, 1] |
| `potion_hp` | bt | 생존 블록에서 물약 사용 체력 |
| `resource_reserve` | bt | 딜 스킬 사용 후 남길 자원 비율 (버스트 비축) |
| `min_commit` | bt | 블록 최소 유지 시간(초) |
| `kite_distance` | bt | (원거리 직업) 보스가 이보다 가까우면 거리 벌림 |

직업 고유 파라미터는 자유롭게 추가 가능. 위 구조와 **다른 BT 설계가 필요하면** 구현 전에 `PROTOCOL_CHANGE_REQUEST.md` 에 적고 사용자 확인을 받는다.

## 5. 결정성 (가장 중요)

같은 `(class, scenario, seed, params, 트리거 응답 순서)` → **바이트 단위로 같은 `result`**. 깨지면 학습이 노이즈를 배운다.

- 판마다 `new System.Random(seed)` (또는 자체 PRNG) **하나만** 사용. 모든 난수(치명타, 패턴 선택, 기믹 타이밍 등)가 여기서 나온다.
- 금지: `UnityEngine.Random`(전역 상태), `Time.deltaTime`/`Time.time` 을 로직에 사용, 코루틴·async 로 로직 타이밍 제어, 병렬 Job 의 비결정 순서, `Dictionary`/`HashSet` 순회 순서에 의존, 판 사이에 남는 static 상태.
- 물리·NavMesh·애니메이션 이벤트에 로직을 걸지 않는다. 필요하면 `Physics.autoSimulation = false` + `Physics.Simulate(dt)` 수동 진행.
- 거리·위치는 로직 시뮬레이션 안의 값으로 다룬다 (Transform 은 표시용).

## 6. 성능 (학습 가능 여부를 결정)

학습 1회에 **수천~수만 판**을 돌린다 (CMA-ES 3,000판, IMPALA 8,000판+).

- 판 진행은 **고정 dt 수동 루프**로 실시간보다 훨씬 빠르게: `while (!done) world.Step(FIXED_DT);` — 프레임 대기 없음.
- 목표: 5분짜리 전투 1판 ≤ **100 ms** (파이썬 참조 구현은 20~40 ms). 최소 수백 배 실시간.
- 렌더링·오디오·UI 를 QA 서버 모드에서 끈다. 판 사이에 씬 로드 금지 (로직 객체만 재생성).
- 측정: `venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777 evaluate --cls <c> --persona stable -n 50` 실행 시간.

## 7. 게임 내용 요구사항 (실험이 성립하려면)

참조 구현(`game_sim`)과 같은 수준을 최소로 한다.

- **직업 3개 이상**, 성격이 다르게 (근접 탱커형 / 원거리 버스트형 / 원거리 지속딜형 등). 직업 이름은 영문 소문자 id.
- **보스전 1종 이상**: 체력 경계 75·50·25% 에서 페이즈 전환(패턴 강화), 거리 무관 광역기, 경고 후 제한 시간 내 대응해야 하는 기믹.
- **BT 2층 구조** (원문 6·7장):
  - 위층: 점수 기반 전략 선택 노드 `S = N × w` (버스트 / 딜 유지 / 생존, 기믹 경고 시 기믹 대응 강제, 후보 없으면 접근)
  - 필요도 N 식: 버스트 = 준비 시 0.8 아니면 제외 / 딜 유지 = `0.5·min(1, hp/φ)`, 사거리 밖이면 제외 / 생존 = `max(0, (θ−hp)/θ)` / **S = 0 인 블록은 후보 제외**
  - 아래층: 블록 내부는 고정 서브트리, 상수는 블랙보드 파라미터로만 참조
  - 생존 블록은 후퇴·회복이 실제로 의미 있어야 함 (비전투 체력 회복 등)
- 사망·부활: `max_deaths` 초과 시 실패, 시간 제한 `time_limit` 초과 시 실패(중도절단).
- 소모품(물약 등) 사용 수 집계.
- **시나리오**: `base` + 밸런스 패치 몇 개 (보스 체력 ±5%, 피해 +10%, 속도 +25%, 기믹 대응 시간 단축 등). 데이터 값만 바꿔 만든다.
- 멈춘 판 감지: 일정 시간(예: 90초) 보스 피해 0 이면 판을 끝내고 `stalled: true, stall_reason: "..."` (v1.2, **invalid 아님**).

## 8. 결과 (`episode_result.result`)

> v1.2: 멈춤(90초 무피해 등)은 **`stalled: true`** (`cleared=false`, `invalid=false`). `invalid` 는 환경 오류에만. 상세 `PROTOCOL_UPDATE_1.2.md`.


필수: `seed, cleared, elapsed, clear_time(미클리어 null), boss_hp_remaining(0~1), deaths`
권장: `consumables_used, segment_times(페이즈 구간별 초), block_time(BT 블록별 점유 초), triggers_fired, invalid, invalid_reason, gimmick_success, gimmick_fail, damage_dealt, damage_taken, invalid_actions`
`record_events: true` 요청 시 `events` (리플레이·디버깅용 이벤트 목록).

## 9. 참조 구현 대응표 (`AI_QA/game_sim` → C#)

| 파이썬 (읽기 전용 참고) | 역할 |
|---|---|
| `game_sim/server/session.py` | 메시지 처리 전체 흐름 — **그대로 C# 로 옮길 기준** |
| `game_sim/server/protocol.py` | 메시지 type·오류 코드 상수 |
| `game_sim/sim/engine.py` | 판 진행 루프, 트리거 발생·totals, 결과 집계 |
| `game_sim/sim/player.py`, `boss.py` | 엔티티·전투 규칙 |
| `game_sim/bt/*` | BT 노드, 필요도 식, 블록, 전략 선택 노드 |
| `game_sim/data/*.json` | 직업·보스·시나리오 데이터 예시 (정의서 형식 포함) |
| `docs/PROTOCOL.md` 부록 A | C# 서버 뼈대 |

## 10. 완료 기준 (Acceptance)

각 단계마다 아래 명령으로 확인하고 결과를 보고한다 (`AI_QA` 폴더에서).

1. **연결·정의서**: 빌드 실행 → `venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777 list`
2. **적합성 검사 전부 PASS** (경고 항목 `trigger.totals` 포함):
   `venv\Scripts\python.exe -m balance_qa check-game --game 127.0.0.1:7777`
3. **처리량**: 6장 측정 명령으로 판당 시간 보고.
4. **학습 동작**: 인스턴스 2개 이상 띄우고
   `venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777,127.0.0.1:7778 optimize --cls <c> --persona stable --budget 600 --eval-n 50`
   `venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777,127.0.0.1:7778 impala --cls <c> --persona stable --budget 400 --eval-n 50`
   무효 판 0%, 학습 후 평가가 손 튜닝 대비 나빠지지 않는지.
5. **명령 템플릿 실행**: `venv\Scripts\python.exe -m balance_qa --workers 2 --game-cmd "unity_game/Build/<Game>.exe -batchmode -nographics -qaPort {port}" list`

6. **전체 사이클 점검 (최종)**: `run/run_full_cycle.py` 맨 위 `GAME` 을 Unity 엔드포인트로 바꿔 실행 → 6단계 모두 OK (`전체 사이클: PASS`).
   이 파일은 `unity_game/` 밖이므로 **수정하지 말고 복사본**(`unity_game/` 안)으로 GAME 값만 바꿔 실행하거나 사용자에게 요청한다.

권장 구현 순서: hello/describe → 트리거 없는 run_episode → 오류 처리 → 결정성 → 트리거·totals → 성능 최적화 → 콘텐츠 확장. 단계마다 2번을 돌린다.

## 11. 산출물

- `unity_game/README.md`: Unity 버전, 빌드 방법, 실행 명령, 포트 인자, 데이터(직업·보스·시나리오) 편집 위치
- 빌드 결과는 `unity_game/Build/` (색인 제외 폴더)
- 정의서 데이터 변경 시 `game_version` 과 직업별 `spec_version` 을 올린다 (학습 결과에 기록됨)
- 프로토콜 변경이 필요했다면 `unity_game/PROTOCOL_CHANGE_REQUEST.md`
