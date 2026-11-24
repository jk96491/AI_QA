# 설치 가이드 — AI_QA + BT-QA SDK

이 저장소는 **BT-QA SDK**(별도 레포 [jk96491/btqa_sdk](https://github.com/jk96491/btqa_sdk))를 **직접 참조**한다. SDK 는 이 저장소에 들어 있지 않으므로 받아서 설치해야 `game_sim`·`play_agent`·테스트가 돈다.

| 필요한 것 | 버전 |
|---|---|
| Python | **3.8** (프로젝트 venv `venv\`, 3.10+ 문법 금지) |
| 패키지 | numpy 1.22.4, PyTorch 1.8.1 CPU (`requirements.txt`) |
| BT-QA SDK | **0.4.0** — `btqa_game`(게임 쪽 서버) + `btqa_play`(플레이 모드 LLM 클라이언트). 표준 라이브러리만 |
| git | SDK clone 용 |
| Unity 빌드 | 선택 — 없어도 Python 게임 대역(`game_sim`)으로 전부 돈다 |

## 1. 한 번에 (권장)

```bash
git clone https://github.com/jk96491/AI_QA.git && cd AI_QA
python -m venv venv                                        # Python 3.8
venv\Scripts\python.exe -m pip install -r requirements.txt # numpy + torch CPU
venv\Scripts\python.exe run/run_setup_sdk.py               # SDK clone + 편집 설치 + 확인 (PyCharm ▶ 15)
venv\Scripts\python.exe -m unittest discover -s tests -t . # 전부 OK 면 끝
```

`run/run_setup_sdk.py` 는 여러 번 실행해도 된다. 두 레포에 **모델 파일 커밋 거부 pre-commit hook** 도 설치한다 (원본·증류 모델은 절대 커밋하지 않는다). 마지막에 `[OK]` 4줄 + "완료" 가 나오면 성공:

```
[OK] btqa_game ← ...\AI_QA\btqa_sdk\python
[OK] btqa_play ← ...\AI_QA\btqa_sdk\python
[OK] SDK 0.4.0 (btqa_play 0.4.0), 밸런스 프로토콜 1.4, 플레이 프로토콜 0.3
[OK] Unity 패키지 사본 0.4.0
```

## 2. 직접 하기 (스크립트가 하는 일)

```bash
git clone https://github.com/jk96491/btqa_sdk.git btqa_sdk                       # 반드시 AI_QA 안에 (.gitignore 로 제외됨)
venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e ./btqa_sdk
```

- **편집 설치(`-e`)**: `btqa_sdk/python` 을 venv 가 바로 가리킨다 (venv 의 `easy-install.pth`). SDK 코드를 고치면 복사·재설치 없이 반영된다.
- `--no-build-isolation`: venv 의 setuptools 가 64 미만이라 필요하다 (없으면 빌드 격리 환경에서 실패). pip 가 "legacy editable install" 경고를 내지만 동작한다.
- `--no-deps`: SDK 는 의존성이 없다 (표준 라이브러리만).
- 확인만: `venv\Scripts\python.exe -c "import btqa_game, btqa_play; print(btqa_game.__file__, btqa_game.__version__)"`

## 3. SDK 업데이트

| 상황 | 할 일 |
|---|---|
| SDK 새 버전이 나왔다 | `run/run_setup_sdk.py` 맨 위 `UPDATE = True` 로 실행 (또는 `git -C btqa_sdk pull`). Python 은 편집 설치라 바로 반영 |
| SDK 를 직접 고친다 | `btqa_sdk/` 에서 수정 → SDK 테스트 `cd btqa_sdk && ..\venv\Scripts\python.exe -m unittest discover -s tests -t .` → 메인 테스트 → SDK 레포에 커밋·푸시. 개발 규칙 `docs/SDK.md` |
| Unity 패키지·계약 문서가 바뀌었다 | `venv\Scripts\python.exe run/run_sync_sdk.py` — 사본 3개(`unity_game/Packages/com.btqa.game`, `docs/PROTOCOL.md`, `docs/PLAY_PROTOCOL.md`) 갱신. Unity 패키지가 바뀌었으면 Unity 재빌드 |
| 다른 venv 에서도 쓴다 (예: Claude API 용 `venv_play`) | 그 venv 에도 `<그 venv>\Scripts\python.exe -m pip install -e ./btqa_sdk` |

## 4. PyCharm

- 프로젝트 인터프리터 = `venv\Scripts\python.exe` (`Python 3.8 (AI_QA)`).
- `btqa_sdk/python` 은 **소스 루트**로 지정돼 있다 (`.idea/AI_QA.iml`). 그래서 인터프리터 경로 캐시와 상관없이 `btqa_game`·`btqa_play` import 가 빨간 줄 없이 잡힌다.
- 그래도 빨간 줄이면: 폴더 `btqa_sdk/python` 우클릭 → **Mark Directory as → Sources Root** → 안 되면 **File → Invalidate Caches… → Invalidate and Restart**.
- 실행 구성 `15 SDK 설치·업데이트` = `run/run_setup_sdk.py`.

## 5. 문제 해결

| 증상 | 원인 → 해결 |
|---|---|
| `ModuleNotFoundError: No module named 'btqa_game'` (또는 `btqa_play`) | SDK 미설치 또는 다른 인터프리터로 실행 → `run/run_setup_sdk.py` 를 **그 인터프리터로** 실행 |
| `tests/sdk/test_sdk_copies.py` 실패 "btqa_sdk 가 아닌 곳에서 로드됨" | pip 로 다른 곳의 btqa-game 이 설치돼 있다 → `venv\Scripts\python.exe -m pip uninstall btqa-game` 후 `run/run_setup_sdk.py` |
| 같은 테스트 "루트 btqa_game/ 사본은 두지 않는다" | 예전 방식의 사본 폴더가 남아 있다 (2026-11-24 전) → 루트 `btqa_game/`·`btqa_play/` 삭제 |
| "SDK 원본 없음" / 사본 비교 건너뜀 | `btqa_sdk/` 가 AI_QA 밖에 있다 → AI_QA 안으로 옮기거나 환경변수 `BTQA_SDK=<경로>` (사본 비교용. import 는 편집 설치 경로를 따른다) |
| `[FAIL] Unity 패키지 사본` / 사본 ≠ SDK | SDK 가 갱신됐는데 사본이 옛것 → `run/run_sync_sdk.py` (+ Unity 재빌드) |
| 편집 설치가 빌드 단계에서 실패 | `--no-build-isolation` 을 빼먹었다 (venv setuptools < 64) |
| 게임 서버 하위 프로세스에서만 import 실패 | 하위 프로세스가 다른 Python 으로 떴다 → `--game-cmd` 가 아닌 기본 실행은 같은 venv 를 쓴다. 직접 띄울 땐 `venv\Scripts\python.exe -m game_sim serve` |

## 6. 그다음

- 빠른 시작·명령: `README.md` / `docs/README.ko.md`, 전체 명령 `CLAUDE.md` "명령"
- 플레이 모드 LLM 연결: `docs/LLM_SETUP.md`
- SDK 와 이 저장소의 관계·개발 규칙: `docs/SDK.md`
