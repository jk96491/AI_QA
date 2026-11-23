# 보스 전투 패턴 고도화 요청 (학습 플랫폼 → Unity)

- 작성: 학습 쪽, 2026-11-23 (사용자 요청: "보스 전투 패턴을 좀 더 그럴싸하게 — 프로젝타일도 떨어지고 장판 깔리고 등등")
- 대상: **숲의 늑대왕(`forest_wolf_king`)** — 플레이 모드 필드 보스이자 밸런스 시나리오. `default` 보스는 **지금 그대로** 둔다 (회귀 기준).
- 목적: 보기에 그럴듯한 보스전 + **BT 가중치가 실제로 의미 있는 전투** (피할지 때릴지의 판단이 결과를 가른다 → CMA-ES/IMPALA 학습 가치가 생긴다).

## 0. 지켜야 할 것 (AGENT_GUIDE·CLAUDE.md 규칙 그대로)

- **결정성**: 패턴 위치·타이밍의 모든 난수는 판의 `System.Random(seed)` 하나. 같은 seed·params·트리거 응답 → 같은 result.
- **속도**: 고정 dt 수동 루프, 5분 전투 1판 ≤ 100 ms. 동시에 살아 있는 투사체·장판 수에 상한(예: 각 16개).
- **프로토콜 v1.3 은 바꾸지 않는다**: `describe` 의 학습 대상(블록 가중치 `w_burst`·`w_dps`·`w_survival`), `state_features`·`totals` 이름·순서, `result` 필드 그대로. 새 정보가 프로토콜에 필요하면 고치지 말고 `PROTOCOL_CHANGE_REQUEST.md` 로.
- 보스 데이터를 바꾸면 `game_version`(→ 0.8.0)·보스 spec 버전 올리기. 학습 쪽은 다시 학습한다 (기존 0.7.x 학습 결과는 버전 경고와 함께 계속 쓸 수는 있음).
- 새 패턴 필드는 **기본값 0 = 꺼짐**. `default.json` 은 값을 안 넣어서 지금과 같은 결과여야 한다 (`check-game` 결정성·edge 통과 + 0.7.1 과 default 시나리오 결과 동일).

## 1. 전투 공간: 1차원 거리 → 2차원 아레나

지금 `CombatSim` 은 플레이어–보스 **거리 하나**만 있다. 떨어지는 투사체·장판은 "어디에" 가 있어야 하므로:

- 원형 아레나(반지름 `arena_radius`, 예 14m) 안의 2D 좌표 `player_pos`, `boss_pos`. 기존 `distance` = 두 점 사이 거리 (기존 cleave·leap·kite 규칙은 이 거리로 그대로 동작).
- 이동은 지금처럼 고정 dt 속도 이동. 아레나 밖으로 못 나감.
- 플레이 모드 필드 전투(BattleViewer)도 같은 좌표를 쓴다 — 결계 = 아레나 경계로 보이게.

## 2. 새 패턴 (늑대왕 데이터에만 켠다)

| # | 패턴 | 동작 | 피하는 법 | 데이터 예 |
|---|---|---|---|---|
| B1 | **낙석 (떨어지는 투사체)** | 하늘에서 바위 N개. 바닥에 **경고 원**(빨간 원이 채워짐) → `windup` 후 착지, 원 안이면 피해 + 짧은 경직. 일부는 **플레이어 현재 위치 조준**, 나머지는 seed 로 아레나 안 무작위 | 원 밖으로 이동 | `rockfall_count 5`, `rockfall_aimed 2`, `rockfall_radius 2.2`, `rockfall_windup 1.6`, `rockfall_damage 240`, `rockfall_cooldown 14`, `rockfall_phase_min 1` |
| B2 | **독 장판 (지속 지대)** | 플레이어 발밑에 독 웅덩이 생성 → `duration` 초 동안 남음, 안에 있으면 초당 피해. 여러 개 쌓여 **설 자리가 줄어든다** | 밖으로 나가 있기 (안에서 계속 때리면 손해) | `pool_radius 3.0`, `pool_duration 18`, `pool_dps 60`, `pool_cooldown 9`, `pool_max 4`, `pool_phase_min 0` |
| B3 | **부채꼴 탄막 (날아가는 투사체)** | 보스 앞으로 부채꼴 방향 K발 발사, 속도 v 로 직진. 발 사이에 틈이 있다 | 틈으로 비켜서기 / 멀리 있으면 피하기 쉬움 | `volley_count 7`, `volley_arc_deg 70`, `volley_speed 9`, `volley_damage 130`, `volley_cooldown 12`, `volley_phase_min 1` |
| B4 | **돌진 (직선 경고)** | 플레이어 쪽으로 **직선 경고 띠** → 돌진, 띠 안이면 큰 피해 + 넉백 | 옆으로 비켜서기 | `charge_width 2.5`, `charge_windup 1.3`, `charge_damage 380`, `charge_cooldown 15`, `charge_phase_min 2` |
| B5 | **하울링 (전 범위, 기존 광역기 대체)** | 짧은 캐스팅 후 아레나 전체 피해 — 피할 수 없음, **물약·생존 판단**으로 버틴다 | 없음 (체력 관리) | 기존 `aoe_*` 를 연출만 바꿔 유지 |
| B6 | **페이즈 조합** | 3페이즈(보스 체력 < 50%)부터 낙석 + 장판 동시, 4페이즈(< 25%)는 쿨다운 ×0.8 | — | `phase_cooldown_mult [1,1,1,0.8]` |
| (선택) B7 | 새끼 늑대 소환 | 4페이즈에 잡몹 2마리 — 타깃 선택이 BT 에 없으므로 **이번엔 하지 않아도 됨**. 할 거면 요청서 먼저 | — | — |

수치는 출발점이다. **기준: 손 튜닝 default(전사·stable 페르소나) 클리어율 40~70%** — 너무 쉬우면 학습할 게 없고, 너무 어려우면 학습 신호가 없다. `balance_qa evaluate -n 300` 으로 맞춘 값을 보고서에 남긴다.

## 3. BT 쪽: 피하기는 "생존 블록" 안에서

학습 대상은 블록 가중치뿐이라, 피하기를 **따로 학습시키지 않는다**. 대신 BT 가 위험을 보고 판단하게 한다:

- 시뮬레이터가 매 틱 **위험도 `danger`(0~1)** 를 계산: 지금 위치가 경고 원·장판·돌진 띠·탄 경로 안이면 그 위험의 (예상 피해 / 현재 체력)으로.
- **생존 블록의 필요도 N 에 `danger` 를 넣는다** (기존 체력 기반 항에 더함). 생존 블록이 이기면 → **가장 가까운 안전 지점으로 이동**(결정적: 후보 8방향 × 2거리 중 위험 0이고 보스와 거리 조건을 만족하는 가장 가까운 점, 동점이면 고정 순서).
- 딜 블록이 이기면 위험을 맞으면서 계속 때린다 → **`w_survival` 대 `w_dps` 의 균형이 결과를 바꾼다** (이게 학습 대상).
- 원거리 직업은 기존 `kite_distance` 와 같이 동작 (멀리서 쏘면 탄막은 쉽고 낙석은 그대로).
- 새 BT 파라미터가 필요하면 가중치가 아닌 값(예: `danger_threshold`)으로 정의서 `group: bt` 에 default 와 함께 — **학습되지 않으므로 손 튜닝 default 가 최종값**. 모든 직업에 같은 이름.
- `tests/game/test_need.py` 류의 기존 필요도 재현은 `danger = 0` 일 때 그대로여야 한다.

## 4. 기록·화면

- 전투 로그(뷰어용, 프로토콜 밖): `telegraph{kind, shape, pos, radius|width, t_land}`, `projectile_land{kind, pos, hit}`, `zone_spawn/zone_expire{pos, radius}`, `player_hit{source, damage}`, `dodge{from, to}`.
- **BattleViewer 연출** (창 모드):
  - 경고 원: 바닥에 빨간 원, `windup` 동안 안쪽이 차오름 → 착지 순간 바위 + 먼지·흔들림
  - 장판: 초록 독 웅덩이(맥동), 사라지기 2초 전 깜빡임
  - 탄막: 보스 입에서 날아가는 발광 투사체 + 궤적
  - 돌진: 바닥에 직선 경고 띠 → 보스가 띠를 따라 질주
  - 맞으면 피격 플래시·피해 숫자, 피하면 짧은 "회피" 표시
  - 아레나 경계(결계) 원
- 학습 결과 비교 화면(`run/run_watch.py`, 손 튜닝 vs CMA-ES vs IMPALA 3창)에서 **학습한 쪽이 더 잘 피하는 게 눈에 보이면** 성공.

## 5. 검증 · 보고

1. `check-game` 전 항목 PASS, edge PASS, 결정성(같은 seed 2회 동일), `default` 시나리오 결과 0.7.1 과 동일
2. 성능: 늑대왕 5분 판 평균 ms (≤ 100 ms)
3. 밸런스: 늑대왕 손 튜닝 클리어율(전사·마법사·궁수 × stable, n=300), 패턴별 피격 비율(로그 집계)
4. `python -m play_agent check-play --exe ... --loadout <새 학습 결과>` PASS (학습 쪽이 0.8.0 으로 다시 학습한 뒤 같이 확인)
5. 창 모드 **스크린샷 3장 이상** (낙석 경고 원 / 장판이 깔린 아레나 / 돌진 띠) + 가능하면 짧은 GIF
6. `game_version` 0.8.0, `README.md`·보고서(`BOSS_PATTERN_REPORT.md`)에 패턴 표·수치·측정값

학습 쪽은 받은 뒤: 0.8.0 으로 `run/run_measure_build.py`(기준선·CMA-ES·IMPALA) → `docs/STATUS.md` 3장 표, 새 로드아웃으로 플레이 모드 재플레이.
