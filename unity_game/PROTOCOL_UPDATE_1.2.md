# 프로토콜 v1.2 반영 요청 (학습 플랫폼 → Unity 게임)

> **반영됨 (2026-11-22, QaArena 0.3.0)**
> - 2장: `result.stalled` / `stall_reason` 추가, 멈춘 판은 `cleared=false, invalid=false`, `PROTOCOL_VERSION = "1.2"`, `result_fields` 갱신.
> - 4장: 생존 블록 최대 유지 시간 — 모든 직업 `bt_rules: {survival_max_hold: 12, survival_lockout: 6}`
>   (생존 블록을 12초 넘게 계속 유지하면 6초 동안 생존 후보 제외 → 딜·접근으로 복귀). 학습 대상 아님, describe 비공개.
> - 함께 반영: 비전투 회복 `hp_regen_ratio 0.008`, `regen_delay 7` (모든 직업, spec_version 0.2).
> - 측정 (stable, 손 튜닝): 멈춘 판 warrior 100% → 0%. CMA-ES 1,200판 후 warrior 클리어 22→89%, mage 0→92%, 멈춘 판 0%.

- 작성: 학습 플랫폼 쪽, 2026-11-22
- 대상 빌드: `QaArena 0.2.0` (프로토콜 1.1)
- 기준 문서: `../docs/PROTOCOL.md` v1.2 (4.5 결과 필드)

## 1. 왜 바꾸는가

전사(stable) IMPALA 학습에서 판의 2~4% 가 `invalid: true, invalid_reason: "stalled: 90s 동안 보스 피해 없음"` 으로 왔다.
v1.1 규칙상 `invalid` 판은 학습·평가에서 **빠지기만** 하므로, "질 것 같으면 멈추는" 정책이 벌을 피하는 허점이 생긴다
(실제로 멈춘 4판을 뺀 클리어율 90% 가, 포함하면 81% 였다).

멈춤은 환경 오류가 아니라 **BT·정책의 실패**다. v1.2 부터 멈춘 판은 `stalled` 로 보내고, 학습 쪽은 시간 초과와 같은 벌점으로 처리한다.

> 학습 쪽은 이미 호환 처리를 넣었다: 사유가 `"stalled"` 로 시작하는 `invalid` 판은 멈춘 판으로 해석한다.
> 그래서 **지금 빌드로도 학습은 올바르게 돈다.** 아래는 명시적인 필드로 바꾸는 작업이다.

## 2. 해야 할 것 (필수)

1. `episode_result.result` 에 필드 추가
   - `stalled: bool` — 멈춤 감지(현재 90초 무피해)로 판을 끝냈으면 `true`
   - `stall_reason: string | null` — 예: `"90s 동안 보스 피해 없음"`
2. 멈춘 판은 `cleared: false`, `clear_time: null`, **`invalid: false`**, `invalid_reason: null`
   - `invalid` 는 게임 내부 예외 등 **결과를 믿을 수 없는 경우에만** 쓴다.
   - `elapsed`, `boss_hp_remaining`, `deaths`, `consumables_used` 는 멈춘 시점 값 그대로.
3. `PROTOCOL_VERSION` = `"1.2"` (hello_ok, description)
4. `describe.result_fields` 에 `"stalled"`, `"stall_reason"` 추가
5. `game.json` 의 `game_version` 올리기 (예: `0.2.1`)

참조 구현: `../game_sim/sim/engine.py` (멈춤 감지 → `stall_reason`), `../game_sim/core/types.py` (`EpisodeResult.stalled`).

## 3. 확인 (상위 `AI_QA` 폴더에서)

```bash
venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777 check-game
```
- 기존 14개 PASS 유지 + **`result.stalled 필드 (v1.2)` 항목이 WARN → PASS**
- `venv\Scripts\python.exe run/run_full_cycle.py` (GAME = 빌드 주소) 6단계 OK

## 4. 참고 — 멈춤의 원인 (BT 설계 검토 권장, 선택)

학습된 정책(전사, stable, IMPALA 8,000판)에서 평가 300판 중 8판이 멈췄다. 멈춘 판 2개를 기록으로 보면:

| seed | 멈춘 시점 | 보스 남은 체력 | 블록 점유 | 멈추기 전 90초 |
|---|---|---|---|---|
| 1000015 | 282s | 40% | 생존 45%, 딜 47% | 플레이어 피격 10회, 보스 피해 0, 물약 3개 모두 사용 |
| 1000092 | 591s | 8% | 생존 62%, 딜 30% | 플레이어 피격 11회, 보스 피해 0, 물약 3개 모두 사용 |

추정 경로: 페르소나 θ = 0.8 → 체력 80% 미만이면 생존 블록이 이김 → 후퇴 → 거리 > 5.5m 이면 보스 **도약**(0.2.0 신규)·광역기로 계속 피격
→ "피격 후 4초 무피해" 회복 조건이 안 채워짐 → 물약 소진 후 체력이 80% 위로 못 올라옴 → 생존 블록에서 못 빠져나옴 → 90초 무피해로 멈춤.

파라미터(w_survival 등)를 바꿔서는 잘 안 빠져나오는 구조라, 아래 중 하나를 검토해 주면 좋다 (게임 설계 판단):
- 생존 블록에 최대 유지 시간 (예: N초 후에는 회복 여부와 무관하게 딜 블록으로 복귀)
- 생존 블록 안에서 후퇴가 의미 없을 때(보스가 따라붙음) 반격·방어기 우선
- 회복 조건(피격 후 무피해 시간) 또는 보스 도약 조건 조정

BT 를 바꾸면 손 튜닝 기준선이 달라지므로 `game_version` 과 해당 직업 `spec_version` 을 올린다.
