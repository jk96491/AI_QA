# 게임 ↔ 학습 플랫폼 프로토콜 v1.2

> 변경 이력: **1.2** — `result.stalled`, `result.stall_reason` 추가. 멈춘 판은 `invalid` 가 아니라 **실패 판**(4.5). 1.x 와 호환.
> **1.1** — `trigger.totals`(판 시작부터의 누적값)와 `describe.triggers.totals` 추가. IMPALA 구간 보상에 필요. 1.0 과 호환(같은 주 버전).


학습 플랫폼(`balance_qa`)과 게임(현재 `game_sim` 파이썬 대역, 추후 **Unity 빌드**) 사이의 **유일한 계약**이다.
게임 구현이 이 문서를 지키고 `python -m balance_qa check-game --game HOST:PORT` 를 통과하면, 학습 쪽 코드는 수정 없이 붙는다.

원문 제안서 대응: 9장 "트리거 발생 → 상태 입력 → 파라미터 출력", 11장 "에피소드 실행 API", 12장 "정의서·에피소드 실행 API" 인터페이스.

---

## 1. 역할 분담

| | 게임 (Unity / game_sim) | 학습 플랫폼 (balance_qa) |
|---|---|---|
| 보유 | 전투, **BT**, 직업·스킬·보스 수치, 시나리오(패치) | 최적화기·정책(torch), 페르소나, 보상, 통계, 리포트 |
| 공개 | 정의서: BT 파라미터 이름·범위·기본값, 트리거 상태 키 | — |
| 실행 | 판(episode)을 seed 로 결정론적으로 끝까지 실행 | 어떤 파라미터로 몇 판 돌릴지 결정 |
| RL | 게임 인스턴스 = IMPALA **액터의 환경** | 액터 스레드·정책 추론·V-trace 학습기 |
| 결정 | 300ms 마다 BT 가 행동 결정 (게임 내부) | 판 시작/트리거 때만 **숫자(파라미터)** 를 정함 |

학습 쪽은 스킬·스탯을 모른다. **파라미터 숫자를 보내고 결과를 받을 뿐이다.**

## 2. 전송

- **TCP**, 게임이 **서버**(포트 대기), 학습 쪽이 클라이언트.
- 메시지 = **UTF-8 JSON 객체 1개 + `\n`** (JSON Lines). 모든 메시지에 `"type"` 필드.
- 게임 인스턴스 1개 = 서버 1개 = **동시 연결 1개**, 연결 안에서 요청은 **순차** 처리.
  - 병렬 실행은 게임 인스턴스를 포트별로 여러 개 띄워서 한다 (원문 11장 VM 풀).
- 포트는 실행 인자로 받는다. 예) `MyGame.exe -batchmode -nographics -qaPort 7777`
- 오류 응답(`error`) 후에도 **연결은 유지**한다. 연결 종료는 클라이언트의 `bye` 또는 소켓 종료.

## 3. 메시지 흐름

```
학습 플랫폼                                  게임
   │ ── hello ───────────────────────────────▶ │
   │ ◀────────────────────────────── hello_ok ─ │
   │ ── describe ────────────────────────────▶ │
   │ ◀──────────────────────────── description ─ │   (정의서 공개)
   │                                             │
   │ ── run_episode (트리거 없음) ───────────▶ │   판 전체를 게임이 실행
   │ ◀─────────────────────────── episode_result ─ │
   │                                             │
   │ ── run_episode (triggers 요청) ─────────▶ │
   │ ◀──────────────── trigger(index 0, 시작) ─ │   게임은 응답 올 때까지 판을 멈춤
   │ ── trigger_response(params) ────────────▶ │
   │ ◀──────────────── trigger(index 1, 75%) ─ │
   │ ── trigger_response(params) ────────────▶ │
   │                  ...                        │
   │ ◀─────────────────────────── episode_result ─ │
   │ ── bye ─────────────────────────────────▶ │
```

## 4. 메시지 명세

### 4.1 `hello` → `hello_ok`

```json
{"type":"hello","protocol_version":"1.2","client":"balance_qa"}
{"type":"hello_ok","protocol_version":"1.2","game":"game_sim","game_version":"0.4.0"}
```
- 주(major) 버전이 다르면 `error(protocol_version)`.

### 4.2 `describe` → `description` (정의서)

```json
{"type":"describe"}
```
```json
{
  "type": "description",
  "protocol_version": "1.2",
  "game": "game_sim", "game_version": "0.4.0",
  "time_limit": 600.0,
  "max_deaths": 3,
  "decision_interval": 0.3,
  "classes": [
    {
      "name": "mage", "display_name": "마법사", "ranged": true, "spec_version": "0.1",
      "params": [
        {"name":"survival_hp_threshold","range":[0.05,1.0],"default":0.5,"optimize":false,"group":"persona","unit":"hp_ratio","description":"θ ..."},
        {"name":"w_burst","range":[0.0,1.0],"default":0.6,"optimize":true,"group":"bt","unit":"weight","description":"버스트 블록 가중치"}
      ]
    }
  ],
  "scenarios": [{"name":"base","description":"원본"}, {"name":"patch_boss_hp_up5","description":"..."}],
  "triggers": {
    "type": "boss_hp_below",
    "supported": [0.75, 0.5, 0.25],
    "state_features": ["hp_ratio","boss_hp_ratio","potions_ratio","resource_ratio","burst_ready","time_ratio","deaths_ratio"],
    "totals": ["elapsed","deaths","consumables_used","boss_hp_remaining"]
  },
  "result_fields": ["seed","cleared", "..."]
}
```

| 필드 | 필수 | 의미 |
|---|---|---|
| `time_limit` | O | 판 제한 시간(초). 학습 쪽 중도절단 계산에 사용 |
| `max_deaths` | O | 이 횟수를 넘겨 사망하면 실패 |
| `classes[].params[]` | O | BT 파라미터. `default` = **개발팀 손 튜닝 값** (기준선) |
| `params[].group` | O | `bt`: 학습 대상 / `persona`: 페르소나가 정하는 값 (θ, φ 등) |
| `params[].optimize` | | 생략 시 `group == "bt"` |
| `scenarios` | O | `"base"` 필수. 패치 시나리오 이름 |
| `triggers.state_features` | O | 트리거 상태 키 순서. **정책 신경망 입력 순서**가 된다 |
| `triggers.supported` | | 기본 트리거 경계 (보스 체력 비율) |
| `triggers.totals` | v1.1 | `trigger.totals` 로 보내는 누적값 키. `elapsed`, `deaths`, `consumables_used` 가 있어야 IMPALA 학습 가능 |

필수 BT 파라미터(현재 BT 구조 기준): `survival_hp_threshold`, `dps_hp_floor`(persona), `w_burst`, `w_dps`, `w_survival`, `potion_hp`, `resource_reserve`, `min_commit`(bt). 원거리는 `kite_distance`.

### 4.3 `run_episode` → (`trigger` ↔ `trigger_response`)* → `episode_result`

```json
{
  "type": "run_episode",
  "episode_id": "127.0.0.1:7777#42",
  "class": "warrior",
  "scenario": "base",
  "seed": 1000123,
  "params": {"w_burst":0.71,"survival_hp_threshold":0.8},
  "triggers": {"boss_hp_below":[0.75,0.5,0.25]},
  "record_events": false
}
```

| 필드 | 필수 | 규칙 |
|---|---|---|
| `episode_id` | O | 응답·트리거에 그대로 돌려줌 |
| `class` | O | 없으면 `error(unknown_class)` |
| `scenario` | | 생략 = `"base"`. 없으면 `error(unknown_scenario)` |
| `seed` | O | **판의 모든 난수는 이 seed 에서만** 나와야 함 (6장) |
| `params` | | 생략한 파라미터는 정의서 `default`. 모르는 이름 → `error(unknown_param)`, 범위 밖 → `error(param_out_of_range)` |
| `triggers` | | 없거나 비어 있으면 트리거 없이 판 끝까지 실행 |
| `record_events` | | true 면 `result.events` 포함 (리플레이·디버깅) |

### 4.4 `trigger` / `trigger_response`

```json
{"type":"trigger","episode_id":"...#42","index":1,
 "state":{"hp_ratio":0.50,"boss_hp_ratio":0.73,"potions_ratio":1.0,"resource_ratio":0.2,"burst_ready":0.0,"time_ratio":0.11,"deaths_ratio":0.0},
 "totals":{"elapsed":67.8,"deaths":0,"consumables_used":0,"boss_hp_remaining":0.73}}
{"type":"trigger_response","episode_id":"...#42","index":1,"params":{"w_survival":0.42,"potion_hp":0.55}}
```

규칙:
1. `triggers` 를 요청한 판에서만 보낸다.
2. **index 0 = 판 시작 직후** (첫 결정 전). 이후 보스 체력이 각 경계 **아래로 처음 내려갈 때** index 1, 2, ... (연속 번호).
3. 한 틱에 여러 경계를 동시에 넘으면 **트리거 1번**만 보낸다.
4. 보스가 이미 죽었으면(클리어) 보내지 않는다.
5. 게임은 `trigger_response` 가 올 때까지 **판 진행을 멈추고 기다린다** (게임 시간 정지).
6. `params` 는 **부분 덮어쓰기**: 준 키만 바뀌고 나머지는 직전 값 유지. 검증 규칙은 4.3 과 같다.
7. `state` 값은 모두 **0~1 정규화된 숫자**, 키는 `describe.triggers.state_features` 전부 포함.
8. `episode_id` 또는 `index` 가 맞지 않으면 `error(bad_request)` 로 판을 중단한다.
9. (v1.1) `totals` = **판 시작부터의 누적값**, 이름·단위는 `episode_result` 와 같다 (`elapsed` 초, `deaths`, `consumables_used`, `boss_hp_remaining`).
   index 0 의 `elapsed` 는 0, 이후 단조 증가, 마지막 트리거 값 ≤ `result` 값.
   학습 쪽은 연속한 트리거의 `totals` 차이로 **구간 보상**을 계산한다 (Σ 구간 보상 = 판 보상).

### 4.5 `episode_result`

```json
{"type":"episode_result","episode_id":"...#42","result":{
  "seed":1000123,"cleared":true,"elapsed":331.2,"clear_time":331.2,"boss_hp_remaining":0.0,
  "deaths":0,"consumables_used":1,"damage_dealt":50120.0,"damage_taken":8120.5,
  "segment_times":[80.1,84.0,83.2,83.9],"block_time":{"dps":250.2,"burst":26.1,"survival":52.0,"gimmick":2.1},
  "gimmick_success":8,"gimmick_fail":0,"triggers_fired":4,"invalid_actions":0,
  "stalled":false,"stall_reason":null,"invalid":false,"invalid_reason":null}}
```

| 필드 | 필수 | 의미 |
|---|---|---|
| `seed` | O | 요청 seed 그대로 |
| `cleared` | O | 클리어 여부 |
| `elapsed` | O | 종료까지 게임 시간(초) |
| `clear_time` | O | 클리어 시간, 미클리어면 `null` |
| `boss_hp_remaining` | O | 0~1 |
| `deaths` | O | 사망 횟수 |
| `consumables_used` | 권장 | 소모품 사용 수 (효율형 보상) |
| `segment_times` | 권장 | 보스 페이즈 구간별 소요 시간 (원문 "단계별 클리어 시간") |
| `block_time` | 권장 | BT 블록별 점유 시간 (행동 분포 진단) |
| `triggers_fired` | 권장 | 보낸 트리거 수 |
| `stalled`, `stall_reason` | v1.2 필수 | **진전 없이 멈춘 판** (예: 90초 동안 보스 피해 0). BT·정책의 실패이므로 `cleared=false`, `invalid=false` 로 보낸다 |
| `invalid`, `invalid_reason` | 권장 | **환경 오류**로 결과를 쓸 수 없는 판만 (게임 내부 예외 등). 학습·평가 집계에서 제외 |

**멈춘 판 처리 (v1.2)** — 학습 쪽은 멈춘 판을 **시간 초과와 같은 실패**로 벌점에 포함한다:
`effective_time = time_limit + boss_hp_remaining × time_limit`.
멈춘 판을 `invalid` 로 빼면 "질 것 같으면 멈추는" 정책이 벌을 피하게 되므로, 멈춤을 `invalid` 로 보내면 안 된다.
(호환: v1.1 게임이 `invalid: true` + `invalid_reason` 이 `"stalled"` 로 시작하면 학습 쪽이 멈춘 판으로 바꿔 해석한다.)
| 기타 | 선택 | `damage_*`, `gimmick_*`, `invalid_actions`, `events` |

### 4.6 `error`

```json
{"type":"error","code":"param_out_of_range","message":"w_dps=5 가 범위 [0, 1] 밖","episode_id":"...#42"}
```

| code | 언제 |
|---|---|
| `bad_request` | JSON 파싱 실패, 필수 필드 누락, 트리거 응답 불일치 |
| `unknown_type` | 모르는 `type` |
| `protocol_version` | 주 버전 불일치 |
| `unknown_class` / `unknown_scenario` | 정의서에 없음 |
| `unknown_param` / `param_out_of_range` | 파라미터 검증 실패 |
| `internal` | 게임 내부 예외 (연결은 유지) |

### 4.7 `bye`

```json
{"type":"bye"}
```
응답 없음. 게임은 연결을 닫고 다음 연결을 기다린다.

## 5. 정의서 작성 규칙 (개발팀)

- `default` 는 개발팀이 손으로 맞춘 값. 학습 결과는 항상 이 기준선과 비교된다.
- `range` 는 **기획 의도 범위**. 최적화는 이 안에서만 탐색한다 (원문 4장 답변 4).
- 바꾸면 행동이 눈에 띄게 달라지는 값만 노출, 직업당 5~20개 (원문 5장).
- 같은 의미의 값은 하나로 묶는다. 파라미터 이름은 직업 간에 같은 의미면 같은 이름.

## 6. 결정성 요구사항 (가장 중요)

같은 `(class, scenario, seed, params, 트리거 응답 순서)` → **완전히 같은 `result`**.
이게 깨지면 최적화가 노이즈를 학습하고, 직업 간 비교가 무의미해진다.

Unity 구현 시:
- 판마다 `new System.Random(seed)` (또는 자체 PRNG) 하나만 쓰고 `UnityEngine.Random` 전역 상태에 의존하지 않는다.
- **고정 시간 간격 시뮬레이션**: 프레임 시간(`Time.deltaTime`)이 아닌 고정 dt 로 직접 루프. 렌더링과 분리해 실시간보다 빠르게 돈다.
- 물리 엔진을 쓰면 `Physics.autoSimulation = false` 후 `Physics.Simulate(dt)` 로 수동 진행.
- `Dictionary` 순회 순서, 병렬 Job, 부동소수 누적 순서 등 비결정 요소를 피한다.
- 트리거 대기 중에는 게임 시간을 멈춘다.

## 7. 성능 기대치

- 학습 1회에 수천~수만 판. 판당 수십 ms 수준이 이상적 (파이썬 대역: 20~40 ms).
- 헤드리스(`-batchmode -nographics`) + 렌더링 없는 고정 dt 루프 권장.
- 병렬은 인스턴스 수로 확장 (`--workers N` / `--game host:p1,host:p2,...`).

## 8. 버전 관리

- `protocol_version` = `주.부`. 필드 추가는 부 버전, 의미 변경·삭제는 주 버전.
- 학습 쪽은 모르는 필드를 무시한다. 게임도 모르는 요청 필드는 무시한다.
- 게임 데이터 변경 시 `game_version` 과 각 class 의 `spec_version` 을 올린다. 학습 결과(`params.json`)에 함께 기록된다.

## 9. 적합성 검사

```bash
# Unity 빌드를 7777 포트로 띄운 뒤
python -m balance_qa check-game --game 127.0.0.1:7777
```

검사 항목: hello · describe 형식 · 기본 파라미터 판 · `params` 생략 = default · **시드 결정성** · seed 변동 · `result.stalled`(v1.2, 경고 항목) ·
**트리거 왕복**(index 0 시작, 연속 번호, 상태 키) · **totals 누적값**(v1.1, IMPALA 용, 경고 항목) · 오류 코드 4종 · 오류 후 연결 유지 · 모든 시나리오 실행.

## 10. 연결 방법 (학습 쪽)

```bash
# 이미 떠 있는 게임 인스턴스들에 접속
python -m balance_qa --game 127.0.0.1:7777,127.0.0.1:7778 optimize --cls mage --persona stable

# 명령 템플릿으로 게임 N개를 띄우고 접속 ({port} 자동 할당)
python -m balance_qa --workers 8 --game-cmd "Build/MyGame.exe -batchmode -nographics -qaPort {port}" optimize ...

# 파이썬 게임 대역 (기본)
python -m balance_qa --workers 4 optimize ...
```

## 부록 A. Unity C# 구현 뼈대 (참고)

```csharp
// QaServer.cs — 헤드리스 빌드에서 시작 시 실행. JSON 은 Newtonsoft.Json 권장 (JsonUtility 는 Dictionary 미지원)
public class QaServer {
    public void Run(int port) {
        var listener = new TcpListener(IPAddress.Loopback, port);
        listener.Start();
        while (true) {
            using var client = listener.AcceptTcpClient();
            client.NoDelay = true;
            using var stream = client.GetStream();
            var reader = new StreamReader(stream, new UTF8Encoding(false));
            var writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true, NewLine = "\n" };
            var session = new QaSession(reader, writer);          // game_sim/server/session.py 와 같은 역할
            string line;
            while ((line = reader.ReadLine()) != null) {
                if (line.Trim().Length == 0) continue;
                if (!session.Handle(JObject.Parse(line))) break;  // bye 면 false
            }
        }
    }
}

// QaSession.Handle: hello → hello_ok, describe → description, run_episode → RunEpisode(...)
// RunEpisode:
//   var rng = new System.Random(seed);
//   var bt = BuildCombatBT(cls, ResolveParams(defaults, msg["params"]));   // 검증 실패 → error 응답
//   if (triggers) { Send(trigger index 0 + state + totals); bt.SetParams(Recv trigger_response); }
//   while (!done) {
//       world.Step(FIXED_DT, rng);                 // BT 300ms 결정 포함, 렌더링 없음
//       if (BossCrossedThreshold()) { Send(trigger + totals); bt.SetParams(Recv()); }   // 응답까지 시간 정지
//   }
//   Send(episode_result);
```
