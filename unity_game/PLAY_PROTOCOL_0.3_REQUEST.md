# 플레이 프로토콜 v0.3 요청 + 첫 LLM 플레이 발견 사항 (학습 플랫폼 → Unity)

- 작성: 학습 쪽, 2026-11-23
- 근거 1: **첫 실제 LLM 플레이**. Claude Code 세션이 직접 플레이어가 되어(`python -m play_agent relay` + `step`, API 호출 없음) QaArena **0.7.0** 튜토리얼 5개를 모두 완료했다.
  기록 `reports/relay-20261123-215152/` (`run.json` 행동·판단, `play_log.json` 게임 로그). 행동 76, 늑대왕은 학습 BT 가 클리어 (308s, 사망 1).
- 근거 2: 사용자 요청 "플레이하면서 생각한 내용이 게임에 표기되도록" → 계약 `../docs/PLAY_PROTOCOL.md` **v0.3** (4.10 `pilot_note`).
- **먼저 할 일**: `PLAY_PROTOCOL_0.2_FOLLOWUP.md` 의 F1~F3 이 0.7.0 에도 아직 없다 (hello 가 `"0.1"` 만 받음). 이 문서의 P1 이 F1 을 대신한다 (0.2 를 건너뛰고 바로 0.3).
- 밸런스 모드(T1, `PROTOCOL.md` v1.3)는 건드리지 않는다.

## 1. 요청 — 플레이어 생각 표시 (`pilot_note`, v0.3)

| # | 항목 | 요청 | 검증 |
|---|---|---|---|
| P1 | 프로토콜 버전 | `PP.ProtocolVersion = "0.3"`. 0.x 규칙대로 주.부 일치만 받는다 (학습 쪽 클라이언트가 0.3 → 0.2 → 0.1 순으로 시도하므로 0.3 만 받아도 된다) | hello 0.3 → ok, 0.1 → `protocol_version` |
| P2 | `play_description.pilot_notes` | `{"max_chars": 200, "kinds": ["thought","plan","finding"]}` 추가. 이 필드가 있어야 클라이언트가 메모를 보낸다 | describe 에 필드 있음 |
| P3 | 메시지 `pilot_note` → `pilot_note_ok` | 계약 4.10 그대로. 세계 시간 0초, 게임 상태·난수·관찰 무관. `reset` 전 `not_reset`, 전투 중 `busy`, 잘못된 `kind`·빈 `text` → `bad_request` | 아래 T-N |
| P4 | 로그 | `play_log` 에 `[t,"pilot_note",{"kind","text"}]` | `get_log` 에 보임 |
| P5 | 화면 표시 (창 모드) | 아래 1.1 | 스크린샷 |

### 1.1 화면 표시 사양 (`Presentation/Play/PlayView.cs` 쪽)

- **"QA 플레이어" 패널**: 화면 왼쪽 아래(퀵슬롯 HUD 와 겹치지 않게), 반투명 배경, **최근 4개**를 위→아래(최신이 맨 아래). 줄마다 종류 배지:
  `생각`(thought, 흰색/회색) · `계획`(plan, 하늘색) · `발견`(finding, 주황색 + 굵게). 최신 줄은 밝게, 이전 줄은 흐리게.
- **말풍선**: 가장 최근 메모(thought·plan)를 플레이어 캐릭터 머리 위에 실시간 4초. `finding` 은 말풍선 대신 화면 위쪽 토스트 4초 (발견이 눈에 띄게).
- **입력·관찰에 영향 금지** (중요):
  - 패널·말풍선·토스트는 `CanvasGroup.blocksRaycasts = false` / `interactable = false` — `ui_click` 의 가림 판정(`blocked by <id>`)이 바뀌면 안 된다.
  - `QaTag` 를 달지 않는다 → 관찰 `screen.ui`·`hierarchy` 에 나오지 않는다 (플레이어가 자기 메모를 다시 읽지 않게, 관찰 결정성 유지).
- 전투 뷰어(BattleViewer) 중에도 패널은 보인다 (전투는 메모가 안 오지만 직전 판단이 남아 있게).
- 헤드리스(`-batchmode`)는 그리지 않고 로그만. 녹화용으로 숨기는 `-qaNoPilotNotes` (선택).
- 긴 글은 `max_chars` 에서 말줄임(…), 한 줄에 안 들어가면 2줄까지 줄바꿈.

### 1.2 검증 (play_check.py 또는 학습 쪽 `python -m play_agent check-play` 에 추가할 항목)

- T-N1: hello 0.3 ok, describe `pilot_notes` 있음
- T-N2: `observe` → `pilot_note` → `observe` : 두 관찰이 `seq` 말고 같음 (`game_time` 포함)
- T-N3: `pilot_note` 후 `get_log` 에 `pilot_note` 항목, 같은 seed·행동열 재생 로그와 **`pilot_note` 를 뺀 나머지가 같음**
- T-N4: 잘못된 kind → `bad_request`, reset 전 → `not_reset`
- T-N5: 패널이 떠 있는 상태에서 인벤토리 버튼 `ui_click` → 그대로 `done` (가림 없음)
- 창 모드 스크린샷 1장: 마을에서 메모 3종류가 패널·말풍선·토스트로 보이는 것

학습 쪽은 이미 준비됨: `PlayClient.note()`, `relay`/`step --think "..." --kind plan`, `LlmPilot` 은 Claude 의 텍스트 응답을 `thought` 로 보낸다. 0.3 미만 게임에는 보내지 않고 `run.json.pilot_notes` 에만 남긴다.

## 2. 첫 LLM 플레이에서 나온 것

| # | 발견 | 판단 | 요청 |
|---|---|---|---|
| G1 | **경비병(npc_guard) 위치를 알 수 없다.** `q_tut_05` 의 보고 대상인데 퀘스트 일지·촌장 대화·`hint_targets` 모두 id 만 있고, 플레이어는 경비병을 한 번도 만난 적이 없다(퀘스트는 물약 구매로 자동 수락). 마을 (34,-22)은 시작점·상인·촌장·숲 입구 동선에서 멀어 마을과 숲을 다 돌아도 못 찾았고, 결국 `world.json` 을 보고 갔다 — 일반 플레이어라면 여기서 막힌다 | **개선 필요** (버그 아님, 진행 막힘 위험) | ① 목표 문구에 장소: `"마을 남동쪽 초소의 경비병에게 보고"` ② 늑대왕을 잡은 직후 이벤트·안내 또는 촌장/상인 대화 한 줄로 경비병 위치 언급 ③ (선택) 퀘스트 대상이 시야 밖이면 HUD 에 방향 표시 |
| G2 | 상점: 20G 일 때 25G `작은 물약` 구매 버튼은 눌리고(→ "골드가 부족합니다" + `purchase_failed`), 80G `큰 물약`은 비활성 | 코드 확인 결과 **의도된 함정 두 종류** (`WorldState.cs:395`). 플레이어는 둘 다 올바르게 처리함 | 변경 없음. (참고: 사람이 보기엔 규칙이 달라 보인다 — 바꾸려면 사용자 결정) |
| G3 | 늑대왕 전투에서 1회 사망했는데 퀵슬롯에 등록한 인벤토리 물약 4개가 그대로 — q_tut_03 에서 퀵슬롯에 등록시켜 놓고 전투에서 안 쓰이니 플레이어는 버그로 본다 | **사용자 결정 2026-11-23: 전투에서 인벤토리 물약을 실제로 쓴다** | 아래 3장 (C1~C5) |

## 3. 요청 — 전투 물약 = 인벤토리 (계약 v0.3 4.7·6장)

| # | 항목 | 요청 | 검증 |
|---|---|---|---|
| C1 | 가져갈 물약 | 전투 시작 시 퀵슬롯에 등록된 **첫 물약 아이템**의 인벤토리 수 `available`, 직업 전투 물약 수 `cap`(`classes[].stats.potions`, 전사 3) → **`carried = min(available, cap)`** 로 `CombatSim` 시작 물약을 설정. 퀵슬롯에 물약 없음 → 0. 체력·자원은 지금처럼 결계 full | 퀵슬롯 비움 → `carried 0`, 전투 로그에 `potion` 없음 |
| C2 | 회복량·쿨다운 | 한 번 마실 때 **전투 규칙**(직업 `potion_heal_ratio` 0.4, `potion_cooldown`) 그대로. 아이템 `heal_ratio` 는 필드 `use_item` 에만. 혼동을 줄이게 `potion_small` 필드 회복량·설명을 0.4 / "체력을 40% 회복한다"로 맞추기를 권장 (`play/items.json`) | 아이템 설명 = 전투 회복량 |
| C3 | 차감 | 전투가 끝나면(승패 무관) 마신 수 `potions_used` 만큼 인벤토리에서 뺀다 → 관찰 `events` 에 `item_removed`, 0개가 되면 퀵슬롯도 비운다 | 늑대왕 후 인벤토리 = 이전 − `potions_used` |
| C4 | 메시지 | `combat_started.potions = {item, available, carried, cap}`, `combat_ended.aftermath.potions_used`, `play_description.combat.encounter_start_state = "barrier_inventory_potions"`, `combat_started.start_state` 같은 값 | 계약 4.7 예시와 같은 키 |
| C5 | 화면 | 0.2 FOLLOWUP **F3** 결계 연출 문구: `"보스 결계: 체력이 회복됩니다. 물약 3개(퀵슬롯)를 가지고 싸웁니다"`. 전투 뷰어 HUD 에 남은 물약 수, 결과 요약에 "물약 n개 사용" | 스크린샷 |

- **T5(학습=실전 동일성)** 는 `carried == cap` 일 때만 비교한다 (play_check 에서 물약을 cap 개 이상 등록한 뒤 T5 실행). `carried < cap` 전투는 결과가 달라도 정상.
- 학습 쪽 영향: `carried < cap` 으로 시작하는 전투는 학습 분포 밖 (학습 판은 항상 cap 개로 시작). 학습 쪽은 다음 단계로 밸런스 프로토콜에 시작 물약 수(`run_episode.initial_state.potions`, SDK 원본 레포)를 추가해 다시 학습한다 — Unity 쪽은 그때 별도 요청서를 받는다. 지금은 C1~C5 만.

참고(학습 쪽 문제, Unity 할 일 아님): 이번 플레이 로드아웃은 0.6.2 때 학습한 `reports/20261123-003306` 이었다. 다음 플레이부터 0.7.0 학습 결과(`reports/20261123-203248` CMA / `203257` IMPALA)를 쓴다.

## 끝나면

- `game_version` 0.7.1 (또는 다음), `PLAY_MODE_REPORT.md` 에 P1~P5·G1·C1~C5 결과 한 줄씩
- `play_check.py` / `python -m play_agent check-play` 전부 PASS + T-N1~N5, T1 밸런스 회귀 그대로
- 스크린샷 경로를 보고서에 남긴다

## 4. 0.7.1 재플레이 결과 (학습 쪽, 2026-11-23 22:18) — 후속 2건

기록 `reports/relay-20261123-221805/` (+ `play_notes.png`). 튜토리얼 5개 완료, 행동 43, 생각 메모 35개 전부 화면 표시.
P1~P5·G1·C1·C3·C4·C5 확인: 메모 패널·말풍선·종류 배지 보임, 경비병을 게임 안내만으로 찾음, 물약 available 4 → carried 3 → 3개 사용 → 인벤토리 1, `barrier_restore`·`notice` 사건.

| # | 발견 | 요청 |
|---|---|---|
| H1 | **"QA 플레이어" 패널이 대화창과 겹친다.** 왼쪽 아래 패널이 대화창(`ui.dialog.*`) 위에 그려져 패널 첫 줄과 대화 본문(`ui.dialog.text`) 글자가 겹쳐 읽기 어렵다 (스크린샷) | 패널을 대화창 영역 밖(예: 왼쪽 가운데, 지금 행동 로그 아래)으로 옮기거나, 대화·상점·인벤토리 창이 열려 있을 땐 패널을 화면 위쪽으로. 입력·관찰 무영향 규칙은 그대로 |
| H2 | 작은 물약 설명 "체력을 30% 회복" ↔ 전투 회복 40% (C2 권장 미반영) | `play/items.json` `potion_small` 의 `heal_ratio` 0.4·설명 40% 로 맞추기 (필드 `use_item` 회복량도 같이 바뀜) |
