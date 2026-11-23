# BT-QA Game SDK 와 이 저장소

게임 연동 SDK 의 **원본은 별도 GitHub 레포 https://github.com/jk96491/btqa_sdk** 다 (사용자 결정 2026-11-23, 0.1.0 = `5627219`, **0.2.0 = `6c71e4c`** 프로토콜 1.4 `run_episode.initial_state`). 이 저장소는 원본을 참조하지 않고 **사본만** 쓴다.
SDK 가이드·변경 이력·자체 테스트는 SDK 레포에 있다 (`README.md`, `docs/SDK.md`, `CHANGELOG.md`, `tests/`).

## 사본 3개

| 사본 (이 저장소) | 원본 (SDK 레포) | 쓰는 곳 |
|---|---|---|
| `btqa_game/` | `python/btqa_game/` | `game_sim` (서버·세션·정의서 선언·검증). `python -m btqa_game check --game HOST:PORT` 로 적합성 검사도 됨 |
| `unity_game/Packages/com.btqa.game/` | `unity/com.btqa.game/` | QaArena — Unity embedded 패키지 (manifest 항목 없음, lock `source: embedded`) |
| `docs/PROTOCOL.md` | `docs/PROTOCOL.md` | 계약 v1.4 — 이 저장소 문서·코드 주석이 가리키는 곳 |

- **사본은 직접 고치지 않는다.** SDK 레포에서 고친 뒤 `venv\Scripts\python.exe run/run_sync_sdk.py` 로 복사한다 (Unity 패키지가 바뀌었으면 Unity 재빌드).
  `--check` = 비교만, `--sdk <경로>` 또는 환경변수 `BTQA_SDK` = SDK 레포 위치 (기본: 이 저장소 안 `btqa_sdk/`, `.gitignore` 로 제외됨).
- 설치는 필요 없다. `btqa_game/` 이 저장소 루트에 있어서 그대로 import 된다 (`requirements.txt` 에 SDK 없음, 게임 서버 프로세스도 `PYTHONPATH` = 저장소 루트).
- `balance_qa`·`play_agent`(학습 쪽)는 사본도 import 하지 않는다. 계약 문서만 따른다 (`tests/test_independence.py`).

## 검사

| 테스트 | 내용 | SDK 레포 없을 때 |
|---|---|---|
| `tests/sdk/test_sdk_copies.py` | `btqa_game` 이 저장소 사본에서 로드되는지 (설치본이 끼어들지 않게), game_sim·Unity 가 사본을 쓰는지, 외부 경로 참조 없는지, 버전 일치 | 실행 |
| 〃 `SdkCopiesMatchOriginalTest` | 사본 == 원본 (바이트 단위) | **건너뜀** |
| `tests/test_independence.py::test_game_sdk_is_standalone` | 사본이 이 저장소의 다른 패키지를 import 하지 않음 | 실행 |

2026-11-23 확인: SDK 레포 폴더를 숨긴 상태에서 메인 테스트 106개(1개 건너뜀) 통과, Unity compilecheck·빌드·check-game 16/16·edge 37/37·check-play 106/106.

## SDK 를 고칠 때

이 저장소에는 SDK 원본이 없다 (2026-11-23 폴더 삭제, `.gitignore` 에 `btqa_sdk/` 는 남겨 둠). 고칠 일이 생기면:

```bash
git clone https://github.com/jk96491/btqa_sdk.git btqa_sdk      # 이 저장소 안에 clone (메인 저장소는 무시)
# btqa_sdk 에서 수정 → SDK 테스트: cd btqa_sdk && ..\venv\Scripts\python.exe -m unittest discover -s tests -t .
venv\Scripts\python.exe run/run_sync_sdk.py                    # 사본 3개 갱신 (Unity 패키지가 바뀌었으면 Unity 재빌드)
# SDK 레포에 커밋·push, 이 저장소에 사본 변경 커밋
```

다른 곳에 clone 했으면 `run/run_sync_sdk.py --sdk <경로>` 또는 환경변수 `BTQA_SDK`.
