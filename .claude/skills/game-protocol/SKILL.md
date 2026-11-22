---
name: game-protocol
description: 게임(Unity 빌드 또는 game_sim 대역)과 학습 플랫폼(balance_qa) 사이의 TCP JSON Lines 프로토콜을 구현·수정·검사·연결할 때 사용. "유니티 연동", "게임 서버 구현", "프로토콜 바꿔", "check-game 실패", "게임 연결 안 돼", "C# 서버" 같은 요청.
---

# 게임 ↔ 학습 플랫폼 프로토콜

계약 문서는 `docs/PROTOCOL.md` 하나다. 코드보다 문서가 우선이며, 구현이 문서와 다르면 구현을 고친다.

## 1. 구성 요소 위치

| 역할 | 파이썬 대역 | Unity (추후) |
|---|---|---|
| 서버·세션 | `game_sim/server/server.py`, `session.py` | `QaServer`, `QaSession` (PROTOCOL 부록 A) |
| 메시지 상수·코덱 | `game_sim/server/protocol.py` | C# 상수 |
| 클라이언트 | `balance_qa/game_api/client.py` | — (학습 쪽 공용) |
| 병렬 풀·실행기 | `balance_qa/game_api/pool.py`, `launcher.py` | — |
| 적합성 검사 | `balance_qa/game_api/conformance.py` | — |

두 쪽은 코드를 공유하지 않는다 (`tests/test_independence.py`). 상수가 양쪽에 중복된 것은 의도된 것.

## 2. Unity 구현을 도울 때

1. `docs/PROTOCOL.md` 4장 메시지와 6장 결정성 요구사항을 기준으로 설명한다.
   IMPALA 학습까지 하려면 v1.1 `trigger.totals`(4.4 규칙 9)와 `describe.triggers.totals` 가 필수다.
2. 동작 예시는 `game_sim/server/session.py` 를 C# 로 옮기는 방식으로 안내한다 (hello / describe / run_episode / trigger 대기).
3. 결정성 체크포인트: 판별 `System.Random(seed)`, 고정 dt 수동 루프, `Physics.Simulate`, 트리거 대기 중 시간 정지, Dictionary 순회 순서.
4. 빌드 후 반드시:
   ```bash
   python -m balance_qa check-game --game 127.0.0.1:<port>
   ```
   FAIL 항목 메시지를 PROTOCOL 해당 절과 연결해서 원인을 설명한다.
5. 정의서(`describe.classes[].params`)에 필수 파라미터가 있는지 확인 (PROTOCOL 4.2 끝). BT 구조가 달라 필수 이름이 다르면 `balance_qa/session.py: DEFAULT_POLICY_OUTPUTS` 와 페르소나 파라미터 이름을 맞춰야 함을 알린다.

## 3. 프로토콜을 바꿀 때 (순서 엄수)

1. `docs/PROTOCOL.md` 수정 + 버전 규칙(8장): 필드 추가 = 부 버전, 의미 변경·삭제 = 주 버전.
2. 게임 쪽: `game_sim/server/protocol.py`(PROTOCOL_VERSION), `session.py`.
3. 학습 쪽: `balance_qa/game_api/protocol.py`, `client.py`, 필요 시 `spec/game_info.py`.
4. `ConformanceChecker` 에 새 규칙 검사 추가.
5. `tests/game/test_server.py`(원시 소켓) 와 `tests/integration/test_protocol_e2e.py` 갱신.
6. `python -m unittest discover -s tests -t .` 전부 통과 + `python -m balance_qa check-game`.

## 4. 연결 문제 진단

| 증상 | 확인 |
|---|---|
| `connect` 실패 | 게임이 포트를 열었는지 (`python -m game_sim serve --port N` 로 대역 비교), 방화벽, `127.0.0.1` vs `localhost` |
| 응답이 섞임 (`X 를 기대했으나 Y`) | 클라이언트가 판 진행 중 다른 요청을 보냈는지, 게임이 한 연결에서 요청을 순차 처리하는지 |
| 트리거에서 멈춤 | 게임이 `\n` 으로 메시지를 끝내고 flush 하는지, `trigger_response` 의 episode_id·index 일치 |
| 결정성 FAIL | PROTOCOL 6장. 같은 seed 로 `record_events: true` 두 번 돌려 이벤트가 처음 갈라지는 시점 비교 |
| 학습 중 무효 판 `connection:` | 게임 크래시/타임아웃. `GameClient(timeout=...)`, 게임 로그 확인 |
| check-game `result.stalled` WARN | 게임이 v1.1 (멈춘 판을 invalid 로 보냄). 학습은 호환 변환으로 정상이지만 v1.2 로 올리도록 요청 (`unity_game/PROTOCOL_UPDATE_1.2.md`) |
| `impala` 실행 시 "trigger.totals 를 보내지 않음" | 게임이 v1.0 수준. `describe.triggers.totals` 와 `trigger.totals` 구현 (PROTOCOL 4.4) |
| 풀 생성 시 "버전/데이터가 서로 다름" | 인스턴스들이 같은 빌드·데이터인지 |

## 5. 디버깅 도구

- 메시지 엿보기: `client.tap = lambda d, m: print(d, m)` (GameClient)
- 원시 소켓 예시: `tests/game/test_server.py` 의 `RawClient`
- 대역 단독 실행: `python -m game_sim serve --port 7777` 후 다른 터미널에서 `check-game --game 127.0.0.1:7777`
