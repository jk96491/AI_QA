# 플레이 모드 완료 보고 (Unity 게임 → 학습 플랫폼)

- 작성: Unity 쪽, 2026-11-23
- 대상 요청: `PLAY_MODE_REQUEST.md` (P1~P4) / 계약 `../docs/PLAY_PROTOCOL.md` v0.1
- 빌드: **QaArena 0.6.2** (`Build/QaArena.exe`). 상세 사용법은 `README.md` "플레이 모드" 절
- `PROTOCOL_CHANGE_REQUEST.md` 는 없음 — 막힌 곳은 없었고, 계약이 정하지 않은 부분은 아래 2장처럼 정해 구현했다. **계약 문서 반영은 학습 쪽 몫** (Unity 쪽은 `docs/` 를 고치지 않음)

## 1. 결과

| 단계 | 버전 | 내용 | 검증 |
|---|---|---|---|
| P1 | 0.6.0 | Play 서버, 마을, move_to·interact(talk)·대화 ui_click, semantic/hierarchy 관찰 | T2, T3 |
| P2 | 0.6.1 | 숲 지역, 퀘스트·조건부 대화·인벤토리·안내 팝업·상점, q_tut_01~04, use_item, PlayLog | T4 |
| P3 | 0.6.2 | 늑대왕(`forest_wolf_king`) + 밸런스 시나리오 노출, set_loadout, 전투 인계·트리거 왕복·체크포인트 부활, engage, q_tut_05 | T5, T6 |
| P4 | 0.6.2 | 결정성·헤드리스·관람 배속 | T7, T8 |
| (추가) | 0.6.2 | **전투 장면 전환**: 창 모드에서 조우 시 암전 → 전투 뷰어 아레나에서 실제 전투 연출 → 필드 복귀 (사용자 요청) | T5·T7 재확인 (창 96/96) |

검증 도구 `QaTools~/play_check.py` (LLM 없는 스크립트 클라이언트, 표준 라이브러리만):
```
venv\Scripts\python.exe unity_game/QaTools~/play_check.py --game 127.0.0.1:7800 --omni 127.0.0.1:7801 --balance 127.0.0.1:7777 --game2 127.0.0.1:7802
```
- 창 모드(`-qaPlaySpeed 64`) **96/96**, 헤드리스(`-batchmode -nographics -qaPlay`) **93/93** (omniscient 인스턴스 항목 제외)
- T1 밸런스 회귀: check-game 15/15, 0.5.0 기준선 고정 seed 21판 `episode_result` **바이트 동일** (`QaTools~/balance_snapshot.py`), 경계 사례 37/37, 판당 시간 동일
- T5: 플레이 조우 result == 밸런스 `run_episode`(같은 class·scenario·seed·params·트리거 응답). 패배 판·트리거 4회 승리 판·학습 params 6판 모두 일치
- T7: 같은 `reset.seed` + 같은 행동열(퀘스트·UI·채집·전투 포함) 2회 → `get_log` 동일, **창 모드 ↔ 헤드리스 사이에서도 동일**
- 전체 사이클 점검(`run/run_full_cycle.py`, GAME_CMD=UNITY, 복사 실행): **PASS** (6단계 OK)
- 학습 결과로 필드 전투: `optimize --scenario forest_wolf_king --budget 1200` (warrior/stable 59% → 98%) 의 `params.json` 을 `set_loadout` 에 넣고 필드에서 6/6 승리

## 2. 계약에 반영해 주세요 (PLAY_PROTOCOL v0.1 → v0.2 제안)

구현하면서 정한 것. 학습 쪽이 받아들이면 문서에, 아니면 Unity 쪽에 수정 요청을.

### 2.1 핸드셰이크·reset
- `hello`: 0.x 동안 **주.부 버전 일치** 요구 (7장 "0.x 는 부 버전도 호환 깨짐" 해석). protocol 이 `"play"` 가 아니면 `protocol_version`
- `reset` 인자는 `seed`·`class` 뿐. 다른 키 → `bad_request`. `seed` 생략 = `-qaPlaySeed`(기본 1), `class` 생략 = warrior
- 새 연결은 `not_reset` 부터, 로드아웃도 비워진다 (연결 단위)

### 2.2 play_description
- `scenarios`: `[{name, boss}]` (밸런스 describe 와 같은 이름)
- `actions`: **실제 지원하는 것만** — `move_to, interact(talk|pickup|open|enter), ui_click, use_item, engage, wait`. `ui_input` 은 없음 (`unknown_action`)
- 추가 필드: `combat.encounters` `[{enemy, zone, scenario, boss}]`, `quests` `[{id,title}]`, `stage`

### 2.3 관찰 (semantic)
- `player.quickslots` (길이 2, null 가능), `player.state` (idle|moving|dialog)
- `quests`: 진행 중만. `state` = `active` | `ready`(반납만 남음), 목표 `{id,text,progress:[n,N],done,hint_targets}`
- 엔티티 `role`: npc|item|portal|container|enemy|area, `marker`: quest_available|quest_turn_in|objective
- `screen.modal`: null|dialog|quests|inventory|shop|**tip**(창 위 안내 팝업)
- omniscient 일 때 숨은 것은 `"hidden": true`
- UI id 목록: README "플레이 모드" 절

### 2.4 행동
- 실패 `reason_detail` 형식: 가림 `"blocked by <ui id>"`, 비활성 `"disabled"`, 범위 밖 `"distance 8.5"`
- `move_to` 중 전투 → `interrupted` / `interrupted_by: "combat"`. **`engage` 는 전투 후 `done`**
- `game_seconds` 에 전투 시간 포함
- 체력이 가득할 때 `use_item`(물약) → `invalid_state`

### 2.5 전투 (4.7)
- 조우 = 밸런스 시나리오 1개 (적 엔티티 데이터의 `scenario`). 로드아웃 키 (class, scenario)
- **조우 seed** = SplitMix64 혼합(`reset.seed + 0x9E3779B97F4A7C15·k`) & 0x7FFFFFFF, k = 조우 순번(1부터). 구현 `WorldState.EncounterSeed`
- `combat_started`: `seq, encounter_id, enemy, boss, class, scenario, seed, loadout{matched,source,persona}, triggers, start_state:"full"`
- `trigger` 에 `seq` 포함. `combat_ended.aftermath` = `{xp, loot:[{id,count}], respawned_at}`
- 전투 중 다른 요청 → `error(busy)` (전투는 계속). 전투 밖 `trigger_response` → `bad_request`
- **결정 필요**: 형식·이름·범위가 틀린 `trigger_response` 는 error 를 보내고 **같은 trigger 를 계속 기다린다** (밸런스 4.4 는 판 중단). 중단이 낫다면 알려 주세요
- 패배 = cleared false 전부(사망 초과·시간 초과·멈춤). 적의 checkpoint 에서 부활, 적은 남고 다음 조우는 새 seed

### 2.6 로그
- `get_log` → `{entries:[[t, kind, payload]], next_seq}`. kind: reset, act, action_result, set_loadout, combat_start, trigger, combat_result + 세계 사건(dialog_*, quest_*, item_*, gold_changed, purchase*, zone_entered, picked_up, combat_*, respawned …)

## 3. 밸런스 계약 쪽 영향
- `describe.scenarios` 에 `forest_wolf_king` 추가 (**패치가 아니라 다른 보스**). 데이터 추가라 v1.2 그대로. `experiments` 의 패치 목록은 이름을 명시해서 영향 없음을 확인했다. "base 외 시나리오 = 패치" 로 가정하는 코드가 생기지 않게 주의
- 늑대왕 손 튜닝 default (stable 200판): **warrior 60% / mage 0% / archer 97%** — 마법사가 이 보스에 매우 약함 (밸런스 발견 후보)
- `CombatEpisodeRunner` 의 트리거 응답 검증을 공유 함수로 분리했다 (동작 동일, T1 확인)

## 4. 전투 장면 (창 모드)
- 조우하면 필드가 암전되고 전투 뷰어(밸런스 모드 학습 판 재생과 같은 연출)로 장면이 바뀐다. 끝나면 결과 배너 후 필드로 돌아온다
- 판 진행·결과는 연출과 무관: 연출기는 세션의 `CombatSim` 을 한 틱씩 진행할 뿐. 장면 전환·결과 배너(약 2.8초)는 응답이 늦게 갈 뿐 세계 시간·결과에 영향 없음
- 배속: `-qaPlayCombatSpeed`(생략 = `-qaPlaySpeed`). 헤드리스는 연출 없이 즉시

## 5. 알려진 제약
- 시야 = 고정 16:9 frustum 수학 판정. **가림(occlusion) 판정 없음** (v0.1 허용)
- 길찾기 = 격자 A* (NavMesh 아님). 의미(done/unreachable)는 같다
- 창 모드에 입력 모듈 없음 → 사람이 창을 클릭·조작할 수 없다 (결정성)
- 트리거 응답 대기 중 Unity 메인 스레드가 멈춘다 — 창이 잠깐 "응답 없음"으로 보일 수 있음 (응답이 오면 계속)
- 헤드리스 Player.log 의 셰이더 `ERROR ... not supported on this GPU` 는 `-nographics` 정상 메시지
- 창 모드 화면은 캡처로 확인함 (한글 TMP 글꼴·HUD·전투 장면 정상). 늑대왕은 전투 장면에서 기존 보스 모델(골렘)을 이름만 바꿔 쓴다
