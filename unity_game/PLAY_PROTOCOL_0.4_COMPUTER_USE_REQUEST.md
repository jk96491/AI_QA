# 플레이 프로토콜 v0.4 요청 — 비전 없는 computer use (Unity → 학습 플랫폼)

- 작성: Unity 쪽, 2026-11-23. 대상 계약 `../docs/PLAY_PROTOCOL.md` (현재 v0.3, QaArena 0.7.1)
- 근거: 사용자 목표 "LLM 에이전트에게 **비전 정보 없이 computer use** 를 시켜 본다".
  지금 플레이 모드는 관찰은 이미 비전 없는 구조화 트리(접근성 트리 방식)지만, 행동이 `ui_click(id)`·`move_to(id)` 같은 **id 기반 고수준**이라
  "화면 좌표로 누르고 키를 친다"는 computer use 의 핵심(좌표 추론·가림·입력 순서)을 시험하지 못한다.
- 원칙 유지: 화면 이미지 없음, 세계 정지(턴제), 결정성(같은 seed + 같은 입력열 → 같은 로그), 전투는 학습 BT. 밸런스 모드(`PROTOCOL.md` v1.3)는 건드리지 않는다.

## 1. 요청 요약

| # | 항목 | 내용 |
|---|---|---|
| C1 | 입력 모드 선언 | `play_description.input_modes = ["semantic","raw"]`. `reset` 에 `input_mode` 인자 추가(기본 `semantic` = 지금과 같음). `raw` 세션에서는 id 기반 행동(`move_to`·`interact`·`ui_click`·`engage`·`use_item`) → `error(unknown_action)` — 에이전트가 우회하지 못하게 |
| C2 | 가상 화면 | 좌표계 = **기준 해상도 1280×720 고정** (창 크기·헤드리스와 무관). `play_description.screen = {"width":1280,"height":720,"origin":"top_left"}` |
| C3 | 관찰에 좌표 | `screen.ui[]` 각 요소에 `rect:[x,y,w,h]` (가상 화면, 정수). 월드 `entities[]` 에 `screen_pos:[x,y]`(화면 안일 때만) — 둘 다 지금의 지각 필터를 그대로 통과한 것만 |
| C4 | 저수준 행동 (raw) | 아래 2장 표 |
| C5 | 히트 판정 | `pointer_click(x,y)` 는 그 좌표의 **EventSystem 레이캐스트 첫 대상**이 받는다. 가려졌으면 가린 쪽이 클릭을 받는다 (지금 `blocked by` 를 오류로 주던 것이 실제 결과로 바뀜). 결과에 `hit: <ui id 또는 null>` |
| C6 | 로그 | `play_log` 에 raw 입력 그대로 (`[t,"input",{...}]`) + 맞은 대상. 재현 = 같은 seed + 같은 입력열 |

## 2. raw 행동 (C4)

| 행동 | args | 동작 | 시간 |
|---|---|---|---|
| `pointer_click` | `x, y, button?("left")` | enter→down→up→click 을 그 좌표 레이캐스트 대상에 | 0초 (+UI 정착 프레임) |
| `pointer_move` | `x, y` | 호버만 (툴팁 등) | 0초 |
| `drag` | `x0,y0,x1,y1` | down→drag→drop (인벤토리 끌어다 놓기 등, 지금 게임엔 대상 없음 — 확장용) | 0초 |
| `key_press` | `key` (`"escape"`,`"enter"`,`"i"`,`"q"`,`"1"`,`"2"`…) | 게임 키 바인딩 — 인벤토리 `i`, 퀘스트 `q`, 퀵슬롯 `1`·`2`, 창 닫기 `escape`, 상호작용 `e` | 0초 |
| `key_hold` | `key` (`w`,`a`,`s`,`d`), `seconds` (≤ `max_action_seconds`) | 카메라 기준 방향으로 이동. 장애물에 막히면 멈춤, 전투 감지 시 `interrupted(combat)` | seconds |
| `text_input` | `text` | 포커스된 입력 칸에 (지금 게임엔 입력 칸 없음 — 확장용) | 0초 |
| `wait` | 지금과 같음 | | |

- `key_press "e"` = 상호작용 범위 안 가장 가까운 대상과 상호작용 (id 를 고르지 않는다). 대상 없음 → `failed(no_target)`.
- 좌표가 화면 밖 → `bad_request`. 아무것도 안 맞음 → `done` + `hit:null` (실제 입력처럼 헛클릭은 오류가 아님).
- `key_hold` 의 이동은 고정 dt 수동 루프 (지금 `MoveTo` 와 같은 결정성). 길찾기 없음 — 막히면 에이전트가 돌아가야 한다.

## 3. Unity 쪽 작업 (요청 승인 시)

- `Perception/Observers.cs`: `rect`·`screen_pos` (가상 화면 변환: `CanvasScaler` 기준 해상도 좌표 → 1280×720). 헤드리스도 같은 가상 화면을 쓰도록 `Screen` 대신 기준 해상도로 계산.
- `Actions/`: `PointerClick`·`KeyPress`·`KeyHold`·`Drag`·`TextInput`. 클릭은 지금 `UiClick` 의 포인터 이벤트 경로 재사용, 대상만 좌표 레이캐스트로.
- 키 바인딩 표를 데이터(`play/input.json`)로 두고 `play_description.keys` 로 공개 (LLM 이 키를 추측하지 않게 — 사람에게 보이는 키 안내와 같은 수준).
- `play_check.py` 에 T-R 추가: 같은 튜토리얼을 raw 입력만으로 완주, 가림 팝업 위치 클릭 → 팝업이 받음, raw 세션에서 id 행동 → `unknown_action`, 결정성(창 ↔ 헤드리스 로그 동일).

## 4. 학습 쪽 작업 (play_agent)

- `PlayClient`: `input_mode`, raw 행동 래퍼. `LlmPilot`/`relay` 도구 목록을 `input_mode` 에 따라 raw 행동으로 생성.
- 리포트 지표: 행동 수, 헛클릭(`hit:null`), 가려진 클릭, 막힌 이동 — semantic 모드와 같은 튜토리얼 비교.

## 5. 결정 필요 (사용자)

1. **이동**: raw 에서 `key_hold` 이동만 허용할지, `move_to(pos)`(좌표 이동, 길찾기 포함)는 남길지. 권장: 처음엔 `move_to(pos)` 를 남기고 UI 조작만 raw 로 → 단계적으로 제거.
2. **월드 클릭**: 월드 물체를 화면 좌표로 클릭해 상호작용(`pointer_click` 이 월드 물체에 맞으면 상호작용)할지, `e` 키만 쓸지. 권장: 둘 다 (일반 PC 게임과 같게).
3. **semantic 관찰의 id**: raw 모드에서도 `screen.ui[].id` 를 보여 줄지. 권장: 보여 줌 (접근성 트리에도 이름은 있다). 숨기면 텍스트·좌표만으로 판단 — 더 어려운 시험.

## 끝나면

- 계약 `PLAY_PROTOCOL.md` v0.4 (0.x 규칙: 주.부 일치), `game_version` 올리기, `PLAY_MODE_REPORT.md` 에 C1~C6 결과
- semantic 모드 검사(`play_check.py`·`check-play`) 그대로 PASS, T1 밸런스 회귀 그대로
