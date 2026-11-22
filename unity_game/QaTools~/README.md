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
| `retune.py search/eval/blend <cls> ...` | stable(θ.8 φ.7) 기준 파라미터 무작위 탐색 / 평가 / default↔최적값 비율 이분 탐색 (목표 클리어율 맞추기) |

## 밸런스 조정 흐름 (0.4.0 에서 쓴 방법)

1. `Assets/QA/Data/Resources/QaData/` JSON 수정 (보스·직업·시나리오). 규칙 상수는 `Assets/QA/Sim/SimConfig.cs`
2. `pwsh unity_game/QaTools~/tune.ps1 -n 300 -personas stable -keep` → default 성능
3. 학습 여지 확인: `venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7791 optimize --cls <c> --persona stable --budget 1200 --eval-n 150`
4. default 를 목표 클리어율로: `retune.py blend <c> '<최적 params json>' 0.6 300` → 값을 반올림해 JSON 에 넣고 2 로 재확인
5. `game.json` 의 `game_version`, 바뀐 직업 `spec_version` 올리기 → `build.ps1 -check`

하네스 포트 7791, 빌드 인스턴스 7777/7778, 파이썬 참조(game_sim) 7790 을 관례로 쓴다.
`bin/ obj/` 는 dotnet 빌드 산출물 (지워도 됨).
