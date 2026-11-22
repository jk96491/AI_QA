---
name: bt-sim-extend
description: 게임 대역(game_sim)에 직업·보스·패치 시나리오·BT 블록·필요도 식을, 학습 플랫폼(balance_qa)에 페르소나·최적화 알고리즘을 추가하거나 바꿀 때 사용. "새 직업 추가", "보스 패턴 추가", "페르소나 만들어", "블록 추가", "알고리즘 바꿔" 같은 요청.
---

# game_sim / balance_qa 확장

전체 구조는 `docs/ARCHITECTURE.md` 5장(확장 지점)을 먼저 읽는다. 공통 규칙:

- Python 3.8 문법, numpy·PyTorch 외 의존성 추가 금지, 모듈 맨 위 `from __future__ import annotations`.
- **어느 쪽인지 먼저 정한다**: 게임 내용(직업·스킬·보스·BT) = `game_sim/` (추후 Unity 로 옮겨갈 것), 학습·평가 = `balance_qa/`. 서로 import 금지.
- 학습 코드(`balance_qa/optim`, `policy`)는 torch CPU, 장치·dtype 은 `balance_qa/backend.py`. 게임 쪽에는 torch 금지.
- 게임 데이터를 바꿔도 학습 쪽은 `describe` 로 자동 반영된다. 학습 쪽에 게임 수치를 하드코딩하지 않는다.
- 객체지향: 추상 클래스(`NeedFunction`, `Block`, `ParamSource`, `CandidateDecoder`, `Optimizer`)를 상속하고 패키지 `__init__.py` 에 export.
- 난수는 `CombatSim.rng` 만 사용 (시드 결정론).
- 작업 후 반드시 `python -m unittest discover -s tests -t .`, `python -m game_sim validate`, `python -m balance_qa check-game`.

## A. 직업 추가 (코드 수정 없음)

1. `game_sim/data/classes/<name>.json` 을 기존 직업을 복사해 작성.
   - `stats`: max_hp, armor[0,1), max_resource, start_resource, resource_regen, move_speed, potions, potion_heal_ratio, potion_cooldown, crit_chance (선택: hp_regen_ratio, regen_delay)
   - `skills`: `role` 은 basic / dps / burst / defense / gap_close. basic 최소 1개. 효과 필드: shield, evade, effect_duration, retreat, gap_close, resource_gain, cast_time, range(0 = 자기 대상)
   - `params`: 필수 `survival_hp_threshold, dps_hp_floor`(`"group": "persona"`) + `w_burst, w_dps, w_survival, potion_hp, resource_reserve, min_commit`, 원거리(`"ranged": true`)는 `kite_distance`. 근접 돌진기가 있으면 `charge_distance`.
   - 각 파라미터: `range`(기획 의도 범위), `default`(= 손 튜닝 값), `unit`, `description`, 선택 `group`(bt|persona), `optimize`.
2. `python -m game_sim validate` 통과 확인 (`SpecError` 면 메시지대로 수정), `python -m balance_qa list` 에 나오는지 확인.
3. 기본값으로 클리어되는지: `python -m balance_qa --workers 4 evaluate --cls <name> --persona stable -n 50`
   - 클리어율이 너무 낮거나(<0.8) 시간이 다른 직업과 2배 이상 차이 나면 수치를 조정.
4. `experiments/common.py` 의 `CLASSES` 에 추가할지 사용자에게 확인.

## B. 페르소나 / 시나리오 (코드 수정 없음)

- 페르소나 (학습 쪽): `qa_specs/personas.json` 에 `id, name, survival_hp_threshold(θ), dps_hp_floor(φ), lambda_death, lambda_consumable`.
  - 원칙: 페르소나는 N 설정값과 λ 만 정의하고 w 는 정하지 않는다 (w 는 최적화 출력).
- 시나리오 (게임 쪽): `game_sim/data/scenarios.json` 에 `scale`(배율) 또는 `set`(값) 으로 보스 필드 변경.

## C. 보스 패턴 추가 (코드 수정)

1. `game_sim/spec/boss_spec.py` `BossSpec` 에 필드 추가 (기본값을 주면 기존 JSON 호환).
2. `game_sim/sim/boss.py` `Boss.update` 에서 `BossAttack` 을 생성. 플레이어 대응이 필요하면 경고 상태를 `Boss` 에 두고 `Observation` 에 노출.
3. 대응 행동이 필요하면 `game_sim/core/types.py` `ActionKind` + `game_sim/sim/engine.py` `_apply` 에 추가.
4. 트리거 상태로 학습 쪽에 알려야 하면 `TRIGGER_STATE_FEATURES` + `CombatSim.trigger_state` (0~1 정규화). 정책 입력 차원은 describe 로 자동 반영.

## D. BT 블록 / 필요도 식 추가 (코드 수정)

1. `game_sim/bt/need.py` 에 `NeedFunction` 상속 클래스. `value()` 가 `None` 이면 후보 제외, 0 이하면 '필요 없음'.
   순수 계산은 `@staticmethod compute(...)` 로 분리해 단위 테스트 가능하게.
2. `game_sim/bt/blocks.py` 에 `Block` 상속, `build()` 에서 `Selector/Sequence_/Condition/Act` 트리 반환. 블록 안 상수는 `bb.p("<param>")` 로 노출.
3. `game_sim/bt/agent.py` `BTAgent._build` 에 `UtilityOption(name, node, need, "w_<name>")` 추가.
4. 모든 직업 정의서에 `w_<name>` 파라미터 추가하고 `game_sim/spec/loader.py: REQUIRED_CLASS_PARAMS` 에 등록. 트리거 정책이 바꿔야 하면 `balance_qa/session.py: DEFAULT_POLICY_OUTPUTS` 에도 추가.
5. `tests/game/test_need.py` 에 식 테스트, `tests/game/test_sim.py` 에 선택 테스트 추가.
6. 기존 문서 7장 재현 테스트가 계속 통과하는지 확인 (식을 바꾸면 안 됨).

## E. 최적화 알고리즘 추가

`balance_qa/optim/base.py` `Optimizer` 상속: `popsize`, `ask()` → torch 텐서 (popsize, dim) float64 CPU, `_tell(xs, losses)`(손실 최소화, 둘 다 텐서), `recommendation()` → 텐서.
난수는 `self.randn(...)` 또는 `self.gen`(torch.Generator) 만 사용.
RL 은 IMPALA 로 한다 (사용자 결정, REINFORCE/PPO 추가 금지). IMPALA 를 바꿀 때는 `balance_qa/rl`:
손실·V-trace 설정은 `LearnerConfig`/`ImpalaLearner.update`, 관측 구성은 `rl.actor.observation`, 정책 분포는 `rl.model.ActorCritic`,
구간 보상은 `rl.trajectory.SegmentRewards` (Σ 구간 보상 = 판 보상 을 지키는 테스트 `tests/learner/test_rl.py` 유지).
`QASession.make_static_optimizer` 와 CLI `--method` choices 에 등록하고, `tests/learner/test_optim.py` 에 sphere 함수 수렴 테스트 추가.
