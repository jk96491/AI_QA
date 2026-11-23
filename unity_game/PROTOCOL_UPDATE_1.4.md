# 밸런스 프로토콜 1.4 반영 요청 — `run_episode.initial_state` (학습 플랫폼 → Unity)

- 작성: 학습 쪽, 2026-11-23. 사용자 요청: "밴딧 설계대로 구현" (`../docs/BANDIT_IMPALA_DESIGN.md`).
- 계약: `../docs/PROTOCOL.md` **v1.4** (4.3.1). 1.x 부 버전 — 1.3 클라이언트·게임과 호환.
- **SDK 는 이미 갱신했다**: 원본 `btqa_sdk` 0.2.0 → `run/run_sync_sdk.py` 로 `Packages/com.btqa.game` 사본 교체 완료 (직접 고치지 않는다).
  SDK 가 하는 것: `describe.initial_state` 직렬화, 요청 검증(모르는 키 `unknown_param` / 범위 밖 `param_out_of_range` / 숫자 아님 `bad_request`), 선언 안 했으면 요청 거부.
- 플레이 모드(play 0.3/0.4)는 건드리지 않는다. 밸런스 모드(`-qaPlay` 없음)만.

## 할 일 (QaArenaHost 두 곳)

1. **선언** — `QaArenaHost.Declare()` 끝에:
   ```csharp
   d.InitialState.Add(new InitialStateDecl("hp_ratio", 0.05, 1.0, 1.0, "판 시작 체력 / 최대 체력"));
   d.InitialState.Add(new InitialStateDecl("potions_ratio", 0.0, 1.0, 1.0, "판 시작 물약 = round(비율 × 직업 물약 수), 0.5 올림"));
   ```
   - 이름은 `triggers.state_features` 에 있는 것만 (SDK `Validate()` 가 검사). `resource_ratio` 는 **넣지 않는다** — 직업마다 시작 자원이 달라(전사 0, 마법사 가득) default 하나로 "생략 = 1.3 과 같은 판" 을 지킬 수 없다 (참조 구현 game_sim 도 같은 이유로 뺐다).
2. **적용** — `RunEpisode()` 에서 `new CombatSim(...)` 직후, `sim.Run()` 전에:
   ```csharp
   if (req.InitialState != null)   // null = 요청 없음 → 지금과 같은 판 (바이트 단위 동일해야 함)
   {
       sim.SetStartHpRatio(req.InitialState["hp_ratio"]);                          // 새로 추가: Begin 전에만, Hp = MaxHp × ratio
       int cap = _repo.Class(req.Class.Name).Stats.Potions;
       sim.SetStartPotions((int)Math.Floor(req.InitialState["potions_ratio"] * cap + 0.5));   // 이미 있음 (플레이 모드용)
   }
   ```
   - `CombatSim.SetStartHpRatio(double)` 는 `SetStartPotions` 와 같은 규칙으로 추가 (Begin 전에만, 0 < ratio ≤ 1). 시작 체력이 낮아도 비전투 회복 규칙(피격 후 지연 회복)은 그대로.
   - 트리거 index 0 의 `state.hp_ratio`·`state.potions_ratio` 가 이 값이어야 한다 (`potions_ratio` = 반올림한 개수 / cap).
   - 결정성: 같은 seed·params·initial_state → 같은 result.

## 검증

- `python -m btqa_game check --game 127.0.0.1:7777` — v1.4 항목 4개 PASS ("initial_state = default → 생략과 같은 결과", "결정성", "트리거 0 state 반영", "오류 코드")
- `venv\Scripts\python.exe -m balance_qa check-game --game 127.0.0.1:7777` — initial_state 2항목 PASS
- **T1 회귀**: `initial_state` 를 보내지 않는 판은 0.8.2 와 결과 동일 (`QaTools~/t1_baseline_0.8.1.json` 21/21)
- `game_version` 0.8.3 (데이터 변경 없음 — 학습 쪽 재학습 불필요), `README.md`·보고서에 한 줄
- 플레이 모드 `play_check.py` 그대로 PASS (play 0.3 hello 유지)

## 학습 쪽 (참고, 이미 구현)

- `balance_qa`: `EpisodeRequest.initial_state`, `GameDescription.initial_state` (선언 안 한 게임에는 보내지 않음), `optimize(initial_state=… | initial_state_fn=…)`, **`bandit`** 명령 (IMPALA 컨텍스트 밴딧), 실험 **E8** (`experiments/e8_bandit.py`)
- `play_agent`: 밴딧 `policy.json` → 필드 전투 트리거 index 0 의 state(`potions_ratio = carried / cap`)로 가중치를 골라 답함 (`BanditPolicy`), 로드아웃 트리거 경계 `[0.5]`
- 반영되면 학습 쪽이 E8 을 늑대왕(`warrior:forest_wolf_king` 등)으로 돌린다.
