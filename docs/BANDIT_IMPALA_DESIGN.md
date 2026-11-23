# 설계: IMPALA 를 컨텍스트 밴딧으로 — "전투 시작에 한 번, 상황을 보고 가중치를 고른다"

- 작성 2026-11-23. 사용자 결정: **결정은 판 시작에 한 번 (one-step bandit)**. 학습 대상은 그대로 **블록 가중치 w 뿐**.
- **구현 완료 2026-11-23** (10장): 프로토콜 v1.4 `initial_state` (SDK 0.2.0, game_sim), `balance_qa bandit`, 실험 E8, play_agent `BanditPolicy`. Unity 반영 요청 `unity_game/PROTOCOL_UPDATE_1.4.md`.
- 관련: `PROTOCOL.md` (v1.4), `PLAY_PROTOCOL.md` 4.7(전투 물약 = 인벤토리), `DISTRIBUTED.md`(액터·학습기), `unity_game/BOSS_PATTERN_REQUEST.md`·`unity_game/PLAYER_SKILL_BT_REQUEST.md`(전투 복잡도).

## 1. 왜 바꾸나

지금 IMPALA 는 트리거(시작 + 보스 체력 75·50·25%) 4번에 가중치를 다시 고른다. 그런데
- 판단 기회가 적고 상태가 거칠며 전투 흐름이 판마다 비슷해서, **판 전체 고정 가중치(CMA-ES)가 이미 거의 최적**이다 (warrior/stable: CMA 와 IMPALA 가 비슷, IMPALA 우위 불명확 — STATUS 3장).
- 가중치 3개 공간은 CMA-ES 가 몇백 판이면 푼다.

RL(IMPALA)이 이유를 가지려면 **"같은 정책 하나가 서로 다른 상황마다 다른 답을 내야 하는" 문제**여야 한다. 판 중간 결정을 늘리는 대신(사용자 결정으로 하지 않음), **판 시작 상황(컨텍스트)을 다양하게** 만든다.

## 2. 문제 정의

```
컨텍스트 c  ──정책 π(w | c)──►  가중치 w (블록 수만큼, 0~range)  ──판 1회──►  보상 R(c, w)  (기존 R 식 그대로)
```

| 항목 | 내용 |
|---|---|
| 결정 | 판마다 1번 = 트리거 index 0 (판 시작). 보스 체력 트리거는 **끈다** (`run_episode.triggers` 비움 + 시작 트리거만, 5장) |
| 행동 | 블록 가중치 w — `describe.classes[].blocks` (지금 3개, 스킬·BT 요청 후 5개). Beta 분포 (지금 IMPALA 와 같음) |
| 보상 | `R = −분 − λ_death·사망 − λ_consumable·소모품 − F_fail·[실패]` (페르소나 λ). 판 끝에 한 번 |
| 가치 V(c) | 기준선(분산 감소)만. γ 무의미 (길이 1) |
| 오프폴리시 | 액터는 조금 옛 정책으로 판을 돈다 → **V-trace 중요도 보정(ρ̄=c̄=1)** 이 여기서도 쓸모 있다 (길이 1 이면 ρ 클리핑된 정책 경사) |

### 컨텍스트 c (정책 입력)

| 묶음 | 특징 | 출처 | 비고 |
|---|---|---|---|
| 조합 | 직업·보스·시나리오 원-핫, 페르소나 λ(연속) | 학습 쪽이 판을 만들 때 앎 (describe 이름 목록으로 원-핫) | 조합 수가 늘수록 CMA-ES 대비 이득 |
| 시작 상태 | `hp_ratio`, `resource_ratio`, `potions`(0~cap) | **새 `run_episode.initial_state` (v1.4, 4장)** — 트리거 0 의 `state` 에도 그대로 보임 | 플레이 모드 `field_state`·`carried` 와 같은 값 |
| 패치 | 시나리오가 선언한 수치(보스 공격력 배율 등) | describe `scenarios[]` (있으면) | 처음 보는 패치에 일반화 = QA 목적 |

트리거 0 의 `state`(hp_ratio, potions_ratio …)는 이미 정책 입력이다. 조합 원-핫·페르소나 λ 만 학습 쪽이 덧붙인다.

## 3. IMPALA 가 이기는 곳 / 지는 곳 (솔직하게)

- 이긴다: **조합 × 시작 상태가 많을 때.** CMA-ES 는 (조합 × 시작 상태 구간)마다 따로 돌려야 하고 연속 상태는 구간으로 쪼개야 한다. 정책 하나는 전부를 같이 배우고 **안 본 상태에서도 바로 답한다** (플레이 모드: 물약 1개 들고 들어간 전투).
- 진다/비슷: 조합이 몇 개뿐이고 시작 상태가 늘 full 이면 조합별 CMA-ES 가 같거나 낫다. → 그래서 **시작 상태 다양화(initial_state)가 이 설계의 핵심**이다.
- 판정은 실험으로 (6장). 이득이 안 나오면 "CMA-ES 로 충분" 이 결론이고 그것도 유효한 결과다.

## 4. 프로토콜 v1.4 제안 — `run_episode.initial_state` (부 버전, 호환)

```json
{"type":"run_episode","episode_id":"e1","class":"warrior","scenario":"forest_wolf_king","seed":7,
 "params":{"w_dps":0.8},"triggers":{"start_only":true},
 "initial_state":{"hp_ratio":0.7,"resource_ratio":0.0,"potions":1}}
```
- `describe.initial_state = {"hp_ratio":[0.05,1.0], "resource_ratio":[0,1], "potions":[0,"cap"]}` — 게임이 받는 키·범위 선언. 없으면 학습 쪽은 보내지 않는다 (1.3 이하 게임 호환).
- 생략한 키 = 지금과 같은 시작값(full). 범위 밖 → `param_out_of_range`, 모르는 키 → `unknown_param`.
- 결정성 그대로: 같은 seed·params·initial_state·응답 → 같은 result. `initial_state` 생략 판은 1.3 과 **완전히 같은 result**.
- 트리거 "시작만": 지금도 트리거 index 0 = 판 시작이다. 경계 목록이 비면 트리거가 아예 없는 1.3 규칙과 겹치므로, **시작 트리거만 받는 방법을 명시**해야 한다 — 안: `triggers: {"start_only": true}` 또는 `describe.triggers` 에 `start` 타입. SDK 원본에서 정한다.
- 플레이 모드와의 연결: 필드 전투 `combat_started.potions.carried`·`field_state` = 이 `initial_state` 와 같은 의미. 학습 = 실전 동일성(T5)을 `carried < cap` 전투에도 확장할 수 있게 된다 (지금은 `carried == cap` 만 비교).

**변경 순서 (CLAUDE.md 규칙)**: `docs/PROTOCOL.md` v1.4 → **SDK 원본 레포 `btqa_sdk`** (Python `btqa_game` + Unity `com.btqa.game` + conformance, CHANGELOG) → `run/run_sync_sdk.py` → `game_sim` (참조 구현) → `balance_qa/game_api` → `ConformanceChecker` → Unity 요청서(`unity_game/` 에 기록). Unity 는 스킬·BT 요청이 끝난 뒤.

## 5. 학습 쪽 구현 (balance_qa)

| 부분 | 변경 |
|---|---|
| `rl/` IMPALA | 판 길이 1 모드 `--decisions start` (기본). 지금의 구간 모드는 `--decisions triggers` 로 남김. 구간 보상(totals 차분) 불필요 → totals 없는 게임도 허용 |
| 컨텍스트 | `ContextEncoder`: 조합 원-핫(describe 이름 순서 고정) + 페르소나 λ + 트리거 0 state. 정책 MLP 입력 = 이것 |
| 학습 판 분포 | `ContextSampler` (확장 지점, 추상 클래스): 조합 균등 × 시작 상태 혼합 — full 40% / 균등(hp 0.3~1, potions 0~cap) 40% / **플레이 기록 `field_state` 분포** 20% (`reports/relay-*`, `play-*` 의 `combat_started`) |
| 시드 | 학습 `TRAIN_SEEDS`, 평가 `EVAL_SEEDS` 그대로 (섞지 않음) |
| 정책 파일 | `policy.json` 에 컨텍스트 정의(원-핫 순서·특징 목록) 기록 → `play_agent` CombatResponder 가 필드 전투 트리거 0 에서 같은 인코딩으로 답함 (numpy, 지금 구조) |
| 하이퍼파라미터 | 시작점: lr 3e-3, batch 32(분산 큼), hidden (64,64), entropy 3e-3. 판 길이 1 이라 판 수 = 갱신 수 |

`balance_qa` 는 여전히 `game_sim`·`btqa_game` 을 import 하지 않는다. 판 시작 상태는 프로토콜로만 보낸다.

## 6. 평가 — 실험 E8 "컨텍스트 밴딧"

| 방법 | 설명 | 판 수 |
|---|---|---|
| 손 튜닝 | 정의서 default | 0 |
| CMA-전역 | 모든 컨텍스트에 가중치 하나 | B |
| **CMA-셀별 (기준 상한)** | (조합 × 물약 0/1/2/3 × hp 구간 3)마다 따로 — 사실상 최적치 | 셀 수 × B |
| **IMPALA 밴딧** | 정책 하나 | B 와 같은 총 판 수, 그리고 셀 수 × B |

- 지표: 셀별 평가 보상(EVAL_SEEDS, n=200/셀, 95% CI), 클리어율, **CMA-셀별 대비 격차**, 총 판 수 대비 성능 곡선.
- 일반화: 학습에서 뺀 셀(예: potions=1·hp<0.5, 처음 보는 패치 시나리오)에서 IMPALA vs CMA-전역.
- 성공 기준(초안): IMPALA 가 같은 총 판 수에서 CMA-전역을 유의하게 이기고, CMA-셀별의 90% 이상을 1/셀수 판 수로 달성. 아니면 "CMA 로 충분" 결론을 리포트.
- 결론 전 `/bt-sim-balance-review` 점검.

## 7. 전투 복잡도와의 관계

밴딧이 의미 있으려면 **시작 상황에 따라 최적 w 가 달라야** 한다. 그래서 같이 진행 중인 게임 쪽 작업이 중요하다:
- 보스 패턴(`BOSS_PATTERN_REQUEST.md`, Unity 작업 중): 낙석·장판·돌진 → 체력·물약이 적을수록 회피·생존 쪽이 유리 → 컨텍스트별 w 차이가 커진다.
- 스킬·BT(`PLAYER_SKILL_BT_REQUEST.md`): 블록 3 → 5 (w 5개, 실효 4). 공간이 커지면 셀별 CMA 비용이 더 커지고 정책 공유 이득이 커진다.

## 8. 순서

1. (Unity, 진행 중) 보스 패턴 → (Unity) 스킬·BT 확장 — 같은 0.8.x
2. (학습 쪽) 0.8.x 측정: `run/run_measure_build.py` (기준선·CMA·기존 IMPALA)
3. (학습 쪽) PROTOCOL v1.4 + SDK 원본 `initial_state`·시작 트리거 → game_sim → balance_qa → 적합성 검사
4. (Unity) v1.4 반영 요청서
5. (학습 쪽) IMPALA 밴딧 모드 + ContextEncoder/Sampler + E8
6. (플레이 모드) CombatResponder 가 필드 `field_state` 로 트리거 0 에 답함 → T5 를 `carried < cap` 까지 확장

## 9. 결정 (구현하며 정함, 2026-11-23)

- **시작 트리거는 만들지 않는다.** 밴딧에서는 학습 쪽이 컨텍스트(조합·시작 상태)를 판 전에 이미 안다 → 가중치를 `run_episode.params` 로 바로 보낸다. 프로토콜 변경은 `initial_state` 하나뿐 (4장의 `start_only` 안은 버림).
  플레이 모드는 시작 상태(가져간 물약)를 응답기가 판 전에 모르므로 **트리거 index 0** 을 쓴다 (로드아웃 경계 `[0.5]`, index 0 에만 답하고 이후 `{}`).
- **`initial_state` 키 = `triggers.state_features` 중 하나 (0~1 비율)** — 직업마다 물약 수가 달라도 같은 뜻, 정책 입력과 같은 값. `potions_ratio` 는 게임이 개수로 반올림.
- **자원(`resource_ratio`)은 선언하지 않는다**: 직업마다 시작 자원이 달라(전사 0, 마법사 가득) default 하나로 "생략 = 1.3 과 같은 판" 을 지킬 수 없다. 체력·물약만.
- 1.3 게임은 모르는 요청 필드를 무시하므로, 학습 쪽은 `describe.initial_state` 선언이 없으면 **보내지 않는다** (`GameDescription.check_initial_state` 가 막음). SDK 1.4 게임은 미선언 요청을 `unknown_param` 으로 거부.
- 샘플러 기본: 조합 균등 × (p_full = 0.4 로 가득 / 나머지는 키별 범위 균등 또는 `--levels` 단계). 플레이 기록(`field_state`) 분포는 기록이 쌓이면 `ContextSampler` 하위 클래스로 추가 (아직 없음).
- 페르소나 λ 는 아직 컨텍스트에 넣지 않았다 — 한 학습 = 페르소나 하나 (보상 함수가 하나). 필요해지면 `ContextEncoder` 확장.
- 트리거 구간 모드 IMPALA(`impala` 명령)는 그대로 남긴다 (비교용, E7).

## 10. 구현 위치

| 부분 | 파일 |
|---|---|
| 계약 v1.4 (`initial_state`) | `docs/PROTOCOL.md` 4.3.1 — 원본 `btqa_sdk` 0.2.0 (`InitialStateDecl`, 검증·적합성 4항목) → `run/run_sync_sdk.py` |
| 참조 구현 | `game_sim/server/session.py` (`INITIAL_STATE` hp_ratio·potions_ratio), `game_sim/sim/engine.py` |
| 학습 쪽 전송 | `balance_qa/spec/game_info.py` (`InitialStateInfo`, `check_initial_state`), `game_api/client.py` (`EpisodeRequest.initial_state`), `runner/episode_runner.py`, `optim/trainer.py` (`initial_state_fn`), `game_api/conformance.py` |
| 밴딧 | `balance_qa/rl/bandit.py` (`ContextCell`·`ContextEncoder`·`ContextSampler`(확장 지점)/`MixedContextSampler`·`BanditSetup`·`BanditParamSource`), `rl/actor.py` (`ActorCore._run_bandit`, 길이 1 궤적), `rl/impala.py` (`bandit=`), `rl/remote_actor.py` (호환 검사) |
| 세션·CLI | `QASession.bandit_setup / train_bandit / evaluate_cells`, `optimize(initial_state=…, initial_state_fn=…)`, `python -m balance_qa bandit`, `run/run_bandit.py` (PyCharm `06b`) |
| 실험 | `experiments/e8_bandit.py` (손튜닝 / CMA-가득 / CMA-전역 / CMA-칸별 / IMPALA 밴딧, `--holdout`) |
| 플레이 모드 | `play_agent/responder.py` (`BetaMlp`, `BanditPolicy`, `BanditBinding`), `play_agent/loadout.py` (밴딧 파일 → 조합마다 항목) |
| 테스트 | `tests/integration/test_bandit.py` (인코더·샘플러, game_sim initial_state, 학습·저장·numpy=torch) |

```bash
python -m balance_qa --workers 8 bandit --combos warrior:forest_wolf_king mage:forest_wolf_king --persona stable --budget 8000 --levels potions_ratio=0,0.333,0.667,1
python -m experiments.e8_bandit --workers 8 --game-cmd "unity_game/Build/QaArena.exe -batchmode -nographics -qaPort {port}" --combos warrior:forest_wolf_king
```
