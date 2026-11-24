# BT-QA SDK 와 이 저장소

SDK 의 **원본은 별도 GitHub 레포 https://github.com/jk96491/btqa_sdk** 다 (사용자 결정 2026-11-23, 0.1.0 = `5627219`, 0.2.0 = `6c71e4c`, **0.3.0** = `42ab358` 플레이 모드 클라이언트 `btqa_play` 추가, 2026-11-24).
SDK 가이드·변경 이력·자체 테스트는 SDK 레포에 있다 (`README.md`, `docs/SDK.md`, `docs/PLAY_SDK.md`, `CHANGELOG.md`, `tests/`).

## Python = btqa_sdk 직접 참조 (사본 없음, 사용자 결정 2026-11-24)

| 패키지 (btqa_sdk) | 쓰는 곳 |
|---|---|
| `python/btqa_game/` | `game_sim` (서버·세션·정의서 선언·검증). `python -m btqa_game check --game HOST:PORT` |
| `python/btqa_play/` | `play_agent` (플레이 모드 LLM 클라이언트 — 그 위에 로드아웃·전투 응답기). `python -m btqa_play tools --game HOST:PORT` |

설치 (한 번, 이 저장소 안에 clone — `.gitignore` 로 제외됨). 한 번에 하려면 `venv\Scripts\python.exe run/run_setup_sdk.py`, 자세한 안내·문제 해결은 **`docs/INSTALL.md`**:

```bash
git clone https://github.com/jk96491/btqa_sdk.git btqa_sdk
venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e ./btqa_sdk    # 편집 설치 (setuptools < 64 라 --no-build-isolation)
```

- 편집 설치라 `btqa_sdk/python/*` 을 고치면 바로 반영된다 (복사 단계 없음). 게임 서버 하위 프로세스도 같은 venv 라 그대로 import 된다.
- `btqa_sdk` 가 없거나 설치하지 않으면 `game_sim`·`play_agent` 가 import 되지 않는다 (`tests/sdk/test_sdk_copies.py` 가 이유를 알려 줌).
- `balance_qa` 는 어떤 SDK 도 import 하지 않는다. `play_agent` 는 `btqa_play` 만, 게임 쪽 `btqa_game` 은 import 하지 않는다 (`tests/test_independence.py`).

## Python 이 아닌 사본 3개

| 사본 (이 저장소) | 원본 (SDK 레포) | 이유 |
|---|---|---|
| `unity_game/Packages/com.btqa.game/` | `unity/com.btqa.game/` | Unity embedded 패키지 (manifest 항목 없음, lock `source: embedded`) — 빌드가 btqa_sdk 폴더에 의존하지 않게 |
| `docs/PROTOCOL.md` | `docs/PROTOCOL.md` | 밸런스 계약 v1.4 — 이 저장소 문서·코드 주석이 가리키는 곳 |
| `docs/PLAY_PROTOCOL.md` | `docs/PLAY_PROTOCOL.md` | 플레이 계약 v0.3 (+ 선택 필드 4.2.1) |

- **사본은 직접 고치지 않는다.** SDK 레포에서 고친 뒤 `venv\Scripts\python.exe run/run_sync_sdk.py` (Unity 패키지가 바뀌었으면 Unity 재빌드).
  `--check` = 비교만, `--sdk <경로>` 또는 환경변수 `BTQA_SDK` = SDK 레포 위치 (기본: 이 저장소 안 `btqa_sdk/`).

## 검사

| 테스트 | 내용 |
|---|---|
| `tests/sdk/test_sdk_copies.py` | `btqa_game`·`btqa_play` 가 btqa_sdk 에서 로드되는지, 루트에 Python 사본이 없는지, game_sim·play_agent 가 SDK 를 쓰는지, Unity 가 embedded 사본을 쓰는지, 버전 일치, 사본 3개 == 원본 |
| SDK 레포 `tests/` | SDK 자체 (표준 라이브러리만, 게임·학습 코드 import 없음, 예제 게임 적합성, 플레이 클라이언트) |

## SDK 를 고칠 때

```bash
# btqa_sdk/python/... 수정 → 바로 반영 (편집 설치)
cd btqa_sdk && ..\venv\Scripts\python.exe -m unittest discover -s tests -t .    # SDK 테스트
venv\Scripts\python.exe -m unittest discover -s tests -t .                        # 메인 테스트
venv\Scripts\python.exe run/run_sync_sdk.py                                       # Unity 패키지·문서가 바뀌었으면
# SDK 레포에 커밋·push, 이 저장소에는 사본(Unity·문서) 변경만 커밋
```

다른 곳에 clone 했으면 `run/run_sync_sdk.py --sdk <경로>` 또는 환경변수 `BTQA_SDK`.
