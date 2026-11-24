# 증류: Claude(교사) → 작은 로컬 LLM(학생) — 플레이 모드 비전투

> 사용자 결정 2026-11-24: 작은 로컬 LLM 이 플레이, **학습은 GPU 가능 / 플레이는 CPU 추론**, 교사(Claude Code 세션)의 판단을 데이터로 남겨 **LoRA(PEFT) 로 증류**. 포트폴리오용 (경쟁 모델 아님 — 사용자 판단).
> 게임 진행에는 **지금 퀘스트 정보만 중요** → 학생은 대화 기록 없이 "지금 관찰 + 직전 행동 결과 → 다음 행동 1개".
> 이 PC: CPU 16스레드, GPU RTX 3060 12GB.

## 1. 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | SDK 단계 형식·JSON 행동 백엔드·기록기·근거 검사·관찰 축약 + 평가(`batch`)·데이터셋(`dataset`) (`btqa_play` 0.4.0), 학습·내보내기 선택 패키지 `btqa_distill` (SDK 가이드 `btqa_sdk/docs/DISTILL_SDK.md`) | **완료** (2026-11-24) |
| 1b | 원본 소형 모델 기준선 (CPU) | **완료**: `qwen2.5-1.5b-cpu` seed 1~3 → 퀘스트 **0/5**, 형식 오류 0%, 호출당 4.2s, 입력 약 2.3천 토큰. 실패 양상: 퀘스트 무시하고 상인 대화창이 열린 채 `talk` 반복 (`blocked_by_modal` 20회+) → `no_progress` (`reports/distill/batch-20261124-212823`) |
| 2 | 교사 데이터: relay `--record` 로 튜토리얼 20~30판 (직업·seed 바꿔서) | 할 일 |
| 2b | 게임 쪽: 시야 밖 퀘스트 대상 위치 (`unity_game/OFFSCREEN_TARGET_REQUEST.md`) | Unity 요청 (사용자 전달) |
| 3 | 학습 환경 `venv_distill` (Python 3.12 + CUDA torch, GPU) + llama.cpp → `python -m btqa_distill train/merge/gguf/ollama` | 코드 완료(SDK), 환경 설치 할 일 |
| 4 | 교정 데이터(학생이 플레이·교사가 틀린 곳만 정답) + 재학습 + 비교표 | 할 일 |

**모델 파일(원본·증류)은 절대 커밋하지 않는다** — 두 레포 `.gitignore`·`tests/test_no_model_files.py`·pre-commit hook. 학습 출력은 `distill_out/`.

## 2. 모델 (어디서 받나)

| 용도 | 어디서 | 이름 |
|---|---|---|
| **플레이 (CPU 추론)** | [Ollama](https://ollama.com/download) 설치 → `ollama pull <이름>` (기본 태그 = Instruct, 4bit Q4_K_M) | `qwen2.5:1.5b` (주력, 약 1GB) · `qwen2.5:0.5b` (도전) · `qwen2.5:3b` (비교) |
| **학습 (GPU, LoRA)** | Hugging Face (safetensors) | `Qwen/Qwen2.5-1.5B-Instruct` · `Qwen/Qwen2.5-0.5B-Instruct` · `Qwen/Qwen2.5-3B-Instruct` |
| 직접 GGUF (llama.cpp) | Hugging Face 공식 GGUF | `Qwen/Qwen2.5-1.5B-Instruct-GGUF` 등 |

- **학습한 모델과 실행할 모델은 같은 계열**이어야 한다: HF `Qwen2.5-1.5B-Instruct` 에 LoRA → 합쳐서 GGUF(Q4_K_M) → Ollama `Modelfile` 로 등록. (Ollama `ADAPTER` 로 어댑터만 붙이는 것도 가능하지만, 작은 모델은 합친 뒤 양자화하는 편이 안전)
- **평가는 실제로 돌릴 양자화 모델(Q4)로** 한다.
- 라이선스: Qwen2.5 **0.5B·1.5B = Apache 2.0**, **3B = Qwen Research License (비상업)** — 포트폴리오 공개 전 각 모델 카드 확인.

## 3. 지금 쓸 수 있는 명령

```bash
# (Ollama 설치 후) 원본 소형 모델 기준선 — 게임: QaArena.exe -batchmode -nographics -qaPlay -qaPort 7801
ollama pull qwen2.5:1.5b
venv\Scripts\python.exe -m btqa_distill cpu-variant --base qwen2.5:1.5b --name qwen2.5-1.5b-cpu   # Ollama 는 GPU 를 자동으로 쓴다 → CPU 전용 변형 (num_gpu 0)
venv\Scripts\python.exe -m play_agent batch --game 127.0.0.1:7801 --seeds 1-5 --loadout reports/20261123-230419 ^
    --llm openai --model qwen2.5-1.5b-cpu --tool-mode json --stateless --record --max-actions 60 --out reports/distill

# 학습 데이터 (교사 기록 → train/val)
venv\Scripts\python.exe -m btqa_play dataset reports/distill/teacher*.jsonl --out distill_out/data/v1
#   → reports/batch-<시각>/summary.json (전부 완료율·퀘스트 평균·형식 오류율·호출당 시간·입력 토큰) + steps.jsonl

# 교사 데이터 (이 Claude Code 세션이 플레이, API 없음)
venv\Scripts\python.exe -m play_agent relay --game 127.0.0.1:7800 --loadout reports/20261123-230419 --record reports/distill/teacher.jsonl
venv\Scripts\python.exe -m play_agent step intro              # system + 첫 step_input
venv\Scripts\python.exe -m play_agent step move_to "{\"target\":\"npc_elder\",\"pos\":null}" --think "..."   # 응답 = 다음 step_input
```

교사 규칙: **응답의 `step_input`(학생이 받는 입력 그대로)만 보고** 판단한다. 대화 기억으로 정한 행동은 학생이 배울 수 없다 — 기록의 `grounding` 이 그런 샘플을 표시한다 (입력에 없는 id, 근거 없는 좌표).

### 화면으로 보기

`venv\Scripts\python.exe run/run_play_local.py` (PyCharm `16`): Unity 창 + 콘솔에 단계마다 `호출 시간 · 도구 · 인자 → 결과` 와 LLM 생각. `MODEL` 에 Ollama 모델 이름 (증류 모델도 같은 방식). 첫 호출은 모델 적재로 15초 남짓, 이후 호출당 6~9초 (CPU, 1.5B).

## 4. 데이터 형식 (`btqa-play-step/1`, `btqa_sdk/python/btqa_play/record.py`)

```json
{"format":"btqa-play-step/1","run":"relay-…-s1","step":3,"source":"teacher","model":"claude-code",
 "messages":[{"role":"system","content":"…규칙·목표·도구·출력 형식…"},{"role":"user","content":"{\"last_action\":…,\"observation\":…}"}],
 "target":{"thought":"…","tool":"ui_click","input":{"ui_id":"ui.dialog.choice.0"}},
 "target_text":"{\"thought\":\"…\",\"tool\":\"ui_click\",\"input\":{…}}",
 "result":{"tool":"ui_click","status":"done"},"usage":{},"latency_s":null,"grounding":[]}
```

- 학습 샘플 = `messages` + assistant `target_text`. 걸러낼 것: `grounding` 비어 있지 않음, `result.error`(형식 오류), 중복(같은 user → 같은 target).
- system 은 판 내내 같다 (CPU 앞부분 캐시). 한 단계 user 는 0.8.3 기준 약 1.1~1.7천 자.

## 5. 측정 (포트폴리오 표)

교사(Claude) / 원본 0.5B·1.5B·3B / LoRA 0.5B·1.5B·3B × seed N개:
전부 완료율, 퀘스트 평균, 행동 수, 형식 오류율, 근거 없는 행동 수, 호출당 시간(CPU), 입력 토큰.
`play_agent batch` 의 `summary.json` 이 이 열들을 낸다.

## 6. 실험 기록 (밤새 반복, 2026-11-24~25)

평가 = `play_agent batch` 전사·늑대왕 로드아웃 seed 1~3, 판당 최대 70행동, CPU(Ollama Q4_K_M). 학습 = RTX 3060, Qwen2.5-1.5B-Instruct + LoRA r16.

| 회차 | 학습 | 데이터 | 결과 (퀘스트 평균 / 5) | 막힌 곳·진단 |
|---|---|---|---|---|
| 원본 | — | — | **0.0** (형식 오류 0%, 호출당 4.2s) | 퀘스트 무시, 상인 대화창 열린 채 talk 반복 |
| r1 | SFT(BC) 3 epoch, val 0.45→0.40 | 교사 7판 251 | **1.0** (6.3s) | 숲에 들어가자마자 "3개 채집했다"고 지어내고 마을로 — 진행도(0/3)를 안 읽음 |
| r2 | SFT 5 epoch (best ep3 val 0.18) | + thought 앞에 **상황 읽기**("상황: forest · 약초 0/3 · 창 없음 →") | **1.0** (7.5s) | 약초 3개는 정확히 모음. 반납 대상(촌장)이 **다른 지역**인데 그 id 로 가려다 실패 → 퀘스트 창 반복 |
| DAgger 1 | — | r2 학생, seed 21: 48단계 중 학생 정답 40 (83%), 교정 8 | — | 교정: 다른 지역 반납 대상(3), 닫힌 대화창 버튼, 상점 1/2 에서 닫기, 마을 진입 직후 퀘스트 창 |
| r3 | SFT 3 epoch | 교사 7판 + DAgger 1 (교정 3배), 상황에 **"대상 보임/이 지역에 없음"** 추가 (`distill_out/data/v5`, config `distill_out/r3/config.json`) | **중단** — 시작 직후 PC 메모리 부족으로 Claude Code 가 백그라운드 작업을 강제 종료 (Ollama 모델·헤드리스 게임·브라우저 등과 겹침, Windows 는 GPU 메모리가 차면 시스템 RAM 으로 넘침). 사용자 확인 후 재시작 | |

**재개 방법 (2026-11-25 새벽 중단 지점)**: Ollama 모델 내리고(`ollama stop <모델>`) 게임 끈 상태에서
`venv_distill\Scripts\python.exe -m btqa_distill train --config distill_out/r3/config.json --train distill_out/data/v5/train.jsonl --val distill_out/data/v5/val.jsonl`
→ merge·gguf·ollama(`qa-qwen1.5b-r3`) → batch seed 1~3. 그다음 DPO 쌍 `distill_out/data/pairs_v1.jsonl`(8쌍, 더 모을 것) → `btqa_distill.dpo` (r4), RFT `python -m play_agent.distill_run rft` (r5, 게임 2개 7801·7802).
