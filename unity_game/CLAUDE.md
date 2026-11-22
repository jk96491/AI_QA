# unity_game — 밸런스 QA 테스트용 Unity 게임

이 폴더는 **Unity 프로젝트 루트**다. 만드는 게임은 사람이 즐길 완성품이 아니라, 학습 플랫폼(`../balance_qa`)이 TCP로 접속해 수천~수만 판을 돌리는 **실행 환경**이다.

**작업 전에 반드시 `AGENT_GUIDE.md` 를 끝까지 읽는다.**

 규칙의 원본은 그 문서와 `../docs/PROTOCOL.md`(v1.2)이며, 충돌하면 PROTOCOL.md 가 우선이다.

> 상위 `../CLAUDE.md` 는 파이썬 학습 플랫폼 개발용 규칙이다. 이 폴더 작업에는 **이 파일과 AGENT_GUIDE.md** 를 따른다.
> 단, 상위 문서의 "서로 import 금지 / 프로토콜로만 연결" 원칙은 여기에도 그대로 적용된다.

## 절대 규칙

1. **`unity_game/` 밖의 파일을 수정하지 않는다.** (`balance_qa/`, `game_sim/`, `tests/`, `docs/`, `qa_specs/`, `run/`, 상위 `CLAUDE.md` 등)
   - `../game_sim/` 은 **읽기 전용 참조 구현**이다. 특히 `../game_sim/server/session.py` 의 흐름을 C# 로 옮긴다.
   - 프로토콜·학습 쪽 변경이 필요하면 고치지 말고 `PROTOCOL_CHANGE_REQUEST.md` 에 요구사항과 이유를 적고 사용자에게 알린 뒤 멈춘다.
2. **프로토콜 v1.2 준수.** TCP, UTF-8(BOM 없음) JSON 1개 + `\n`, 게임 = 서버, 인스턴스당 포트 1개·연결 1개, 오류 후에도 연결 유지.
3. **결정성.** 같은 class·scenario·seed·params·트리거 응답 → 같은 result.
   판마다 `System.Random(seed)` 하나만. `UnityEngine.Random`, `Time.deltaTime`/`Time.time`(로직), 코루틴·async 타이밍, 물리 자동 시뮬레이션, Dictionary 순회 순서 의존, 판 사이 static 상태 **금지**.
4. **속도.** 로직은 렌더링과 분리된 고정 dt 수동 루프로 돌린다 (`while (!done) world.Step(FIXED_DT);`). 5분 전투 1판 ≤ 100 ms 목표. 판 사이 씬 로드 금지.
5. **트리거.** index 0 = 판 시작 직후, 이후 보스 체력 75·50·25% 경계마다 연속 번호. 응답 올 때까지 게임 시간 정지. `state`(0~1 정규화) + `totals`(누적 elapsed·deaths·consumables_used·boss_hp_remaining) 포함. 응답 params 는 부분 덮어쓰기.
6. **정의서(describe).** 파라미터 `name, range, default(손 튜닝 값), group(bt|persona), optimize, unit, description`. 학습 쪽이 쓰는 이름(`survival_hp_threshold`, `dps_hp_floor`, `w_burst`, `w_dps`, `w_survival`, `potion_hp`, `resource_reserve`, `min_commit`, 원거리 `kite_distance`)은 **모든 직업에 같은 이름·의미로** 둔다. 다른 BT 설계가 필요하면 규칙 1처럼 요청서 먼저.
7. **파라미터 검증은 엄격하게.** 모르는 이름 `unknown_param`, 범위 밖 `param_out_of_range`, 생략은 default.

## 폴더

```
Assets/QA/Protocol   QaServer, QaSession, 메시지 DTO, 오류 코드   (← ../game_sim/server)
Assets/QA/Sim        전투 로직 (MonoBehaviour 비의존)              (← ../game_sim/sim)
Assets/QA/BT         BT 노드·필요도 식·블록·전략 선택·블랙보드      (← ../game_sim/bt)
Assets/QA/Data       직업·보스·시나리오 정의                       (← ../game_sim/data)
Assets/QA/Boot       명령행(-qaPort) 파싱 → 헤드리스 서버 시작
Assets/Presentation  화면 (선택, 로직이 여기에 의존 금지)
Build/               빌드 결과 (PyCharm 색인 제외)
```

`Library/ Temp/ Logs/ obj/ UserSettings/ Build/ Builds/` 에는 코드·데이터를 두지 않는다 (색인 제외·버전 관리 제외 대상).

## 실행

- 서버 모드: `Build/<Game>.exe -batchmode -nographics -qaPort 7777` → stdout 에 `LISTENING 7777`
- JSON: `com.unity.nuget.newtonsoft-json`

## 검증 명령 (상위 폴더 `AI_QA` 에서 실행)

이 폴더에서 실행할 때는 `cd ..` 후 실행한다. 파이썬은 반드시 `venv\Scripts\python.exe`.

```bash
venv\Scripts\python.exe -m balance_qa check-game                       # 참조 구현(game_sim)으로 기대 동작 확인
venv\Scripts\python.exe -m balance_qa check-game --game 127.0.0.1:7777 # Unity 빌드 적합성 — 전 항목 PASS 가 목표
venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777 list       # 정의서 확인
venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777 evaluate --cls <c> --persona stable -n 50   # 처리량
venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777,127.0.0.1:7778 optimize --cls <c> --persona stable --budget 600 --eval-n 50
venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777,127.0.0.1:7778 impala   --cls <c> --persona stable --budget 400 --eval-n 50
venv\Scripts\python.exe -m balance_qa --workers 2 --game-cmd "unity_game/Build/<Game>.exe -batchmode -nographics -qaPort {port}" list
```

**최종 확인 = 전체 사이클 점검** (모든 단계 OK 여야 완료):
```bash
venv\Scripts\python.exe run/run_full_cycle.py      # 파일 맨 위 GAME = "127.0.0.1:7777,127.0.0.1:7778" 로 수정 후
```

참조 구현과 나란히 비교하려면 `venv\Scripts\python.exe -m game_sim serve --port 7790` 으로 파이썬 게임을 띄우고 같은 명령을 `--game 127.0.0.1:7790` 으로 돌린다.

## 작업 순서 (단계마다 check-game 실행 후 결과 보고)

1. 헤드리스 부트 + `hello` / `describe`
2. 트리거 없는 `run_episode` + 결과 필드
3. 오류 처리 (8개 오류 코드, 오류 후 연결 유지)
4. 결정성 (같은 seed 두 번 → 동일 결과)
5. 트리거 + `totals`
6. 성능 (판당 시간 측정·보고)
7. 콘텐츠 확장 (직업 3개+, 보스 페이즈·광역기·기믹, 패치 시나리오)

## 산출물

- `README.md`: Unity 버전, 빌드 방법, 실행 명령, 데이터 편집 위치
- 데이터 변경 시 `game_version`, 직업별 `spec_version` 증가
- 필요 시 `PROTOCOL_CHANGE_REQUEST.md`
