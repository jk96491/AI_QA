# 요청: 증류 평가가 "1판"이 아니게 — seed 변화 · 시작 조건 · 상태 저장 (학습 쪽 → Unity 세션, 2026-11-26)

> 플레이 프로토콜 **0.3 그대로** (hello 버전 유지). B·C 는 0.3 의 **선택 기능**(PLAY_PROTOCOL 4.4.1·4.11, SDK 0.5.0) — 선언하지 않은 클라이언트·게임 모두 지금처럼 동작한다.
> 밸런스 모드·전투 수치 변경 없음. 계약 사본 `docs/PLAY_PROTOCOL.md` (SDK 원본에서 동기화됨).
> 사용자 결정 2026-11-26: "증류는 DAgger 에서 멈추지 않고 DPO·RFT 까지 의미가 있어야 한다".

## 왜

학습 쪽은 작은 로컬 모델(Qwen2.5-1.5B, CPU)을 증류했다 — SFT+DAgger 의 r8 이 튜토리얼 5개를 seed 1~5 모두 완주. 그 뒤 DPO·RFT 는 모두 후퇴했는데, 원인의 절반이 **평가**였다:

1. **seed 가 튜토리얼을 바꾸지 않는다.** 0.8.4 에서 seed 1~5 로 숲에 들어가 보면 배치가 **완전히 같다** (학습 쪽 `check-play --only TD` 의 T-V: 숲 배치 1가지). 교사 기록도 39단계 중 33단계가 seed 와 무관하게 같은 입력이었다. → "5판 5/5" 는 사실상 "1판 1/1".
2. 그래서 기준 모델이 평가를 다 깬 뒤에는 오를 곳도, 안 본 조건도 없다. 후속 학습의 이득(흔들려도 깨는 것, 처음 보는 판에서 깨는 것)을 잴 수 없다.
3. RFT 와 새 DPO 쌍(on-policy)은 **같은 상태에서 후보 행동 여러 개**를 시험한다. 지금은 후보마다 reset + 행동열 재생이라 느리다 (37행동 재생 2.2s × 후보 5 × 단계 수).

## 할 일

### A. seed 가 튜토리얼 판을 바꾼다 (필수, 가장 중요)

- `reset.seed` 가 **세계 배치**를 정하게: 최소한 **숲 약초(herb_01~04) 위치**, 가능하면 늑대(일반 몹)·늑대왕 대기 위치, 마을 NPC 대기 위치 약간(상인·경비병 ±몇 m), 플레이어 시작 위치 약간.
- 지킬 것:
  - **같은 seed → 같은 판** (결정성, 4.8). 창 ↔ 헤드리스 동일.
  - 엔티티 **id·퀘스트 id·목표 글·hint_targets 구조는 그대로** (학습 쪽 전처리가 이 구조를 읽는다). 바뀌는 것은 위치·순서.
  - 모든 seed 에서 튜토리얼이 끝까지 풀린다 (약초가 벽 안·이동 불가 지점에 놓이지 않게). 시야 밖 대상의 `known:"marker"`(0.8.4) 도 그대로.
  - 조우 seed 식(4.7)은 그대로 — 전투 쪽 seed 의존은 지금과 같다.
- seed 가 무엇을 바꾸는지 보고서에 적는다 (PLAY_PROTOCOL 4.4 에 "게임이 정하고 문서에 적는다"로 추가됨).

### B. `reset_options` 선언 + `reset.options` (선택 기능 4.4.1, 권장)

평가 스위트(`play_agent/specs/qa_arena.eval.json`)가 이미 아래 이름으로 조건을 적어 두었다. 선언하면 그 조건이 돌기 시작하고, 선언 전에는 건너뛴다.

```json
"reset_options": [
  {"name": "start_gold",    "type": "int",  "min": 0, "max": 200, "default": 20, "description": "시작 골드"},
  {"name": "start_potions", "type": "int",  "min": 0, "max": 5,   "default": <지금 값>, "description": "시작 작은 물약 수"},
  {"name": "layout",        "type": "enum", "values": ["a", "b", "c"], "default": "a", "description": "채집물·NPC 대기 위치 변형 (a = 지금 배치)"}
]
{"type": "reset", "seed": 3, "class": "warrior", "options": {"start_gold": 0, "layout": "b"}}
```
- 이름·범위는 Unity 판단으로 바꿔도 된다 (바꾸면 보고서에 — 학습 쪽 스위트 파일을 맞춘다). `layout` 은 A 의 seed 변화와 **별개 축**(seed 는 같은 변형 안의 흔들림, layout 은 다른 지도 변형)이면 좋다. 어렵다면 A 만 하고 `layout` 은 빼도 된다.
- 규칙 (4.4.1): 모르는 키·범위 밖 → `error(bad_request)`, 빠진 키 = default, `play_log` 의 `reset` 항목에 `options`, 옵션 값 자체를 관찰에 몰래 넣지 않음 (결과 — 골드 표시·물약 수·위치 — 만 보인다).
- `start_gold: 0` 이면 상인 퀘스트(물약 사기)가 막힐 수 있다 → 그것도 평가 조건이다 (모델이 막혔을 때 어떻게 하는지). 튜토리얼이 원래 골드를 주는 흐름이 있으면 그대로 둔다.

### C. `capabilities.snapshot` + `snapshot`/`restore` (선택 기능 4.11, 여유 있으면)

```json
"capabilities": {"snapshot": true}
{"type": "snapshot"}                 →  {"type": "snapshot_ok", "id": "snap_3"}
{"type": "restore", "id": "snap_3"}  →  observation (그 시점, events 비움)
```
- 저장 범위 = 결정성에 들어가는 모든 것: 세계·퀘스트·인벤토리·골드·퀵슬롯·창(modal)·대화 상태·**난수 상태**·조우 순번 k·로드아웃·`play_log`.
- `restore` 뒤 같은 행동 → 같은 결과·같은 로그 꼬리. 없는 id → `bad_request`, 전투 중 → `busy`, reset 전 → `not_reset`. 연결이 끊기면 사라진다. 개수 상한(예 64)을 넘으면 오래된 것부터.
- 학습 쪽 `btqa_play.branch.Brancher` 가 선언을 보면 자동으로 쓴다 (없으면 재생 — 결과는 같아야 한다).

## 하지 않을 것

- 밸런스 모드(`run_episode`)·전투 수치·BT·보스 패턴 변경 없음 → 밸런스 재측정 불필요해야 한다 (T1 21/21).
- 퀘스트 구조·id·UI id 변경 없음. 상점 구매 버튼 함정(`WorldState.cs:395`) 그대로.
- 숨은 정보 공개 없음 (원칙: 플레이어가 지각 가능한 것만).

## 검증

학습 쪽 검사 (LLM 없음):
```bash
venv\Scripts\python.exe -m play_agent check-play --exe unity_game/Build/QaArena.exe --only TD     # A·B·C
venv\Scripts\python.exe -m play_agent check-play --exe unity_game/Build/QaArena.exe                # 기존 T2~T9 그대로 PASS
venv\Scripts\python.exe -m btqa_play tools --game 127.0.0.1:781x                                  # 선언 검사
```
- **T-V**: 같은 seed → 같은 숲 배치, seed 1~5 → 숲 배치 3가지 이상 (0.8.4 = 1가지, FAIL).
- **T-R** (B 를 하면): 모르는 옵션·범위 밖 → `bad_request`, `start_gold=0` → 관찰 골드 0, `layout` 값마다 배치가 다름·같은 seed+options → 같은 배치, `play_log` reset 항목에 `options`.
- **T-S** (C 를 하면): restore 뒤 같은 행동 → 같은 결과, 다른 행동 뒤 restore → 저장 시점 관찰, restore 하면 `play_log` 도 저장 시점, 없는 id → `bad_request`.
- 기존 T4(스크립트 튜토리얼 완주)·T7(결정성)은 **seed 11·12 고정 좌표**를 쓴다 (`play_agent/check.py` `scripted_run`: 약초 근처 좌표 `[-4,0,-28]`·`[4,0,-23]`). 약초 위치가 seed 로 바뀌면 그 스크립트가 깨질 수 있다 → 깨지면 **스크립트 쪽을 학습 쪽이 고친다** (보고서에 "T4/T7 스크립트 좌표 영향" 으로 적기만). Unity 자체 `QaTools~/play_check.py` 도 같은 사정.

보고: 빌드 번호, seed 가 바꾸는 것 목록, 선언한 `reset_options` 원문, snapshot 지원 여부, TD 결과, 기존 check-play 결과.
