# 요청: 플레이 모드 행동·안내 선언 (play 0.3 선택 필드 4.2.1) — 학습 쪽 → Unity 세션, 2026-11-24

> 계약 `docs/PLAY_PROTOCOL.md` 4.2.1 (원본은 이제 SDK 레포 `btqa_sdk/docs/PLAY_PROTOCOL.md`). 학습 쪽 Python 은 이제 `btqa_sdk` 를 직접 참조한다 (루트 `btqa_game/` 사본 없음 — Unity 쪽 영향 없음, `Packages/com.btqa.game` 사본은 그대로). **hello 버전은 "0.3" 그대로** — 선택 필드라 안 보내도 지금처럼 동작한다.
> 권장 빌드 번호: 0.8.3 (`PROTOCOL_UPDATE_1.4.md` 와 같은 빌드로 묶어도 된다).

## 0. 배경 — 무엇이 바뀌었나 (학습 쪽, 반영 완료)

- LLM 플레이어 클라이언트(프로토콜 클라이언트·LLM 도구·tool use 루프·relay·LLM 백엔드)를 **SDK `btqa_play`** 로 옮겼다 (BT-QA SDK **0.3.0**). `play_agent` 는 그 위에 학습 결과 로드아웃·전투 응답기만 얹는다.
- **SDK 에는 게임 내용이 없다** (사용자 결정 2026-11-24: SDK 는 정해진 형식으로 받아서 쓴다). 지금 QaArena 의 도구 설명·스키마·관찰 읽는 법·목표는 학습 쪽 **외부 스펙 파일 `play_agent/specs/qa_arena.play.json`** 이 채우고 있다.
- 게임이 `play_description` 에 **행동 설명·인자 스키마·게임 안내·진척 기준을 직접 선언**하면 그것이 외부 스펙보다 우선한다 (키마다). 게임이 정본이 되고, 새 행동을 추가할 때 학습 쪽 파일을 고칠 필요가 없어진다. **출발점 = 위 스펙 파일 내용을 그대로 옮기는 것** (형식이 같다).
- **Unity SDK 패키지(`Packages/com.btqa.game`)는 코드 변화 없음** — `package.json` 버전만 0.2.0 → 0.3.0 (학습 쪽이 `run/run_sync_sdk.py` 로 이미 바꿈). 패키지는 지금처럼 **고치지 않는다** (`SDK_MIGRATION.md`).

## 1. 할 일 — `Assets/QA/Play/Server/PlaySession.cs: Describe()`

### 1.1 `actions[]` 에 `description`·`schema` 추가 (6개 전부)

- `args` 는 지금 그대로 둔다 (사람용 요약, 0.3 미만 클라이언트용). **`schema.properties` 키 = `args` 키** (같은 집합 — 검사함).
- `required` 에 없는 인자 = 선택 (클라이언트가 null 허용으로 바꾸고, null 이면 `act.args` 에서 뺀다).
- 설명은 **QaArena 실제 동작 기준**으로 고쳐 써도 된다 (아래는 SDK 기본값을 다듬은 초안). 실패 `reason` 이 무엇을 뜻하는지 적어 두면 LLM 이 덜 헤맨다.

```csharp
static JObject Act(string name, JObject args, string desc, JObject props, params string[] required) => new JObject
{
    ["name"] = name, ["args"] = args, ["description"] = desc,
    ["schema"] = new JObject { ["type"] = "object", ["properties"] = props, ["required"] = new JArray(required) },
};
static JObject Prop(string type, string desc) => new JObject { ["type"] = type, ["description"] = desc };
```

선언할 내용 (JSON 으로 보인 것 — 위 도우미로 옮긴다):

```json
[
 {"name":"move_to","args":{"target":"entity_id | null","pos":"[x,y,z] | null"},
  "description":"엔티티(target) 또는 좌표(pos=[x,y,z]) 로 걸어간다. 둘 중 하나만 준다. 대상의 상호작용 거리(2.5) 안에 들어가면 done. 시야 밖 대상은 not_visible — 근처 좌표나 지역 입구로 먼저 간다. 길이 없으면 unreachable. 이동 중 적의 어그로 범위에 들어가면 전투가 자동으로 시작되고 학습된 BT 가 싸운다 (interrupted, 결과는 combats).",
  "schema":{"type":"object","properties":{
     "target":{"type":"string","description":"observation.entities[].id"},
     "pos":{"type":"array","items":{"type":"number"},"description":"[x,y,z] 월드 좌표"}},"required":[]}},
 {"name":"interact","args":{"target":"entity_id","verb":"talk|pickup|open|enter"},
  "description":"엔티티와 상호작용. verb 는 그 엔티티 actions 에 있는 것. 범위 밖이면 자동으로 다가가지 않고 out_of_range — 먼저 move_to. 창(modal)이 열려 있으면 blocked_by_modal.",
  "schema":{"type":"object","properties":{
     "target":{"type":"string","description":"observation.entities[].id"},
     "verb":{"type":"string","enum":["talk","pickup","open","enter"]}},"required":["target","verb"]}},
 {"name":"ui_click","args":{"ui_id":"string"},
  "description":"화면 UI 요소를 클릭 (screen.ui 의 id, 또는 hierarchy 노드 id). interactable:false 면 not_interactable — reason_detail 'blocked by <id>' 는 그 창이 가리고 있다는 뜻, 'disabled' 는 비활성.",
  "schema":{"type":"object","properties":{"ui_id":{"type":"string","description":"screen.ui[].id"}},"required":["ui_id"]}},
 {"name":"use_item","args":{"item_id":"string"},
  "description":"인벤토리 아이템을 필드에서 사용 (inventory 의 id). 효과가 없는 상태(체력 가득에서 물약 등)면 invalid_state. 전투 중 물약은 BT 가 퀵슬롯 물약을 쓴다 — 이 행동이 아니다.",
  "schema":{"type":"object","properties":{"item_id":{"type":"string","description":"observation.inventory[].id"}},"required":["item_id"]}},
 {"name":"engage","args":{"target":"entity_id"},
  "description":"적에게 다가가 일부러 전투를 시작한다. 전투는 학습된 BT 가 하고, 끝나면 done (승패는 combats[].cleared). 지면 체크포인트에서 부활하고 적은 남는다.",
  "schema":{"type":"object","properties":{"target":{"type":"string","description":"role=enemy 엔티티 id"}},"required":["target"]}},
 {"name":"wait","args":{"seconds":"number | null","until":"event_kind | null"},
  "description":"세계 시간을 보낸다: seconds 초, 또는 until 사건이 일어날 때까지 중 먼저 (최대 60초). 둘 중 하나는 준다.",
  "schema":{"type":"object","properties":{
     "seconds":{"type":"number","description":"초"},
     "until":{"type":"string","description":"세계 사건 종류 (예: dialog_closed, quest_update, combat_ended)"}},"required":[]}}
]
```

> `wait.until` 의 실제 사건 이름 목록이 고정돼 있으면 `"enum": [...]` 으로 바꿔도 된다 (지금 코드는 아무 사건 종류나 받는 것으로 보임 — `PlayActions.cs:291`).

### 1.2 `pilot_guide`·`progress_keys` 추가

`play_agent/specs/qa_arena.play.json` 의 `pilot_guide.system_prompt`(관찰 필드 읽는 법·큰 규칙)·`default_goal`·`progress_keys` 를 옮기고, 실제 게임에 맞게 고친다. 아래는 `about`·`rules` 예:

```json
"pilot_guide": {
  "about": "QaArena: 마을과 숲으로 된 튜토리얼 RPG. 촌장의 의뢰로 시작해 숲의 늑대왕을 쓰러뜨린다.",
  "rules": [ "...이 게임만의 요령 (아래 규칙대로) ..." ],
  "default_goal": "튜토리얼 퀘스트를 모두 끝까지 완료하라 (진행 중인 퀘스트가 없어질 때까지).",
  "system_prompt": "(스펙 파일의 문단 — 관찰 player/quests/entities/screen/events 읽는 법, modal 처리, 전투·물약·부활)"
},
"progress_keys": ["quests", "player.zone", "inventory", "player.gold", "player.quickslots"]
```

`system_prompt`·`rules` 작성 규칙 (중요):
1. **플레이어가 게임 안에서 알 수 있는 것만** (튜토리얼 팁·NPC 대사·도움말 수준). 숨은 좌표·데이터 파일 내용 금지 — 원칙 "플레이어가 지각 가능한 것만" (1장).
2. **의도적으로 심은 QA 함정·알려진 버그는 쓰지 않는다** (예: 상점 구매 버튼 interactable 함정 `WorldState.cs:395`). 그걸 LLM 이 스스로 찾는지가 QA 다.
3. SDK 공통 규칙은 **도구 사용 방식만** 있다 (한 번에 하나, reason 읽고 방법 바꾸기, 전투는 BT, finish) → 그것은 되풀이하지 않고, 관찰 읽는 법·이 게임의 규칙은 `system_prompt` 에 쓴다.
4. 3~6줄, 한 줄에 하나. 세션 중 바뀌지 않게 (프롬프트 캐시).

후보 (사실인지 확인하고 고르기): 전투 물약 = 퀵슬롯에 등록한 물약만 가져감(최대 3), 퀘스트 일지 창에서 목표 확인, 지면 체크포인트에서 부활.

## 2. 하지 않을 것

- `hello`/`play_description.protocol_version` 은 **"0.3" 그대로**. 0.4(raw 입력)는 사용자 결정 대기 그대로 — `actions_raw` 는 손대지 않는다 (0.4 가 확정되면 같은 `description`·`schema` 를 거기에도 붙이면 된다).
- 전투·BT·밸런스 서버 변경 없음 → 밸런스 결과(T1 21/21)가 바뀌면 안 된다.
- `Packages/com.btqa.game` 수정 금지.

## 3. 검증 (Unity 쪽 포트 7810~7819)

```bash
QaArena.exe -batchmode -nographics -qaPlay -qaPort 7811
venv\Scripts\python.exe -m btqa_play tools --game 127.0.0.1:7811
#   → 외부 스펙 없이도 (--spec none) 행동 6개 모두 "설명/스키마 출처 = game/game", "선언 검사: 통과", 프롬프트에 system_prompt·"qa_arena 안내:" 블록
venv\Scripts\python.exe -m play_agent tools --game 127.0.0.1:7811 --spec none
venv\Scripts\python.exe -m play_agent check-play --exe unity_game/Build/QaArena.exe
#   → 전 항목 PASS (0.8.2 = 127/127), T-D 줄에 "출처 move_to=game/game,... pilot_guide 있음"
```
+ Unity 자체 검증(play_check, T1 밸런스 동일)은 평소대로.

보고: 빌드 번호, `btqa_play tools` 출력의 출처 표·프롬프트 "안내" 블록, `pilot_guide.rules` 최종 문구.

## 4. 같이 전달할 것 (이미 대기 중인 요청)

| 문서 | 내용 |
|---|---|
| `PROTOCOL_UPDATE_1.4.md` | 밸런스 1.4 `initial_state` (QaArenaHost 선언 2줄 + `SetStartHpRatio`) — 학습 쪽 E8(늑대왕 밴딧)이 이걸 기다림 |
| `UI_FOLLOWUP_0.8.2.md` | 화면 겹침 H1(메모 패널 ↔ 대화창)·H3(전투 로그 ↔ QA 패널)·H4(스킬 이름 ↔ 쿨 숫자) |
| 이 문서 | 행동 `description`·`schema` + `pilot_guide` |

세 개를 한 빌드(0.8.3)로 묶어도 된다. 빌드 전 `build.ps1` 이 모든 QaArena 를 끈다는 것을 학습 세션에 먼저 알린다.
