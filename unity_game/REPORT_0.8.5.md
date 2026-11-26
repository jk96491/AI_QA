# QaArena 0.8.5 — 증류 평가 요청 반영 (DISTILL_EVAL_REQUEST.md A·B·C)

빌드 `Build/QaArena.exe` **0.8.5** (2026-11-26). 플레이 프로토콜 **0.3 그대로** (hello 버전 유지), 선택 기능 4.4.1·4.11 선언.
밸런스 모드·전투 수치·BT·보스 변경 없음 (T1 21/21 동일).

## A. seed 가 바꾸는 것 (PLAY_PROTOCOL 4.4 "게임이 정하고 문서에 적는다")

`reset.seed` → 배치 전용 난수 (`Placement.LayoutRng(seed)`, 세계 Rng·조우 seed 4.7 과 별개 — 전투 쪽 seed 의존은 그대로).

| 대상 | 흔들림 (기준 위치 ±, 0.1 m 단위) |
|---|---|
| 약초 herb_01~04 | ±3.0 m |
| 늑대왕 wolf_king 대기 위치 | ±2.0 m |
| 경비병 npc_guard | ±2.0 m |
| 상인 npc_merchant | ±1.5 m |
| 촌장 npc_elder | ±1.0 m |
| 플레이어 마을 시작 위치 | ±1.5 m (reset 때만, 지역 이동 시작점은 그대로) |

바뀌지 않는 것: 엔티티·퀘스트·UI id, 목표 글, hint_targets, 포털·체크포인트·울타리 안 상자 위치, 장애물, `known:"marker"` 규칙.
배치 조건 (못 맞추면 다시 뽑고 24번 실패하면 기준 위치): 지역 경계 1.5 m 안쪽, 장애물 밖, 지역 시작점에서 상호작용 거리까지 도달 가능,
다른 엔티티와 1.5 m 이상, **적 어그로 반경 + 2 m 밖** (채집물·NPC·입구가 늑대왕 어그로 안에 들지 않게). 데이터: `play/world.json` 의 `jitter`, `start_jitter`, `layouts`.

## B. `reset_options` 선언 원문 (이름은 요청서 그대로)

```json
"reset_options": [
  {"name": "start_gold", "type": "int", "min": 0, "max": 200, "default": 20, "description": "시작 골드"},
  {"name": "start_potions", "type": "int", "min": 0, "max": 5, "default": 0, "description": "시작 인벤토리 작은 물약 수 (퀵슬롯에는 등록되지 않음)"},
  {"name": "layout", "type": "enum", "values": ["a", "b", "c"], "default": "a", "description": "채집물·NPC·늑대왕 대기 위치 변형 (a = 기본 배치). seed 는 같은 변형 안의 흔들림"}
]
```
- `start_potions` 기본값 = **0** (지금 시작 인벤토리는 비어 있다).
- `layout` 은 seed 와 별개 축: b·c 는 약초 4개·NPC 3명·늑대왕의 기준 위치가 다른 지도 변형이고, seed 는 그 위에서 흔든다. 경비병은 모든 변형에서 "마을 남동쪽", 늑대왕은 "숲 북쪽" (퀘스트 글과 맞음).
- 검사: 모르는 키·범위 밖·정수 아님·모르는 layout → `bad_request` (이전 상태 유지). 빠진 키 = default.
- `play_log` reset 항목에 **항상** 확정 값 `options` (기본값 포함): `{"seed":1,"class":"warrior","options":{"start_gold":20,"start_potions":0,"layout":"a"},"omniscient":false}`.
- 옵션 값 자체는 관찰에 넣지 않음 (골드·인벤토리·위치 결과만 보임).
- `start_gold: 0` → 약초 보상 30G 로 물약 1개만 살 수 있어 q_tut_04(2개 구매)가 막힌다. 튜토리얼에 다른 골드 입수 경로는 없다 — 의도한 평가 조건으로 그대로 둠.

## C. snapshot / restore — 지원 (`capabilities: {"snapshot": true}`)

- 저장 범위: 세계 전부 (위치·엔티티 활성·퀘스트 진행·인벤토리·골드·퀵슬롯·창/대화/상점/팁 상태·플래그·시간·난수 상태·조우 순번 k·전투 사망 누계·options), 로드아웃, input_mode, `play_log`.
- `restore` → 그 시점 관찰 (events 비움). 같은 snapshot 으로 여러 번 restore 가능. snapshot/restore 자체는 로그에 항목을 남기지 않는다 (restore 하면 로그가 저장 시점 그대로).
- 관찰 `seq` 는 restore 해도 계속 증가 (되돌리지 않음).
- 상한 연결당 64개 (넘으면 오래된 것부터 삭제), 연결이 바뀌면 전부 삭제. 없는/지운 id → `bad_request`, reset 전 → `not_reset`, 전투 중 → `busy`. 창·헤드리스 동일.

## 검증 결과

| 검사 | 결과 |
|---|---|
| `check-play --only TD` (헤드리스 7812) | **15/15 PASS** — T-V seed 1~5 → 숲 배치 5가지, T-R 전 항목, T-S 전 항목 |
| `check-play` 전체 (7810/7811 omni/7812/7813, 로드아웃 20261123-230419·203248) | **126/127** — 실패 1개는 아래 |
| 도달성 스윕 (omniscient, seed 1~20 × layout a·b·c = 60판) | 문제 0: NPC 3명 move_to done, 약초 4개 모두 줍기 done, 우연한 전투 0 |
| `balance_qa check-game` (7813) | PASS |
| T1 `balance_snapshot.py diff` (기준 0.8.1) | 21/21 동일 |

**T4/T7 스크립트 좌표 영향 (학습 쪽 수정 대상)**:
- 실패 1개 = T4 `reset → 첫 장면` 의 `player.pos == [0,0,0]` — 시작 위치를 ±1.5 m 흔들었기 때문 (요청 A). 기대값을 "마을 안" 또는 seed 3 의 실제 값으로 바꾸면 된다.
- T4 고정 행동열 튜토리얼 완주와 T7 결정성(seed 11·12)은 이번 측정에서 **PASS** (약초 근처 좌표 `[-4,0,-28]`·`[4,0,-23]` 가 흔들린 위치에서도 아직 상호작용 거리 안). 다른 seed 를 쓰면 깨질 수 있다 — 좌표 대신 `move_to target=herb_xx` 권장.
- Unity 자체 `QaTools~/play_check.py` 도 같은 사정 (이번엔 돌리지 않음).

## 바뀐 파일 (unity_game 안)

- `Assets/QA/Play/World/StartConditions.cs` (새 파일): `ResetOptions` (선언·검사·로그), `Placement` (seed·layout 배치)
- `Assets/QA/Play/World/WorldState.cs`: `EntityState.X/Z` (판별 위치), 생성자 options, `Clone()` (snapshot)
- `Assets/QA/Play/World/PlayData.cs`: `jitter`, `start_potions`, `start_potion_item`, `start_jitter`, `layouts` 읽기·검증
- `Assets/QA/Play/Server/PlaySession.cs`: `reset.options`, `play_description.reset_options`·`capabilities`, `snapshot`/`restore`
- `Assets/QA/Play/Actions/PlayActions.cs`, `Assets/Presentation/Play/PlayView.cs`: 엔티티 위치를 `EntityState` 에서 읽음, 새 세계(reset·restore)면 장면 다시 짓기
- `Assets/QA/Sim/Rng.cs`: `Clone()` (수열 불변), `Assets/QA/Play/Log/PlayLog.cs`: `Save/Restore`
- `Assets/QA/Data/Resources/QaData/play/world.json`: jitter·layouts, `game.json`: game_version 0.8.5
