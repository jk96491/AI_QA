# 플레이 프로토콜 v0.2 후속 요청 (학습 플랫폼 → Unity)

- 작성: 학습 쪽, 2026-11-23
- 근거: `PLAY_MODE_REPORT.md` 2장을 받아 `../docs/PLAY_PROTOCOL.md` 를 **v0.2** 로 확정했다. 보고서 2장의 결정은 모두 그대로 받아들였다.
- 아래는 v0.2 문서와 0.6.2 가 다른 곳 (문서에 **[0.6.2 미반영]** 표시). 작은 변경이다. 밸런스 모드(T1)는 건드리지 않는다.

| # | 항목 | 지금 (0.6.2) | 요청 | 검증 |
|---|---|---|---|---|
| F1 | 프로토콜 버전 | hello 는 `"0.1"` 만 받음 | `PP.ProtocolVersion = "0.2"` (0.x 주.부 일치 규칙은 그대로) | hello 0.2 → ok, 0.1 → `protocol_version` |
| F2 | 오류 코드 | 로드아웃 `boss` ≠ 시나리오 보스 → `unknown_boss` | **`boss_mismatch`** 로 이름 변경 (보스가 없는 게 아니라 시나리오와 다름) | `play_check.py` 422행 기대값도 변경 |
| F3 | 보스 결계 | 없음 (`CombatSim` 이 항상 full 로 시작 — 결과는 같음) | 요청서 `PLAY_MODE_REQUEST.md` 3.6 step 3: 적 어그로 반경 = **보스 결계**. 진입 시 회복 연출·안내 문구, 관찰 `events` 에 `barrier_restore`, 그리고 **`combat_started.field_state = {hp_ratio, resource_ratio, potions, deaths_so_far}`** (회복 직전 필드 값) | 지금은 필드 피해원이 없으니 `hp_ratio:1.0` 이어도 된다. 필드 체력을 줄일 수 있게 되면(F4 이후) 깎인 값이 찍혀야 함 |
| F4 | (선택, 나중) 필드 피해원 | 없음 → `use_item` 물약은 항상 `invalid_state` | 숲에 작은 피해(가시덤불 구역 등) — 물약 사용·`field_state` 분포를 검증할 수 있게 | 체력 깎인 뒤 `use_item` → done |

## 결정 대기 (사용자) — 잘못된 `trigger_response`

0.6.2: error 를 보내고 같은 trigger 를 계속 기다림. 학습 쪽 권장은 **지금 그대로 유지**다. 중단으로 바꾸면 "클라이언트 버그"가 "전투 패배·부활"이라는 게임 결과로 둔갑해 로그를 오염시킨다. `play_agent` 는 전투 중 error 를 받으면 세션을 끝낸다.
사용자가 중단을 고르면 이 표에 F5 로 추가한다. **그때까지 이 항목은 바꾸지 않는다.**

## 끝나면

- `game_version` 올리기 (0.6.3), `PLAY_MODE_REPORT.md` 에 F1~F3 결과 한 줄씩
- `play_check.py` (또는 학습 쪽 `python -m play_agent check-play`) 전부 PASS, T1 밸런스 회귀 그대로
