# QaArena — 밸런스 QA 테스트용 Unity 게임

학습 플랫폼(`../balance_qa`)이 TCP 프로토콜 v1.2(`../docs/PROTOCOL.md`)로 접속해 수천~수만 판을 돌리는 헤드리스 전투 게임.
로직은 `../game_sim`(파이썬 참조 구현)을 C# 로 옮긴 것이다.

- **Unity**: 6000.0.60f1 (Unity 6 LTS), 스크립팅 백엔드 Mono
- **패키지**: `com.unity.nuget.newtonsoft-json` 3.2.1
- **빌드 결과**: `Build/QaArena.exe`

## 에디터에서 쓰기

### 프로젝트 열기
Unity Hub → **Add → Add project from disk** → `AI_QA/unity_game` 선택 → 6000.0.60f1 로 열기.

> 에디터가 이 프로젝트를 열고 있는 동안에는 명령행 빌드(아래)가 실패한다 (Unity 는 한 프로젝트를 한 프로세스만 연다). 명령행으로 빌드하려면 에디터를 닫거나 메뉴로 빌드한다.

### Play 모드에서 QA 서버 켜기
1. 메뉴 **QA → Play Mode Server → Enabled** 체크 (기본 포트 7777, 바꾸려면 **QA → Play Mode Server → Port...**)
2. **Play** ▶ — Game 뷰 좌상단에 `QA 서버 127.0.0.1:7777 / 연결 / 처리한 판` 이 표시되고, Console 에 `[QA] LISTENING 7777`
3. 상위 폴더 `AI_QA` 에서 학습 쪽 명령 실행 (예: `venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777 check-game`)
4. Play 를 멈추면 서버도 닫힌다

- 서버는 백그라운드 스레드에서 돌아 에디터가 멈추지 않는다. 판 진행은 프레임과 무관한 고정 dt 루프라 Play 모드에서도 결과가 빌드와 같다.
- C# 코드에 중단점을 걸고 디버깅할 수 있다 (Rider/VS 에서 Attach to Unity). 트리거 응답 대기 중에는 게임 시간이 멈춘다.
- 대량 학습은 에디터보다 빌드 인스턴스 여러 개가 빠르다 (아래).
- Enabled 를 끈 상태의 Play 는 일반 실행 (서버 없음).

### 전투 뷰어 (화면)
Play 하면 (서버 설정과 무관하게) 전투가 화면에 그려진다. 헤드리스(`-batchmode`)에서는 만들지 않는다.
- 오른쪽 **전투 설정** 패널: 직업·시나리오·seed·BT 파라미터 슬라이더 → **▶ 전투 시작**
- **학습 결과 파라미터 불러오기**: `reports/<run>/params.json` 내용을 붙여넣으면 직업·시나리오·파라미터가 자동 적용
- **학습 서버 판 보기** (Play Mode Server 켠 상태): 학습 쪽이 마지막으로 돌린 판을 같은 seed·params·트리거 응답으로 재생 → 결과가 서버와 같으면 `✓`. "자동 따라보기" 를 켜면 새 판이 올 때마다 재생
- 조작: Space 일시정지, N 한 틱, R 같은 판 다시, Enter 새 전투, 1~6 속도(0.5x~16x), Tab 패널, 휠 확대, 오른쪽 드래그 회전
- 화면: 보스 체력바(페이즈 눈금)·준비 동작 바, 바닥 빨간 경고(내려찍기·처형)/주황(도약), 노란 고리 = 기믹 경고, 플레이어 체력·자원·시전 바·현재 BT 블록, 전투 기록, 결과(블록 점유 비율)
- 맵 경계: 둘 다 반지름 27m(주황 고리) 안에서만 움직인다 — 경계에 닿으면 보스 주위로 벽을 따라 돌고, 그래도 넘으면 둘을 함께 안쪽으로 민다. 판 로직은 거리만 다루므로 결과에는 영향 없음
- 그래픽은 Unity 기본 도형으로 조립한 것 (`Assets/Presentation/ViewerArt.cs` 의 `BuildBoss`/`BuildPlayer` 를 프리팹으로 바꾸면 실제 모델 적용). 판 로직은 뷰어에 의존하지 않는다.

### 빌드
- 에디터 메뉴 **QA → Build Windows (QA server)** → `Build/QaArena.exe`
- 명령행 (에디터 닫힌 상태, `unity_game` 폴더에서):
  ```
  "C:\Program Files\Unity\Hub\Editor\6000.0.60f1\Editor\Unity.exe" -batchmode -quit -projectPath . -executeMethod Qa.EditorTools.QaBuild.BuildWindows -logFile Logs/build.log
  ```

## 빌드 실행

| 모드 | 명령 | 비고 |
|---|---|---|
| 헤드리스 (학습용) | `Build/QaArena.exe -batchmode -nographics -qaPort 7777` | 메인 스레드 블로킹, CPU 대기 0. `LISTENING 7777` 은 Player.log 에 (stdout 으로 보려면 `-logFile -`) |
| 창 모드 (확인용) | `Build/QaArena.exe -qaPort 7778` | 전투 뷰어 창 (학습 판 재생 가능) |
| 창 모드 + 자동 재생 | `Build/QaArena.exe -qaPort 7778 -qaFollow -qaViewSpeed 8 -qaPanel 0` | 학습 쪽 `--view` 용 |

창 모드 뷰어 인자 (판 로직과 무관, 화면만):
- `-qaFollow` — 시작부터 "학습 판 자동 따라보기" 켜기 (재생이 끝날 때마다 그 시점의 최신 학습 판을 재생)
- `-qaViewSpeed <x>` — 재생 속도, 0.5/1/2/4/8/16 중 가장 가까운 값 (기본 1)
- `-qaPanel 0` — 오른쪽 설정 패널 접기 (Tab 으로 다시 펼침)
| 일반 실행 | `Build/QaArena.exe` | `-qaPort` 없음 → 서버 없음 |

- `-qaHost <ip>` 로 바인드 주소 변경 (기본 127.0.0.1). `-qaPort 0` 이면 빈 포트 자동 선택.
- 인스턴스 1개 = 포트 1개 = 동시 연결 1개. 병렬은 인스턴스를 여러 개 띄운다.
- 여러 인스턴스를 직접 띄울 때는 `-logFile Logs/player<port>.log` 로 로그를 나눈다.

학습 쪽에서 띄우기 (상위 `AI_QA` 폴더):
```
venv\Scripts\python.exe -m balance_qa --workers 4 --game-cmd "unity_game/Build/QaArena.exe -batchmode -nographics -qaPort {port}" optimize --cls warrior --persona stable --budget 600
```

## 도구

빌드·검증·밸런스 측정 도구는 `QaTools~/README.md` (명령행 빌드 `build.ps1 -check`, .NET 하네스, 컴파일 검사, `tune.ps1`·`retune.py`).

## 검증 (상위 `AI_QA` 폴더에서)

```
venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777 check-game          # 적합성 (전 항목 PASS)
venv\Scripts\python.exe unity_game/QaTools~/edge_cases.py --game 127.0.0.1:7777 # 오류 처리 경계 사례 37개
```
> `--game` 은 하위 명령 **앞**에 쓴다.

## 보스 (고정 BT — 학습 대상 아님)

보스 BT 의 상수는 `bosses/default.json` 에만 있고 `describe` 로 공개하지 않는다. 학습 쪽은 플레이어 BT 파라미터만 바꾼다.
0.3초마다 위에서부터 조건이 맞는 첫 행동 (준비 동작 중에는 완료까지 대기):

| 우선 | 행동 | 조건 → 효과 | 플레이어 쪽에서 의미 있는 선택 |
|---|---|---|---|
| 1 | 기믹 | 타이머 → 경고, 1.5s 안에 대응 못하면 최대 체력 60% | (강제 대응) |
| 2 | 광역기 | ~15s 마다, 거리 무관 | 체력 관리 |
| 3 | 처형 | 페이즈 3+, 플레이어 체력 < 35%, 사거리 안 → 1.0s 준비 후 750 | 저체력 근접 금지: θ, `potion_hp` |
| 4 | 도약 | 페이즈 2+, 거리 > 5.5m → 0.6s 후 앞에 착지 + 260 | 너무 멀리 빠지지 않기: `kite_distance` |
| 5 | 투척 | (기본 꺼짐 `throw_damage: 0`, 패치 시나리오용) | |
| 6 | 내려찍기 | 사거리 안, 11s 마다 → 1.2s 준비 후 사거리 안이면 360 | 근접 유지 vs 후퇴: `w_survival`, `w_dps` |
| 7 | 평타 | 사거리 안, 2s 마다 100 | |
| 8 | 추격 | 사거리 밖 → 접근 | |

모든 피해 × 페이즈 배율(1.0/1.1/1.25/1.4) × 격노(420초 이후 ×1.5) × 난수 ±20%.

0.5.0 기준 손 튜닝 default 성능 (stable, 학습 쪽 평가 시드 300판): warrior 클리어 61% [55, 66] 사망 1.00, mage 62% [57, 68], archer 100%(329s), 멈춘 판 0%.
학습 (stable, 하네스, 학습 쪽 보상에 클리어 실패 벌점 30분 반영 후): warrior CMA-ES 1,200판 62→99%, 사망 0.94 / IMPALA 1,600판 98%, 사망 0.93.
0.4.0 까지는 warrior 가 클리어에 ~3회 사망이 필요해 학습이 "안 죽고 시간 초과" 로 수렴했다 → 0.5.0 에서 방어력 0.5→0.6 으로 "거의 안 죽고 깨는" 길을 만들고,
손 튜닝 default 는 다시 덜 다듬어(`potion_hp` 0.5→0.36, `resource_reserve` 0.3→0.15: 물약을 늦게 마시고 비축을 덜 함) 클리어 60% 대로 맞췄다.
archer 는 여전히 쉬움 (직업 간 불균형 = 밸런스 QA 가 찾아야 할 대상).

### 플레이어 쪽 고정 규칙 (0.5.0)
- 부활: 사망 후 25초(`SimConfig.ReviveDelay`) 뒤 최대 체력의 50%(`ReviveHpRatio`)로 부활 — 부활을 회복 수단으로 쓰지 못하게
- 비전투 회복: 마지막 피격 후 `regen_delay`(6초) 지나면 초당 최대 체력의 `hp_regen_ratio`(1.2%) 회복 — `classes/<id>.json` 의 `stats`
- 전사 방어력 `armor` 0.6 (0.4.0 에서 0.3 → 0.5, 0.5.0 에서 0.6 — 근접 탱커가 보스 근접기를 버티고 사망 1회 이하로 클리어할 수 있도록)
- 생존 블록 최대 유지 시간: `bt_rules.survival_max_hold`(12초) 넘게 생존 블록에 머물면 `survival_lockout`(6초) 동안 생존 후보 제외 → 딜·접근으로 복귀 (멈춘 판 방지). 학습 대상 아님, describe 비공개
- 멈춘 판 (90초 동안 보스 피해 0): `stalled: true, stall_reason` 으로 보내는 **실패** 판 (v1.2). `invalid` 는 쓰지 않는다

> 0.2.0 부터 보스가 `game_sim`(파이썬 참조)과 다르다. 프로토콜·플레이어 BT 는 그대로 같다.

## 데이터 편집

`Assets/QA/Data/Resources/QaData/`
- `game.json` — `game`, `game_version` (**데이터를 바꾸면 올린다**)
- `classes/<id>.json` — 직업 스탯·스킬·BT 파라미터(`params`: range / default / group). 바꾸면 그 직업의 `spec_version` 도 올린다
- `bosses/default.json` — 보스 수치·페이즈
- `scenarios.json` — 패치 시나리오 (`scale` 배율 / `set` 값)

기동 시 전부 검증한다 (필수 파라미터, 범위, 모르는 필드 오타 등). 실패하면 서버가 뜨지 않고 로그에 이유를 남긴다.

## 코드 구조

```
Assets/QA/Protocol   QaServer(TCP), QaSession(메시지 처리), CombatEpisodeRunner(run_episode·트리거)
Assets/QA/Sim        CombatSim(고정 dt 루프), Player, Boss, Rng(xoshiro256**, 판마다 seed 로 1개)
Assets/QA/BT         노드, Blackboard, 필요도 N, 블록 5종, UtilitySelector(S = N × w), BTAgent
Assets/QA/Data       정의서 로더·검증 + JSON 데이터
Assets/QA/Boot       진입점 (-qaPort / 에디터 Play Mode Server)
Assets/QA/Editor     빌드 스크립트, QA 메뉴
Assets/Presentation  상태 표시 (로직은 여기에 의존하지 않음)
QaTools~             검증 스크립트 (Unity 가 임포트하지 않는 폴더)
```

결정성: 같은 class·scenario·seed·params·트리거 응답 → 바이트 단위로 같은 result.
`UnityEngine.Random`, `Time.*`, 코루틴, 물리, Dictionary 순회 순서에 로직이 의존하지 않는다.
