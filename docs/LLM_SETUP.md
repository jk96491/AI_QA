# LLM 연결 안내 — 플레이 모드는 각자 자기 LLM 을 쓴다

플레이 모드(`docs/PLAY_PROTOCOL.md`)에서 **비전투(이동·대화·퀘스트·UI)는 LLM 이**, 전투는 학습된 BT 가 한다.
이 저장소는 특정 LLM 이나 키를 들고 있지 않다. **쓰는 사람이 자기 LLM 을 골라 연결한다.**

## 1. 어떤 방법을 고를까

| 방법 | 비용 | 준비 | 자동 반복 | 이럴 때 |
|---|---|---|---|---|
| **A. 대화형 에이전트가 직접 플레이** (`relay`) | 쓰고 있는 구독(Claude Code 등) 한도 안 — **추가 과금 없음** | 없음 | ✗ (사람이 세션을 보고 있어야 함) | 한두 번 직접 따라가며 보고 싶을 때. 2026-11-23 첫 플레이가 이 방식 |
| **B. 로컬 LLM** (`--llm openai`) | 무료 (내 PC GPU·전기) | Ollama / LM Studio 설치 + 모델 받기 | ✓ | 키·과금 없이 여러 번 자동으로 |
| **C. Claude API** (`--llm anthropic`) | 종량제 (구독과 **별도 결제**) | console.anthropic.com 키, Python ≥ 3.10 venv | ✓ | 판단 품질이 가장 중요할 때 |
| **D. 다른 OpenAI 호환 클라우드** (`--llm openai`) | 그 서비스 요금 | 그 서비스 키 | ✓ | OpenAI·OpenRouter 등 이미 쓰는 서비스가 있을 때 |

> Claude 구독(Pro/Max)과 Claude API 는 결제가 따로다. 구독이 있어도 C 는 따로 청구된다.

## 2. 설정 파일 `llm.json` (저장소 루트, git 에 안 올라감)

`btqa_sdk/python/btqa_play/llm.example.json` 을 복사해 `llm.json` 으로 저장하고 고친다. CLI 인자를 주면 파일 값보다 우선한다.

```json
{"llm": "openai", "model": "qwen2.5:14b", "base_url": "http://localhost:11434/v1", "api_key_env": null}
```

| 키 | 뜻 |
|---|---|
| `llm` | `openai`(OpenAI 호환 — 로컬·클라우드) 또는 `anthropic`(Claude API). **필수** — 안 고르면 실행을 거부한다 |
| `model` | 모델 이름. openai 는 필수, anthropic 기본 `claude-opus-5-5` |
| `base_url` | openai 서버 주소. 기본 `http://localhost:11434/v1`(Ollama) |
| `api_key_env` | 키가 든 **환경변수 이름** (예 `OPENAI_API_KEY`). 로컬 서버는 `null` |
| `effort` | anthropic 만: `low`(기본)~`max` |
| `max_tokens`, `temperature`, `timeout`, `extra_body` | 선택. `extra_body` 는 서버 고유 옵션을 요청 본문에 그대로 넣는다 |

**키 규칙**: 키 값은 어디에도 쓰지 않는다 — 파일·CLI 인자·PyCharm 실행 구성(`.idea/runConfigurations` 는 git 에 올라간다) 모두 금지. 환경변수로만 넣는다 (Windows: `setx 이름 "값"` 후 터미널·PyCharm 재시작). `llm.json` 에 `api_key` 같은 키가 있으면 실행을 거부한다.

## 3. 방법별 실행

먼저 게임을 플레이 모드 창으로 띄운다: `unity_game\Build\QaArena.exe -qaPlay -qaPort 7800 -qaPlaySpeed 4`
(PyCharm `14 LLM 플레이 (각자 LLM)` = `run/run_play.py` 는 게임 띄우기까지 같이 한다. 맨 위 설정 블록에서 고른다.)

### A. 대화형 에이전트 (relay)

```bash
venv\Scripts\python.exe -m play_agent relay --game 127.0.0.1:7800 --loadout reports/<run>
# 에이전트가 한 행동씩:
venv\Scripts\python.exe -m play_agent step intro
venv\Scripts\python.exe -m play_agent step move_to "{\"target\":\"npc_elder\"}" --think "촌장에게 먼저 간다" --kind plan
venv\Scripts\python.exe -m play_agent step finish "{\"success\":true,\"summary\":\"...\",\"blocked\":null}"
```
Claude Code 에게는 "relay 를 띄우고 step 으로 튜토리얼을 플레이해" 라고 하면 된다. PowerShell 은 JSON 따옴표를 망가뜨리기 쉬워 Bash 로 부르는 게 낫다.

### B. 로컬 LLM

> 작은 모델(0.5B~3B)을 CPU 로: `--tool-mode json --stateless` (출력 JSON 강제 + 단계마다 새 대화). 증류 계획 `docs/DISTILL.md`.

1. 서버 설치: [Ollama](https://ollama.com) (기본 `http://localhost:11434/v1`) 또는 LM Studio(서버 켜기, `http://localhost:1234/v1`), llama.cpp `llama-server`, vLLM 도 같은 방식.
2. **도구 호출(function calling)을 지원하는 모델**을 받는다. 예: `ollama pull qwen2.5:14b` (12GB GPU 에 4bit 로 들어가는 크기). 작은 모델일수록 도구 인자를 틀리거나 같은 행동을 반복하기 쉽다 → 진척 없음 상한(`no_progress`)이 멈춘다.
3. 실행 (프로젝트 venv 3.8 그대로, 추가 설치 없음):
   ```bash
   venv\Scripts\python.exe -m play_agent play --game 127.0.0.1:7800 --loadout reports/<run> --llm openai --model qwen2.5:14b --max-actions 40
   ```

### C. Claude API

1. Python ≥ 3.10 venv (지금은 없음 — 2026-11-24 삭제, 쓸 때 만든다): `py -3.12 -m venv venv_play` → `venv_play\Scripts\python.exe -m pip install anthropic numpy` → SDK 편집 설치 `venv_play\Scripts\python.exe -m pip install -e ./btqa_sdk` (btqa_play)
2. 키: console.anthropic.com 에서 발급 → `setx ANTHROPIC_API_KEY "sk-ant-..."` (재시작)
3. `venv_play\Scripts\python.exe -m play_agent play --game 127.0.0.1:7800 --loadout reports/<run> --llm anthropic --effort low --max-actions 40`

### D. OpenAI 호환 클라우드

`setx OPENAI_API_KEY "..."` 후 `--llm openai --base-url https://api.openai.com/v1 --model <모델> --api-key-env OPENAI_API_KEY`. 다른 서비스는 그 서비스의 `/v1` 주소와 키 환경변수.

## 4. 결과

`reports/play-<시각>/run.json` (`llm` = 쓴 백엔드, 행동·판단 기록, 토큰, 전투 요약, `pilot_notes`) + `play_log.json`(게임 로그, 재현용).
LLM 이 도구를 부르기 전에 말한 한 문장은 게임 화면 "QA 플레이어" 패널에 생각으로 표시된다 (play v0.3 게임만, 아니면 `run.json` 에만).

## 5. 새 LLM 백엔드 추가 (개발자)

LLM 백엔드는 SDK `btqa_play` 에 있다 (`btqa_sdk/python/btqa_play/llm/`, 이 저장소는 직접 참조). 거기서 `llm/base.py: LlmBackend` 를 상속해 `start / complete / add_tool_results / add_user` 를 구현하고 `llm/__init__.py: make_backend` 에 이름을 등록한다 (SDK 레포에 커밋).
도구 정의는 중립 형식(`tools.build_tools`)으로 들어오고, 백엔드가 자기 API 형식으로 바꾼다. 테스트는 `tests/play/test_llm.py` 처럼 가짜 전송을 주입해 네트워크 없이.
`play_agent` 는 `balance_qa`·`game_sim`·`torch` 를 import 하지 않는다 (`tests/test_independence.py`).
