# QaTools~ — 검증·밸런스 도구 (Unity 가 임포트하지 않는 폴더)

모든 명령은 상위 `AI_QA` 폴더에서, 파이썬은 `venv\Scripts\python.exe`.

| 파일 | 용도 |
|---|---|
| `build.ps1 [-check]` | Unity 명령행 빌드 → `Build/QaArena.exe`. `-check` 면 7777 로 띄워 check-game + edge_cases (에디터가 열려 있으면 실패) |
| `edge_cases.py --game H:P` | 프로토콜 경계 사례 37개 (check-game 이 안 보는 오류 처리·연결 끊김) |
| `harness/` | Unity 없이 같은 로직 소스로 QA 서버를 띄우는 .NET 9 하네스 — 결과가 Unity 빌드와 바이트 단위로 같다. 판당 ~1ms |
| `compilecheck/` | 에디터를 열어 둔 상태에서도 `Assets/**/*.cs` 전체를 Unity DLL 로 컴파일 검사 (`dotnet build`) |
| `tune.ps1 [-n 300] [-personas stable,aggressive] [-keep]` | 하네스 재빌드·기동 → 직업별 손 튜닝 default 성능 (클리어·멈춤·사망) |
| `peek.py [port] [n] [θ,φ]` | 하네스에 직접 판을 돌려 블록 점유·보스 기술 횟수·피해 출처 진단 (`record_events`) |
| `try_patch.py <cls> '<patch>' [budget]` | 직업 JSON 임시 패치(stats·skills·defaults) → 하네스 재기동 → default + CMA 최적점(사망·클리어) 비교. 원본 `<cls>.json.bak` 백업, 끝나면 정식 값으로 되돌리고 .bak 삭제 |
| `retune.py search/eval/blend <cls> ...` | stable(θ.8 φ.7) 기준 파라미터 무작위 탐색 / 평가 / default↔최적값 비율 이분 탐색 (목표 클리어율 맞추기) |
| `balance_snapshot.py save/diff <host:port> <json>` | 밸런스 모드 회귀(T1): 고정 seed·트리거 응답 21판 `episode_result` 저장/바이트 비교. 기준선 `t1_baseline_0.5.0.json` |
| `play_check.py --game H:P [--omni H:P] [--balance H:P]` | 플레이 모드 자체 검증 (T2 핸드셰이크·T3 지각 필터·T4 튜토리얼 01~05 완주·T5 전투 동일성·T6 전투 인계·T7 결정성·T8 새 게임). `--omni` = `-qaPlayOmniscient` 인스턴스, `--balance` = 같은 빌드의 밸런스 인스턴스, `--game2` = T7 교차 비교용 다른 플레이 인스턴스 |
| `play_shots.py <출력 폴더>` | 창 모드 플레이 인스턴스(7800)를 늑대왕 전투까지 몰고 가며 창 캡처 (필드·장면 전환·전투·복귀 PNG) |
| `import_tmp_essentials.py` | TMP Essential Resources 를 `Assets/TextMesh Pro/` 로 직접 풀기 (빌드 전 1회) |

## 밸런스 조정 흐름 (0.4.0 에서 쓴 방법)

1. `Assets/QA/Data/Resources/QaData/` JSON 수정 (보스·직업·시나리오). 규칙 상수는 `Assets/QA/Sim/SimConfig.cs`
2. `pwsh unity_game/QaTools~/tune.ps1 -n 300 -personas stable -keep` → default 성능
3. 학습 여지 확인: `venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7791 optimize --cls <c> --persona stable --budget 1200 --eval-n 150`
4. default 를 목표 클리어율로: `retune.py blend <c> '<최적 params json>' 0.6 300` → 값을 반올림해 JSON 에 넣고 2 로 재확인
5. `game.json` 의 `game_version`, 바뀐 직업 `spec_version` 올리기 → `build.ps1 -check`

하네스 포트 7791, 빌드 인스턴스 7777/7778, 파이썬 참조(game_sim) 7790, 플레이 모드 7800/7801(omniscient) 을 관례로 쓴다.
`bin/ obj/` 는 dotnet 빌드 산출물 (지워도 됨).
