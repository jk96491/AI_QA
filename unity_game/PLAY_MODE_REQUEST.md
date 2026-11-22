# 플레이 모드 제작 요청 (학습 플랫폼 → Unity 게임)

- 작성: 학습 플랫폼 쪽, 2026-11-22
- 대상 빌드: 다음 이후 빌드 (**0.6.0** 권장). 단계별로 나눠 내도 된다 (5장).
- 계약 문서: **`../docs/PLAY_PROTOCOL.md` v0.1 (초안)**. 이 요청서와 충돌하면 PLAY_PROTOCOL.md 가 우선.
  초안이라 구현하다 막히거나 더 나은 방식이 보이면 **고치지 말고** `PROTOCOL_CHANGE_REQUEST.md` 에 적고 알린다 (기존 규칙과 같음).
- 기존 규칙(`AGENT_GUIDE.md`, `CLAUDE.md`)은 그대로 유효하다. 특히 `unity_game/` 밖 수정 금지.

---

## 0. 무엇을 만드나 (한 줄)

지금 QaArena 는 "보스전 한 판"만 있다. 여기에 **작은 마을 + 숲 튜토리얼**(이동·대화·채집·인벤토리·퀘스트·필드 보스)을 붙이고,
외부 클라이언트(LLM)가 **화면 대신 구조화된 관찰(JSON)** 을 읽고 **고수준 행동**으로 플레이할 수 있게 TCP 플레이 서버를 연다.
필드 전투는 **기존 `CombatSim` + `BTAgent` 를 그대로** 돌려 학습된 파라미터로 싸운다.

```
            ┌─────────────── 비전투 (LLM, 턴제: 클라이언트가 생각하는 동안 세계 정지) ───────────────┐
 reset → observe → act(move_to/interact/ui_click…) → action_result(+observation) → act → …
            └── 전투 감지 → combat_started → [CombatSim+BTAgent, loadout params] → (trigger↔response)* → combat_ended ──┘
```

### 0.1 두 모드를 헷갈리지 말 것

| | 학습 (밸런스 QA, 지금 있는 것) | 플레이 (이번에 만드는 것) |
|---|---|---|
| 실행 | `-qaPort` | `-qaPlay -qaPort` |
| 시작 | **전투로 바로** (`run_episode` = 보스전 한 판). 월드·퀘스트 로드 금지 — 속도·결정성 유지 | **게임 처음부터** (`reset` = 항상 새 게임, 튜토리얼 첫 장면). 중간 시작 옵션 만들지 않음 |
| 전투 | `CombatSim` + `BTAgent` | 같은 `CombatSim` + `BTAgent`, 파라미터는 `set_loadout` 으로 받은 학습 결과 |

- 필드 보스(`forest_wolf_king`)도 학습은 밸런스 모드 시나리오로 **전투만 바로** 돌린다 (2.3). 그래서 밸런스 모드에도 그 보스를 노출해야 한다.
- 플레이 모드 코드(월드·퀘스트·UI)는 밸런스 모드에서 **로드되지도 실행되지도 않아야** 한다.

## 1. 절대 규칙 (이번 작업 추가분)

1. **밸런스 QA 모드는 한 줄도 동작이 바뀌면 안 된다.** `-qaPlay` 가 없을 때의 동작·성능·결정성은 지금과 같아야 한다.
   - 확인: `venv\Scripts\python.exe -m balance_qa check-game --game-cmd "..."` 15/15 PASS 유지, 판당 시간 유지.
2. **전투 로직은 새로 만들지 않는다.** 필드 전투 = `CombatSim(spec, boss, params, seed, …)` 그대로. 필드용 별도 전투 규칙·데미지 공식 금지.
   - 이유: 학습한 BT 파라미터가 실전에서 그대로 통하려면 같은 로직이어야 한다 (sim-to-real 격차 0).
   - 검증 기준: 같은 class·scenario·seed·params·트리거 응답 → 밸런스 서버 `run_episode` 와 **같은 `result`** (6장 T5).
3. **플레이 로직(퀘스트·대화·인벤토리·월드 상태)도 MonoBehaviour 에 넣지 않는다.** `Sim/` 처럼 순수 C# 로 두고, MonoBehaviour 는 표현·입력·길찾기만.
4. **플레이 모드 UI 는 uGUI + TextMeshPro** (Unity 6 의 `com.unity.ugui` 2.0 에 포함). IMGUI(OnGUI) 금지 — 계층을 읽을 수 없다.
   기존 `BattleViewerHud`(IMGUI)는 밸런스 뷰어용으로 그대로 둬도 된다. 플레이 모드 화면에서 LLM 이 읽어야 할 정보는 uGUI 로 다시 그린다.
5. **관찰은 플레이어가 지각할 수 있는 것만** (3.4). 숨은 오브젝트·내부 플래그는 `-qaPlayOmniscient` 때만.
6. **세계 정지**: 클라이언트 요청을 처리하는 동안에만 게임 시간이 흐른다. 응답을 보낸 뒤 다음 요청이 올 때까지 정지 (애니메이션·AI·타이머·스폰 전부).
7. 결정성(플레이 모드): 같은 `reset.seed` + 같은 행동열 → 같은 관찰·결과. 판마다 `System.Random` 하나, `UnityEngine.Random`·`Time.deltaTime` 로직 금지 (기존 규칙 3과 같음).
   - 이동·NavMesh 는 고정 dt 로 직접 진행한다 (`NavMeshAgent` 자동 이동 대신 `NavMesh.CalculatePath` 경로를 고정 dt 로 따라가기 권장).

## 2. 콘텐츠 (최소 범위)

크게 만들 필요 없다. **LLM 이 실패할 만한 지점이 골고루 있는 것**이 중요하다.

### 2.1 지역

| id | 내용 |
|---|---|
| `village` | 시작 지점. NPC 3명(촌장 `npc_elder`, 상인 `npc_merchant`, 경비 `npc_guard`), 상자 1개, 숲 입구 `portal_forest` |
| `forest` | 약초 3~5개(`herb_*`), 일반 적 없음(v0.1), 필드 보스 1마리(**보스 결계** 안 — 진입 시 회복, 3.6), 체크포인트 `cp_forest` |
| (선택) `arena` | 기존 훈련장 보스(`default`)와 싸우는 곳. 회귀 확인용 |

- 맵은 평면 + 장애물 몇 개면 충분. 길찾기 실패(`unreachable`)를 확인할 수 있도록 **닿을 수 없는 위치 1곳**(울타리 안 상자 등)을 둔다.

### 2.2 튜토리얼 퀘스트 (데이터 `Assets/QA/Data/Resources/QaData/play/quests.json`)

| id | 목표 | 확인하려는 것 |
|---|---|---|
| `q_tut_01` | 촌장에게 말 걸기 | move_to → interact(talk), 대화창 선택지 `ui_click` |
| `q_tut_02` | 약초 3개 채집 → 촌장에게 반납 | 여러 대상 순회, 진행도 `progress` 읽기 |
| `q_tut_03` | 인벤토리를 열고 "작은 물약"을 장착 슬롯(퀵슬롯)에 등록 | UI 창 열기·닫기, 버튼 가림(`blocked_by_modal`) |
| `q_tut_04` | 상인에게 물약 2개 구매 (골드 부족 분기 포함) | 상점 UI, 실패 메시지 읽기 |
| `q_tut_05` | 숲의 늑대왕 처치 → 경비에게 보고 | **전투 인계**, 패배 시 체크포인트 부활, 재도전 |

- 퀘스트 정의 형식 (제안, 바꿔도 됨 — 바꾸면 이 표에 맞춰 문서화):
  ```json
  {"id":"q_tut_02","title":"숲의 약초","giver":"npc_elder","requires":["q_tut_01"],
   "objectives":[{"id":"o1","kind":"collect","item":"herb","count":3,"text":"약초 3개 채집","hint_targets":["herb_01","herb_02","herb_03"]},
                 {"id":"o2","kind":"talk","target":"npc_elder","text":"촌장에게 돌아가기"}],
   "rewards":{"gold":30,"items":[{"id":"potion_small","count":2}]}}
  ```
- 대화도 데이터로 (`play/dialogues.json`): 노드·선택지·조건(퀘스트 상태)·결과(퀘스트 수락 등).
- **의도적 함정 1~2개**를 넣는다: 예) 선택지 "나중에"를 고르면 퀘스트가 수락되지 않음, 상점에서 골드가 부족하면 구매 버튼 비활성. (LLM 이 관찰을 제대로 읽는지 보는 용도)

### 2.3 필드 보스

- `forest_wolf_king`: **기존 `BossSpec` JSON 형식**으로 새 보스를 만든다 (`QaData/bosses/forest_wolf_king.json`).
- 학습 쪽이 이 보스로 파라미터를 학습할 수 있어야 하므로 **밸런스 모드에도 노출**한다: `scenarios` 에 이 보스를 쓰는 시나리오 `forest_wolf_king` 을 추가 (기존 `base` 는 그대로).
  - 밸런스 프로토콜은 `run_episode(class, scenario)` 로 판을 정하고 `boss` 인자가 없다. 보스는 시나리오가 정한다.
  - 시나리오의 선택 필드 `boss`(생략 = `"default"`)는 **이미 구현되어 있다** (`Data/Spec/BossSpec.cs:122` `SpecJson.Str(d, "boss", "default")`, `SpecRepository.cs:68` 이 `bosses/<boss>.json` 을 읽고 `scale`/`set` 적용).
    **코드 변경 없이 데이터만 추가**한다: `bosses/forest_wolf_king.json` + `scenarios.json` 에 `"forest_wolf_king": {"description":"숲의 늑대왕", "boss":"forest_wolf_king"}`.
    (지금 `scenarios.json` 의 기존 시나리오는 모두 `boss` 생략 = `default` 이므로 그대로 둔다.)
  - 필드의 늑대왕 조우 = 시나리오 `forest_wolf_king` (조우 → 시나리오 대응은 `world.json` 에 둔다). 로드아웃 키도 `(class, scenario)`.
  - 이것은 정의서 데이터 추가(부 버전 호환)이므로 프로토콜 변경이 아니다. `game_version` 만 올린다.
- 난이도: 손 튜닝 default 로 전사 클리어 50~80% 정도 (학습 효과가 보이도록 100% 근처는 피함).

## 3. 구현 모듈 (권장 구조)

```
Assets/QA/Play/
  Server/      PlayServer, PlaySession, PlayMessages (P 상수), 오류 코드    ← 기존 QaServer 의 전송부 재사용
  World/       WorldState(순수 C#), QuestSystem, DialogueSystem, Inventory, Shop, Checkpoints, PlayRng
  Perception/  QaTag(MonoBehaviour), Visibility, SemanticObserver, HierarchyObserver, StableIds
  Actions/     IPlayAction, MoveTo, Interact, UiClick, UiInput, UseItem, Engage, Wait, ActionRunner
  Combat/      EncounterDetector, CombatBridge, Loadout
  Log/         PlayLog
Assets/Presentation/Play/   마을·숲 씬, NPC·플레이어 표현, uGUI 창들 (대화·퀘스트·인벤토리·상점·HUD)
Assets/QA/Data/Resources/QaData/play/   quests.json, dialogues.json, items.json, world.json(엔티티 배치·id)
```

### 3.1 Boot / Server

- `QaBoot` 에 `-qaPlay` 분기 추가: 있으면 `PlayServer` 를 열고 플레이 씬을 로드, 없으면 지금 그대로.
- 추가 인자: `-qaPlaySeed <n>`(기본 reset seed), `-qaPlaySpeed <x>`(행동 처리 중 시간 배속, 창 모드 관람용, 결과에 영향 없음), `-qaPlayOmniscient`.
- 시작 시 stdout 에 `LISTENING <port>` (기존과 같음). 창 모드와 `-batchmode -nographics` 둘 다 동작.
  - 헤드리스에서 카메라 시야·UI 레이캐스트가 안 되면(확인 필요) **그 사실을 `PROTOCOL_CHANGE_REQUEST.md` 에 적고** 우선 창 모드만 지원해도 된다.
- 메시지 처리: `hello`(protocol=`"play"` 확인), `play_describe`, `set_loadout`, `reset`, `observe`, `act`, `get_log`, `bye`.
  `reset` 인자는 `seed`·`class` 뿐 (시작 지점 옵션 없음 = 항상 새 게임). `-qaPlaySeed` 는 `reset.seed` 생략 시 기본값.
  `reset` 전 `observe`/`act` → `error(not_reset)`. 전투 중 `trigger_response` 외 → `error(busy)`.

### 3.2 세계 정지·시간

- `PlayClock`: 게임 시간은 `ActionRunner` 가 고정 dt(예: 0.05초)로 `World.Step(dt)` 을 호출할 때만 흐른다.
- 창 모드 표시를 위해 실제 프레임과 동기화할 때는 "한 프레임에 k 스텝"(`-qaPlaySpeed`)으로 진행하되, **로직 결과는 dt·스텝 수로만 결정**.
- 응답 송신 후에는 Step 을 부르지 않는다 = 정지. 화면은 마지막 상태를 그대로 그린다.

### 3.3 QaTag (어노테이션)

```csharp
public sealed class QaTag : MonoBehaviour {
    public string id;            // 안정 id: "npc_elder", "herb_01", "ui.dialog.choice.0"
    public QaRole role;          // Npc, Item, Portal, Container, Enemy, Ui, Area
    public string label;         // 플레이어에게 보이는 이름 (현지화 문자열 그대로)
    public string[] actions;     // "talk", "pickup", "open", "use", "enter", "engage"
    public string[] tags;        // "quest_giver", "merchant" …
    public bool alwaysKnown;     // 시야 밖이어도 관찰에 포함 (미니맵·퀘스트 마커처럼 플레이어가 아는 것)
}
```
- id 는 **데이터(`world.json`) 또는 프리팹에 고정**. `GameObject.name`, `GetInstanceID()` 를 id 로 쓰지 않는다.
- 동적으로 생기는 것(드롭 아이템, 대화 선택지)은 규칙으로 id 생성: `drop_<seq>`, `ui.dialog.choice.<i>`.
- 퀘스트 목표가 가리키는 대상이 보이면 `marker`(`quest_available`/`quest_turn_in`/`objective`) 를 채운다 — 화면의 느낌표·마커와 같은 정보.

### 3.4 Perception (관찰)

**지각 가능성 판정 (`Visibility`)** — omniscient 가 아니면 모두 적용:
- 월드: `activeInHierarchy` && 렌더러 `isVisible`(또는 카메라 frustum 판정 — 헤드리스 대비 수학 판정 권장) && 플레이어 카메라 기준 가림 없음(선택, v0.1 은 생략 가능) || `alwaysKnown`
- UI: 활성 Canvas, 조상 `CanvasGroup.alpha > 0.01`, RectTransform 이 화면 안, 텍스트가 빈 문자열 아님
- `interactable` = `Selectable.IsInteractable()` && 요소 중심에서 `EventSystem.RaycastAll` 첫 결과가 자기(또는 자식)

**SemanticObserver** — `PLAY_PROTOCOL.md` 4.5 의 JSON 을 만든다.
- `player`, `quests`(활성·완료 가능 퀘스트와 목표 진행도), `screen.modal` + `screen.ui`, `entities`(거리순 최대 32), `inventory`, `events`(직전 관찰 이후).
- UI 자동 추출: `Button`, `Toggle`, `TMP_InputField`, `TMP_Dropdown`, `Slider` 와 `TMP_Text`. QaTag 가 없으면 id = 부모 경로 기반 (`ui.<창 QaTag id>/<자식 이름>`), 같은 이름 형제는 `#index`.
- 리치텍스트 태그는 제거한 순수 텍스트.
- 숫자 반올림: 위치 0.1, 거리 0.1, 비율 0.01 (토큰 절약 + 결정성 비교 쉬움).

**HierarchyObserver** — 4.5 hierarchy 모드: `root` 부터 `max_depth` 까지 `{id,name,active,components,text,interactable,children}`. 같은 지각 필터 적용.

### 3.5 Actions

각 행동은 `IPlayAction { Start(args); Status Step(dt); }` 로, `ActionRunner` 가 완료/실패/중단까지 Step 을 돌린다.

| 행동 | 구현 요점 | 실패 사유 |
|---|---|---|
| `move_to` | `NavMesh.CalculatePath` → 경로점을 고정 dt 이동. `interact_range` 안이면 done | `unknown_target`, `not_visible`, `unreachable`, `timeout` |
| `interact` | 범위 안이면 동사 실행 (대화창 열기, 줍기 …). **자동 접근 안 함** | `out_of_range`, `not_interactable`(동사 미지원), `blocked_by_modal` |
| `ui_click` | RectTransform 중심 → 화면 좌표 → `PointerEventData` 로 enter/down/up/click (`ExecuteEvents`). `onClick.Invoke()` 직접 호출 금지 | `unknown_target`, `not_interactable` + `reason_detail`(가린 요소 id) |
| `ui_input` | `TMP_InputField.text` 설정 + `onEndEdit` | 위와 같음 |
| `use_item` | 인벤토리 로직 호출 (UI 를 거치지 않는 지름길 — 인벤토리 UI 테스트는 `ui_click` 으로) | `unknown_target`, `invalid_state` |
| `engage` | 대상 적에게 접근 → 전투 시작 | `unreachable` 등 |
| `wait` | `seconds` 또는 `until` 사건 | — |

- 공통: 행동 중 대화창·컷신이 열리거나 전투가 시작되면 `interrupted`.
- 모든 행동은 `max_action_seconds`(기본 60 게임초) 를 넘으면 `timeout`.
- 결과에는 항상 새 semantic observation 을 싣는다.

### 3.6 Combat (전투 인계)

- `EncounterDetector`: 적의 어그로 반경 진입 또는 `engage` → 전투 시작. **클라이언트(LLM) 판단을 기다리지 않는다.**
- `CombatBridge`:
  1. 조우 seed = `PlayRng` 에서 결정적으로 (조우 순번 기반). `combat_started` 송신.
  2. `Loadout` 에서 (class, scenario) 항목 조회 → params. 없으면 정의서 default, `loadout.matched=false`.
  3. **시작 상태 `full` = 게임 규칙** (사용자 결정 2026-11-22): 보스 조우는 **"보스 결계"** 안에서 일어나고, 결계에 들어서면 체력·자원·포션 수가 학습 판 시작과 같게 회복된다.
     화면에도 회복 연출·안내 문구를 보여 주고(관찰 `events` 에 `barrier_restore`), 필드 상태를 전투로 끌어오지 않는다 (`PLAY_PROTOCOL.md` 6장).
     - **회복 직전의 필드 상태를 기록**한다: `combat_started.field_state = {hp_ratio, resource_ratio, potions, deaths_so_far}`. 학습 쪽이 v0.2(상태 이어받기 학습)의 시작 상태 분포로 쓴다.
  4. `new CombatSim(spec, boss, params, seed, seedTok, cfg, triggers, onTrigger)` — `onTrigger` 는 `CombatEpisodeRunner` 와 같은 방식으로 `trigger` 를 보내고 `trigger_response` 를 기다림 (`episode_id` 대신 `encounter_id`).
     가능하면 `CombatEpisodeRunner` 의 트리거 왕복·결과 생성 코드를 **공유 함수로 빼서** 두 모드가 같은 코드를 쓰게 한다 (밸런스 모드 결과가 바뀌지 않는지 T1 로 확인).
  5. 화면: `BattleViewer` 처럼 Sim 상태를 읽어 필드 위에 그린다 (1차원 거리 → 필드 좌표 변환). 로직은 화면에 의존하지 않는다.
  6. 종료: `combat_ended`(result = `episode_result.result` 와 같은 필드 + `aftermath`). 승리 → 전리품·퀘스트 갱신. 패배 → `cp_forest` 부활, 보스 체력 회복.
  7. 이어서 진행 중이던 행동을 `interrupted(by:"combat")` 로 끝낸다.
- `Loadout` 검증은 `ClassSpec.ResolveParams` 와 같은 규칙 (`unknown_param`, `param_out_of_range`), 시나리오 없음 → `unknown_scenario`, 항목의 `boss` 가 시나리오 보스와 다름 → `boss_mismatch`.

### 3.7 PlayLog

- 세션의 모든 요청·응답 요약·사건을 `[game_time, kind, payload]` 로 쌓는다. `get_log` 로 반환.
- 창 모드에서는 화면 구석에 최근 행동 5개를 uGUI 로 표시 (관람용, 관찰 대상에서 제외 — `QaTag` 없이 `QaIgnore` 표시).

## 4. 명령행 정리

```
Game.exe -qaPlay -qaPort 7800                       # 창 모드 플레이 서버
Game.exe -qaPlay -qaPort 7800 -qaPlaySpeed 4        # 관람 배속
Game.exe -qaPlay -qaPort 7800 -qaPlayOmniscient     # 디버그: 숨은 것까지 관찰
Game.exe -batchmode -nographics -qaPlay -qaPort 7800  # 헤드리스 (지원 가능하면)
Game.exe -batchmode -nographics -qaPort 7777        # 기존 밸런스 QA (변화 없음)
```

## 5. 단계 (나눠서 빌드해도 됨)

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| P1 | Play 서버 뼈대: hello/play_describe/reset/observe/bye, 마을 1곳, NPC 1명, `move_to`·`interact(talk)`·대화 `ui_click` | T2, T3 |
| P2 | 퀘스트·대화 데이터, 인벤토리·상점 UI, 튜토리얼 01~04, hierarchy 관찰, PlayLog | T4 |
| P3 | 숲·필드 보스·`set_loadout`·전투 인계·트리거 왕복·부활, 밸런스 모드에 새 보스 시나리오 노출 | T5, T6 |
| P4 | 결정성·헤드리스·관람 배속 정리 | T7 |

각 단계 끝에 `game_version` 을 올리고, 무엇을 했는지 `README.md` 에 한 단락 남긴다.

## 6. 자체 검증 (Unity 쪽에서 실행)

학습 쪽 `check-play` 는 아직 없다. 그때까지 `QaTools~/` 에 **LLM 없는 스크립트 클라이언트**(파이썬 표준 라이브러리만)를 두고 아래를 확인한다.

| # | 검사 | 기준 |
|---|---|---|
| T1 | 밸런스 모드 회귀 | `check-game` 15/15 PASS, 기존 seed 몇 개의 `episode_result` 가 변경 전과 완전히 같음 |
| T2 | 핸드셰이크 | protocol 불일치 → `error(protocol_version)`, `reset` 전 `act` → `error(not_reset)` |
| T3 | 지각 필터 | 시야 밖 NPC 는 `entities` 에 없음, omniscient 에서는 있음. 팝업에 가린 버튼은 `interactable:false`, 그 버튼 `ui_click` → `failed(not_interactable)` + 가린 요소 id |
| T4 | 튜토리얼 스크립트 완주 | 고정 행동열로 `q_tut_01`~`04` 완료. 닿을 수 없는 상자 `move_to` → `unreachable`. 골드 부족 구매 → 실패가 관찰에 보임 |
| T5 | **전투 동일성** | 플레이 모드 조우 result == 밸런스 서버 `run_episode`(같은 class·시나리오·seed·params, 같은 트리거 응답) result. 필드 전체 일치. 늑대왕은 시나리오 `forest_wolf_king`, `combat_started.seed` 를 그대로 씀 |
| T6 | 전투 인계 | `move_to` 중 어그로 → `combat_started` → `trigger`(loadout 에 triggers 있을 때) → `combat_ended` → `action_result(interrupted, combat)` 순서. 전투 중 `observe` → `error(busy)`. 패배 시 체크포인트 부활. 체력을 깎은 채 결계에 들어가면 `combat_started.field_state` 에 깎인 값이 찍히고 전투는 풀 상태로 시작 |
| T7 | 플레이 결정성 | 같은 `reset.seed` + 같은 행동열 2회 → `get_log` 의 결과 부분이 같음 |
| T8 | 새 게임 시작 | `reset` 을 퀘스트 진행 후 다시 보내면 퀘스트·인벤토리·골드·위치가 첫 장면 상태로 완전히 돌아감. 밸런스 모드(`-qaPort` 만)에서는 플레이 씬·월드 데이터가 로드되지 않음 |

## 7. 확인·질문이 필요한 경우

- 헤드리스에서 UI 레이캐스트·시야 판정 가능 여부
- 퀘스트·대화 데이터 형식을 제안과 다르게 할 경우
- 1차원 `CombatSim` 을 필드 좌표에 그리는 방식이 어색해서 전투 로직을 바꾸고 싶어질 경우 → **바꾸지 말고 요청서로** (학습 결과 무효화)

모두 `PROTOCOL_CHANGE_REQUEST.md` 에 적고 사용자에게 알린다.
