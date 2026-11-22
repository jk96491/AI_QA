# QaArena — 밸런스 QA 테스트용 Unity 게임

학습 플랫폼(`../balance_qa`)이 TCP 프로토콜 v1.2(`../docs/PROTOCOL.md`)로 접속해 수천~수만 판을 돌리는 헤드리스 전투 게임.
로직은 `../game_sim`(파이썬 참조 구현)을 C# 로 옮긴 것이다.

- **Unity**: 6000.0.60f1 (Unity 6 LTS), 스크립팅 백엔드 Mono
- **패키지**: `com.unity.nuget.newtonsoft-json` 3.2.1
- **빌드 결과**: `Build/QaArena.exe`

## 에디터에서 쓰기

### 프로젝트 열기
Unity Hub → **Add → Add project from disk** → `AI_QA/unity_game` 선택 → 6000.0.60f1 로 열기.

> 에디터가 이 프로젝트를 열고 있는 동안에는 명령행 빌드(아래)가 실패한다 (Unity 는 한 프로젝트를 한 프로세스만 연다). 명령행으로 빌드하려면 에디터를 닫거나 메뉴로 빌드한다.

### Play 모드에서 QA 서버 켜기
1. 메뉴 **QA → Play Mode Server → Enabled** 체크 (기본 포트 7777, 바꾸려면 **QA → Play Mode Server → Port...**)
2. **Play** ▶ — Game 뷰 좌상단에 `QA 서버 127.0.0.1:7777 / 연결 / 처리한 판` 이 표시되고, Console 에 `[QA] LISTENING 7777`
3. 상위 폴더 `AI_QA` 에서 학습 쪽 명령 실행 (예: `venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777 check-game`)
4. Play 를 멈추면 서버도 닫힌다

- 서버는 백그라운드 스레드에서 돌아 에디터가 멈추지 않는다. 판 진행은 프레임과 무관한 고정 dt 루프라 Play 모드에서도 결과가 빌드와 같다.
- C# 코드에 중단점을 걸고 디버깅할 수 있다 (Rider/VS 에서 Attach to Unity). 트리거 응답 대기 중에는 게임 시간이 멈춘다.
- 대량 학습은 에디터보다 빌드 인스턴스 여러 개가 빠르다 (아래).
- Enabled 를 끈 상태의 Play 는 일반 실행 (서버 없음).

### 전투 뷰어 (화면)
Play 하면 (서버 설정과 무관하게) 전투가 화면에 그려진다. 헤드리스(`-batchmode`)에서는 만들지 않는다.
- 오른쪽 **전투 설정** 패널: 직업·시나리오·seed·BT 파라미터 슬라이더 → **▶ 전투 시작**
- **학습 결과 파라미터 불러오기**: `reports/<run>/params.json` 내용을 붙여넣으면 직업·시나리오·파라미터가 자동 적용
- **학습 서버 판 보기** (Play Mode Server 켠 상태): 학습 쪽이 마지막으로 돌린 판을 같은 seed·params·트리거 응답으로 재생 → 결과가 서버와 같으면 `✓`. "자동 따라보기" 를 켜면 새 판이 올 때마다 재생
- 조작: Space 일시정지, N 한 틱, R 같은 판 다시, Enter 새 전투, 1~6 속도(0.5x~16x), Tab 패널, 휠 확대, 오른쪽 드래그 회전
- 화면: 보스 체력바(페이즈 눈금)·준비 동작 바, 바닥 빨간 경고(내려찍기·처형)/주황(도약), 노란 고리 = 기믹 경고, 플레이어 체력·자원·시전 바·현재 BT 블록, 전투 기록, 결과(블록 점유 비율)
- 맵 경계: 둘 다 반지름 27m(주황 고리) 안에서만 움직인다 — 경계에 닿으면 보스 주위로 벽을 따라 돌고, 그래도 넘으면 둘을 함께 안쪽으로 민다. 판 로직은 거리만 다루므로 결과에는 영향 없음
- 그래픽은 Unity 기본 도형으로 조립한 것 (`Assets/Presentation/ViewerArt.cs` 의 `BuildBoss`/`BuildPlayer` 를 프리팹으로 바꾸면 실제 모델 적용). 판 로직은 뷰어에 의존하지 않는다.

### 빌드
- 에디터 메뉴 **QA → Build Windows (QA server)** → `Build/QaArena.exe`
- 명령행 (에디터 닫힌 상태, `unity_game` 폴더에서):
  ```
  "C:\Program Files\Unity\Hub\Editor\6000.0.60f1\Editor\Unity.exe" -batchmode -quit -projectPath . -executeMethod Qa.EditorTools.QaBuild.BuildWindows -logFile Logs/build.log
  ```

## 빌드 실행

| 모드 | 명령 | 비고 |
|---|---|---|
| 헤드리스 (학습용) | `Build/QaArena.exe -batchmode -nographics -qaPort 7777` | 메인 스레드 블로킹, CPU 대기 0. `LISTENING 7777` 은 Player.log 에 (stdout 으로 보려면 `-logFile -`) |
| 창 모드 (확인용) | `Build/QaArena.exe -qaPort 7778` | 전투 뷰어 창 (학습 판 재생 가능) |
| 창 모드 + 자동 재생 | `Build/QaArena.exe -qaPort 7778 -qaFollow -qaViewSpeed 8 -qaPanel 0` | 학습 쪽 `--view` 용 |

창 모드 뷰어 인자 (판 로직과 무관, 화면만):
- `-qaFollow` — 시작부터 "학습 판 자동 따라보기" 켜기 (재생이 끝날 때마다 그 시점의 최신 학습 판을 재생)
- `-qaViewSpeed <x>` — 재생 속도, 0.5/1/2/4/8/16 중 가장 가까운 값 (기본 1)
- `-qaPanel 0` — 오른쪽 설정 패널 접기 (Tab 으로 다시 펼침)
| 일반 실행 | `Build/QaArena.exe` | `-qaPort` 없음 → 서버 없음 |

- `-qaHost <ip>` 로 바인드 주소 변경 (기본 127.0.0.1). `-qaPort 0` 이면 빈 포트 자동 선택.
- 인스턴스 1개 = 포트 1개 = 동시 연결 1개. 병렬은 인스턴스를 여러 개 띄운다.
- 여러 인스턴스를 직접 띄울 때는 `-logFile Logs/player<port>.log` 로 로그를 나눈다.

학습 쪽에서 띄우기 (상위 `AI_QA` 폴더):
```
venv\Scripts\python.exe -m balance_qa --workers 4 --game-cmd "unity_game/Build/QaArena.exe -batchmode -nographics -qaPort {port}" optimize --cls warrior --persona stable --budget 600
```

## 플레이 모드 (P1~P4 완료, 0.6.2) — LLM 비전투 플레이 + 학습된 BT 전투

완료 보고·계약 반영 요청: `PLAY_MODE_REPORT.md`.

계약 `../docs/PLAY_PROTOCOL.md` v0.1 (초안), 작업 목록 `PLAY_MODE_REQUEST.md`. **`-qaPlay` 가 없으면 아무것도 바뀌지 않는다** (밸런스 모드 T1: check-game 15/15, 고정 seed 21판 결과 바이트 동일, 경계 사례 37/37).

| 명령 | 비고 |
|---|---|
| `Build/QaArena.exe -qaPlay -qaPort 7800` | 창 모드 (1280×720). 행동 진행이 실시간 1배 |
| `... -qaPlaySpeed 16` | 관람 배속 (결과는 dt·틱 수로만 정해져 배속과 무관) |
| `... -qaPlayCombatSpeed 8` | 전투 장면 배속만 따로 (생략 = `-qaPlaySpeed`) |
| `... -qaPlayOmniscient` | 디버그: 시야 밖·닫힌 창까지 관찰 (`"hidden": true` 표시) |
| `... -qaPlaySeed 7` | `reset.seed` 생략 시 기본값 |
| `Build/QaArena.exe -batchmode -nographics -qaPlay -qaPort 7800` | 헤드리스 — 행동·전투 즉시 진행. 결과·로그는 창 모드와 같다 (T7) |

지원: `hello`(protocol `"play"`) / `play_describe` / `set_loadout` / `reset`(seed·class 만, 항상 새 게임) / `observe`(semantic·hierarchy) / `act`(`move_to`·`interact`(talk·pickup·open·enter)·`ui_click`·`use_item`·`engage`·`wait`) / `trigger_response` / `get_log` / `bye`.
`ui_input` 은 `error(unknown_action)` (입력창이 아직 없음).

**전투 인계 (P3)** — 필드 전투 = 밸런스 모드와 **같은 `CombatSim` + `BTAgent`, 같은 인자** (sim-to-real 격차 0):
- 조우: `move_to`·`engage` 중 매 틱 적의 `aggro_radius` 안에 들어가면 게임이 즉시 전투 시작 (LLM 을 기다리지 않음). 조우 = 밸런스 시나리오 1개 (`wolf_king` → `forest_wolf_king`)
- 조우 seed = `mix(reset.seed, 조우 순번)` (SplitMix64, 0~2^31-1). `combat_started.seed` 로 알려 준다
- 파라미터 = `set_loadout` 의 (class, scenario) 항목 (`params`·`triggers` 를 run_episode 와 똑같이 `CombatSim` 에 넘김). 없으면 정의서 default, `loadout.matched=false`
- 시작 상태 `full` (`CombatSim` 이 항상 가득 찬 상태로 시작 — 필드 상태를 가져가지 않고, 끝난 뒤에도 필드 체력은 가득)
- 메시지: `combat_started` → (`trigger` ↔ `trigger_response`)* → `combat_ended`(`result` = episode_result.result 그대로 + `aftermath`) → `action_result`(move_to 는 `interrupted`/`combat`, engage 는 `done`). 전투 시간만큼 세계 시간이 흐른다
- 전투 중 `trigger_response` 외 요청 → `error(busy)` (전투는 계속). trigger 대기 중이 아닐 때의 `trigger_response` → `bad_request`. 형식·이름·범위가 틀린 응답은 error 를 보내고 **같은 trigger 를 계속 기다린다** (밸런스 모드는 판 중단)
- 승리: 적 제거, 전리품·경험치, kill 목표. 패배(사망 초과·시간 초과·멈춤): 적의 `checkpoint`(`cp_forest`)에서 부활, 적은 그대로(다음 조우는 새 seed·새 체력)
- **전투 장면 (창 모드)**: 조우하면 암전 → 전투 뷰어 아레나로 장면 전환 → 학습 판 재생과 같은 연출(보스·직업 모델, 스킬·피격·경고 장판·기믹, 보스 체력바·페이즈·격노, BT 블록, 전투 기록)로 실제 전투 → 결과 배너 → 필드로 복귀 (`Assets/Presentation/BattleViewerPlay.cs`).
  판은 세션이 만든 `CombatSim` 을 뷰어가 한 틱씩 진행할 뿐이라 결과는 같다 (창 모드만 이벤트 기록을 켜고, 보내는 result 에서 `events` 를 뺀다 — T5·T7 창 ↔ 헤드리스 동일 확인). 플레이 모드 뷰어는 키·마우스·설정 패널·다시하기 버튼을 받지 않는다.
  헤드리스는 연출 없이 즉시 진행
- 트리거 왕복 검증은 `CombatEpisodeRunner.CheckTriggerResponse`·`ParseTriggers` 를 두 모드가 공유

- 지역: 마을 `village` — 촌장 `npc_elder`, 상인 `npc_merchant`, 경비 `npc_guard`(시작 시 시야 밖), 울타리 안 상자 `chest_fenced`(닿을 수 없음), 숲 입구 `portal_forest`(alwaysKnown) /
  숲 `forest` — 약초 `herb_01~04`, 체크포인트 `cp_forest`(부활 위치), 마을로 `portal_village`, 필드 보스 늑대왕 `wolf_king`(어그로 6m)
- 튜토리얼 (P2): `q_tut_01` 촌장에게 말 걸기 → `q_tut_02` 약초 3개 채집 후 반납(골드 30·작은 물약 2) → `q_tut_03` 인벤토리에서 작은 물약을 퀵슬롯에 등록 → `q_tut_04` 상인에게 작은 물약 2개 구매(골드 20) → `q_tut_05` 늑대왕 처치 후 경비에게 보고(골드 50)
- 의도적 함정: ① 촌장 첫 대화에서 "나중에" → 퀘스트 미수락 ② 인벤토리를 처음 열면 안내 팝업(`ui.tip`)이 위에 떠 슬롯·등록 버튼을 가림 ③ 상점: 작은 물약 버튼은 골드가 부족해도 눌리고 `ui.shop.message` 에 "골드가 부족합니다 (필요 25G, 보유 20G)", 큰 물약(80G) 버튼은 골드 부족 시 비활성 ④ 체력이 가득할 때 `use_item` → `invalid_state`
- UI id: HUD `ui.hud.{zone,gold,quickslot.0,quickslot.1,inventory,quests}` / 대화 `ui.dialog.{speaker,text,choice.<i>}` / 퀘스트 `ui.quests.{title,body,close}` / 인벤토리 `ui.inventory.{slot.<item>,detail,assign,close}` / 안내 `ui.tip.{text,ok}` / 상점 `ui.shop.{gold,item.<item>,buy.<item>,message,close}`
- 관찰 추가분: `quests`(active·ready 퀘스트와 목표 `progress`·`done`·`hint_targets`), `inventory`, `player.quickslots`, 엔티티 `marker`(quest_available / quest_turn_in / objective), `screen.modal` 에 `"tip"`
- 데이터: `Assets/QA/Data/Resources/QaData/play/` — `world.json`(지역·엔티티·장애물·이동 한계), `dialogues.json`(조건부 시작 노드 `quest:<id>=<state>`·`flag:`, 효과 accept_quest·complete_quest·open_shop·set_flag), `quests.json`(목표 kind talk·collect·quickslot·buy·turn_in), `items.json`(아이템·상점). 기동 시 교차 검증, 밸런스 모드에서는 읽지 않는다
- 구현 메모
  - 길찾기는 NavMesh 대신 **격자 A\*** (`Play/World/GridPath.cs`, 0.5m 칸, 8방향, 시야선 단순화) — 고정 dt·결정성·헤드리스를 위해. 관찰되는 의미(`done`/`unreachable`)는 같다
  - 시야 = 플레이어 추적 카메라 자세로 만든 **고정 16:9 frustum 수학 판정** (창 크기와 무관). 가림(occlusion) 판정은 v0.1 대로 생략
  - UI = uGUI + TextMeshPro(한글은 OS 글꼴 맑은 고딕으로 동적 글꼴 생성). `interactable` = `Selectable.IsInteractable()` + 요소 중심 `EventSystem.RaycastAll` 첫 대상이 자기 자신. 모달 창은 전체 화면 반투명 배경이 입력을 막는다 → 가린 버튼은 `interactable:false`, 클릭 시 `reason_detail: "blocked by ui.dialog"`
  - `ui_click` 은 포인터 이벤트(enter→down→up→click)만 보낸다 (`onClick.Invoke` 안 씀). **입력 모듈이 없어** 사람이 창을 클릭해도 플레이에 끼어들지 못한다
  - 소켓은 백그라운드 스레드, 처리는 메인 스레드(`PlayDriver.Update`). 응답 전에 2프레임 기다려 UI 배치가 갱신된 뒤 관찰한다. 응답 후에는 Step 을 부르지 않는다 = 세계 정지
  - 계약 외 추가 필드: `play_description.stage`("P1"), `play_log.next_seq`, omniscient 의 `hidden`. hello 는 0.x 동안 **주.부 버전 일치**를 요구 (PLAY_PROTOCOL 7장 "0.x 는 부 버전도 호환 깨짐 허용" 해석)
- TMP 자산: `Assets/TextMesh Pro/` (TMP Essential Resources). 없으면 `python unity_game/QaTools~/import_tmp_essentials.py` 후 빌드 (`ImportPackage` 는 batch 빌드 안에서 끝나지 않음)
- 검증: `venv\Scripts\python.exe unity_game/QaTools~/play_check.py --game 127.0.0.1:7800 [--omni 127.0.0.1:7801] [--balance 127.0.0.1:7777] [--game2 127.0.0.1:7802]` (T2~T8, 96항목. `--balance` = 같은 빌드의 밸런스 인스턴스 — T5 결과 비교·T8, `--game2` = T7 교차 비교(창 ↔ 헤드리스). 헤드리스 단독은 omniscient 항목 제외 93)

```
Assets/QA/Play/Server      PlayServer(TCP), PlaySession(메시지 처리·세계 정지), PlayBoot(-qaPlay 인자), PlayDriver
Assets/QA/Play/World       PlayData(JSON·교차 검증), WorldState(지역·퀘스트·대화·인벤토리·상점·창, 순수 C#), GridPath(A*)
Assets/QA/Play/Perception  QaTag/QaIgnore, Visibility(frustum·UI 레이캐스트), UiIds, Semantic/HierarchyObserver
Assets/QA/Play/Actions     MoveTo, Interact, UseItem, Wait, ActionRunner (순수 C#) + UiClick
Assets/QA/Play/Combat      Loadout (set_loadout 검증·조회)
Assets/QA/Play/Log         PlayLog
Assets/Presentation/Play   PlayView (지역·플레이어·카메라·uGUI: HUD·대화·퀘스트·인벤토리·안내·상점)
```

## 도구

빌드·검증·밸런스 측정 도구는 `QaTools~/README.md` (명령행 빌드 `build.ps1 -check`, .NET 하네스, 컴파일 검사, `tune.ps1`·`retune.py`).

## 검증 (상위 `AI_QA` 폴더에서)

```
venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777 check-game          # 적합성 (전 항목 PASS)
venv\Scripts\python.exe unity_game/QaTools~/edge_cases.py --game 127.0.0.1:7777 # 오류 처리 경계 사례 37개
```
> `--game` 은 하위 명령 **앞**에 쓴다.

## 보스 (고정 BT — 학습 대상 아님)

보스 BT 의 상수는 `bosses/default.json` 에만 있고 `describe` 로 공개하지 않는다. 학습 쪽은 플레이어 BT 파라미터만 바꾼다.
0.3초마다 위에서부터 조건이 맞는 첫 행동 (준비 동작 중에는 완료까지 대기):

| 우선 | 행동 | 조건 → 효과 | 플레이어 쪽에서 의미 있는 선택 |
|---|---|---|---|
| 1 | 기믹 | 타이머 → 경고, 1.5s 안에 대응 못하면 최대 체력 60% | (강제 대응) |
| 2 | 광역기 | ~15s 마다, 거리 무관 | 체력 관리 |
| 3 | 처형 | 페이즈 3+, 플레이어 체력 < 35%, 사거리 안 → 1.0s 준비 후 750 | 저체력 근접 금지: θ, `potion_hp` |
| 4 | 도약 | 페이즈 2+, 거리 > 5.5m → 0.6s 후 앞에 착지 + 260 | 너무 멀리 빠지지 않기: `kite_distance` |
| 5 | 투척 | (기본 꺼짐 `throw_damage: 0`, 패치 시나리오용) | |
| 6 | 내려찍기 | 사거리 안, 11s 마다 → 1.2s 준비 후 사거리 안이면 360 | 근접 유지 vs 후퇴: `w_survival`, `w_dps` |
| 7 | 평타 | 사거리 안, 2s 마다 100 | |
| 8 | 추격 | 사거리 밖 → 접근 | |

모든 피해 × 페이즈 배율(1.0/1.1/1.25/1.4) × 격노(420초 이후 ×1.5) × 난수 ±20%.

0.5.0 기준 손 튜닝 default 성능 (stable, 학습 쪽 평가 시드 300판): warrior 클리어 61% [55, 66] 사망 1.00, mage 62% [57, 68], archer 100%(329s), 멈춘 판 0%.
학습 (stable, 하네스, 학습 쪽 보상에 클리어 실패 벌점 30분 반영 후): warrior CMA-ES 1,200판 62→99%, 사망 0.94 / IMPALA 1,600판 98%, 사망 0.93.
0.4.0 까지는 warrior 가 클리어에 ~3회 사망이 필요해 학습이 "안 죽고 시간 초과" 로 수렴했다 → 0.5.0 에서 방어력 0.5→0.6 으로 "거의 안 죽고 깨는" 길을 만들고,
손 튜닝 default 는 다시 덜 다듬어(`potion_hp` 0.5→0.36, `resource_reserve` 0.3→0.15: 물약을 늦게 마시고 비축을 덜 함) 클리어 60% 대로 맞췄다.
archer 는 여전히 쉬움 (직업 간 불균형 = 밸런스 QA 가 찾아야 할 대상).

### 플레이어 쪽 고정 규칙 (0.5.0)
- 부활: 사망 후 25초(`SimConfig.ReviveDelay`) 뒤 최대 체력의 50%(`ReviveHpRatio`)로 부활 — 부활을 회복 수단으로 쓰지 못하게
- 비전투 회복: 마지막 피격 후 `regen_delay`(6초) 지나면 초당 최대 체력의 `hp_regen_ratio`(1.2%) 회복 — `classes/<id>.json` 의 `stats`
- 전사 방어력 `armor` 0.6 (0.4.0 에서 0.3 → 0.5, 0.5.0 에서 0.6 — 근접 탱커가 보스 근접기를 버티고 사망 1회 이하로 클리어할 수 있도록)
- 생존 블록 최대 유지 시간: `bt_rules.survival_max_hold`(12초) 넘게 생존 블록에 머물면 `survival_lockout`(6초) 동안 생존 후보 제외 → 딜·접근으로 복귀 (멈춘 판 방지). 학습 대상 아님, describe 비공개
- 멈춘 판 (90초 동안 보스 피해 0): `stalled: true, stall_reason` 으로 보내는 **실패** 판 (v1.2). `invalid` 는 쓰지 않는다

> 0.2.0 부터 보스가 `game_sim`(파이썬 참조)과 다르다. 프로토콜·플레이어 BT 는 그대로 같다.

## 데이터 편집

`Assets/QA/Data/Resources/QaData/`
- `game.json` — `game`, `game_version` (**데이터를 바꾸면 올린다**)
- `classes/<id>.json` — 직업 스탯·스킬·BT 파라미터(`params`: range / default / group). 바꾸면 그 직업의 `spec_version` 도 올린다
- `bosses/default.json` — 보스 수치·페이즈
- `scenarios.json` — 패치 시나리오 (`scale` 배율 / `set` 값, 선택 `boss` = 다른 보스 정의서. 생략 = `default`)
- `bosses/forest_wolf_king.json` — 숲의 늑대왕 (시나리오 `forest_wolf_king`, 플레이 모드 필드 보스). 0.6.2 손 튜닝 default (stable 200판): warrior 클리어 60%, mage 0%, archer 97%. CMA-ES 1,200판으로 warrior 59→98%

기동 시 전부 검증한다 (필수 파라미터, 범위, 모르는 필드 오타 등). 실패하면 서버가 뜨지 않고 로그에 이유를 남긴다.

## 코드 구조

```
Assets/QA/Protocol   QaServer(TCP), QaSession(메시지 처리), CombatEpisodeRunner(run_episode·트리거)
Assets/QA/Sim        CombatSim(고정 dt 루프), Player, Boss, Rng(xoshiro256**, 판마다 seed 로 1개)
Assets/QA/BT         노드, Blackboard, 필요도 N, 블록 5종, UtilitySelector(S = N × w), BTAgent
Assets/QA/Data       정의서 로더·검증 + JSON 데이터
Assets/QA/Boot       진입점 (-qaPort / 에디터 Play Mode Server)
Assets/QA/Editor     빌드 스크립트, QA 메뉴
Assets/Presentation  상태 표시 (로직은 여기에 의존하지 않음)
QaTools~             검증 스크립트 (Unity 가 임포트하지 않는 폴더)
```

결정성: 같은 class·scenario·seed·params·트리거 응답 → 바이트 단위로 같은 result.
`UnityEngine.Random`, `Time.*`, 코루틴, 물리, Dictionary 순회 순서에 로직이 의존하지 않는다.
