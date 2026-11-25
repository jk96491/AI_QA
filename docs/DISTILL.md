# 증류: Claude(교사) → 작은 로컬 LLM(학생) — 플레이 모드 비전투

> 사용자 결정 2026-11-24: 작은 로컬 LLM 이 플레이, **학습은 GPU 가능 / 플레이는 CPU 추론**, 교사(Claude Code 세션)의 판단을 데이터로 남겨 **LoRA(PEFT) 로 증류**. 포트폴리오용 (경쟁 모델 아님 — 사용자 판단).
> 게임 진행에는 **지금 퀘스트 정보만 중요** → 학생은 대화 기록 없이 "지금 관찰 + 직전 행동 결과 → 다음 행동 1개".
> 이 PC: CPU 16스레드, GPU RTX 3060 12GB.

## 1. 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | SDK 단계 형식·JSON 행동 백엔드·기록기·근거 검사·관찰 축약 + 평가(`batch`)·데이터셋(`dataset`) (`btqa_play` 0.4.0), 학습·내보내기 선택 패키지 `btqa_distill` (SDK 가이드 `btqa_sdk/docs/DISTILL_SDK.md`) | **완료** (2026-11-24) |
| 1b | 원본 소형 모델 기준선 (CPU) | **완료**: `qwen2.5-1.5b-cpu` seed 1~3 → 퀘스트 **0/5**, 형식 오류 0%, 호출당 4.2s, 입력 약 2.3천 토큰. 실패 양상: 퀘스트 무시하고 상인 대화창이 열린 채 `talk` 반복 (`blocked_by_modal` 20회+) → `no_progress` (`reports/distill/batch-20261124-212823`) |
| 2 | 교사 데이터: relay `--record` 로 튜토리얼 7판 | **완료** (`distill_data/raw/teacher.jsonl`) |
| 2b | 게임 쪽: 시야 밖 퀘스트 대상 위치 (`unity_game/OFFSCREEN_TARGET_REQUEST.md`) | Unity 요청 (사용자 전달) |
| 3 | 학습 환경 `venv_distill` (Python 3.12 + CUDA torch, GPU) + llama.cpp → `python -m btqa_distill train/export` | **완료** |
| 4 | 교정 데이터(DAgger 1~4) + 재학습 + 비교표 (6·7장) | **완료** — 최종 r8 (CPU 5/5) |

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

**증류 한 바퀴 (SDK 명령 + QaArena 함수 이름)** — SDK 는 게임 내용을 모르고, `play_agent` 는 torch·`btqa_distill` 을 import 하지 않는다 (`tests/test_independence.py`).
게임 고유 처리(상황 읽기 전처리 `play_agent.distill_prep`, RFT 보상·판 준비 `play_agent.distill_reward`)는 `'모듈:함수'` 이름으로만 넘긴다.

```bash
# DAgger: 학생이 플레이하고 교사(이 세션)가 정답을 단다 — 게임 7801 (헤드리스)
venv\Scripts\python.exe -m play_agent relay --game 127.0.0.1:7801 --loadout reports/20261123-230419 --seed 1 --port 7898 ^
    --record reports/distill/dagger5.jsonl --student qa-qwen1.5b-r8
venv\Scripts\python.exe -m btqa_play step view --port 7898      # 학생 제안 + 다음 단계 입력
venv\Scripts\python.exe -m btqa_play approve 1 --port 7898      # 학생 제안이 맞으면 승인 (1~2개씩 — 몰아서 승인하면 틀린 행동을 놓친다)
venv\Scripts\python.exe -m btqa_play step move_to "{\"target\":\"herb_02\"}" --think "약초 1/3 — 아직 남았다" --port 7898   # 틀리면 교사 정답

# 데이터셋: 교정 3배 + 상황 읽기 전처리, 검증 = 교사 판 s5 고정
venv\Scripts\python.exe -m btqa_play dataset reports/distill/teacher.jsonl reports/distill/dagger*.jsonl --out distill_out/data/v12 ^
    --val-runs 215705-s5 --correction-weight 3 --prep play_agent.distill_prep:prep_sample
# 학습 → 내보내기 (CPU 전용 + GPU 변형)
venv_distill\Scripts\python.exe -m btqa_distill train --config distill_out/r13/config.json --train distill_out/data/v12/train.jsonl --val distill_out/data/v12/val.jsonl
venv_distill\Scripts\python.exe -m btqa_distill export --base Qwen/Qwen2.5-1.5B-Instruct --adapter distill_out/r13/adapter --out-dir distill_out/r13 ^
    --llama-cpp distill/llama.cpp --name qa-qwen1.5b-r13 --template-from qwen2.5:1.5b --gpu-name qa-qwen1.5b-r13-gpu
# 평가 (CPU·GPU 따로 — 같은 가중치라도 결과가 다를 수 있다, 6장 r8 GPU)
venv\Scripts\python.exe -m play_agent batch --game 127.0.0.1:7801 --seeds 1-5 --loadout reports/20261123-230419 ^
    --llm openai --model qa-qwen1.5b-r13 --tool-mode json --stateless --record --max-actions 70 --out reports/distill
# DPO 쌍 · DPO · RFT (6장: 이 규모에서는 모두 후퇴)
venv\Scripts\python.exe -m btqa_play pairs reports/distill/dagger*.jsonl --out distill_out/data/pairs.jsonl --prep play_agent.distill_prep:prep_pair
venv_distill\Scripts\python.exe -m btqa_distill dpo --base distill_out/r8/merged --pairs distill_out/data/pairs.jsonl --out distill_out/r9
venv_distill\Scripts\python.exe -m btqa_distill rft --base distill_out/r8/merged --game 127.0.0.1:7801 --scratch 127.0.0.1:7802 --seeds 11 ^
    --reward play_agent.distill_reward:reward --prepare play_agent.distill_reward:prepare --spec play_agent/specs/qa_arena.play.json --out distill_out/r10
```

- `dataset --correction-weight` 는 **교정 단계 기록 자체**(학생 제안 ≠ 정답, 또는 `edited`)를 N 번 넣는다. r3~r12 는 이전의 손 스크립트로 만들었는데, 그건 교정 단계와 **입력 글이 같은 다른 샘플**까지 늘렸다 (v11: 손 스크립트 550 ↔ SDK 442, val 은 같음). 그 회차 재현은 `distill_data/datasets/` 사본으로.
- 교사가 학생 제안을 잘못 승인했으면 기록에서 그 줄의 `target`·`target_text` 를 고치고 `"edited": "<이유>"` 를 단다 (교정으로 센다).

교사 규칙: **응답의 `step_input`(학생이 받는 입력 그대로)만 보고** 판단한다. 대화 기억으로 정한 행동은 학생이 배울 수 없다 — 기록의 `grounding` 이 그런 샘플을 표시한다 (입력에 없는 id, 근거 없는 좌표).

### 화면으로 보기

`venv\Scripts\python.exe run/run_play_local.py` (PyCharm `16`): Unity 창 + 콘솔에 단계마다 `호출 시간 · 도구 · 인자 → 결과` 와 LLM 생각. `MODEL` 에 Ollama 모델 이름 (증류 모델도 같은 방식). 첫 호출은 모델 적재로 15초 남짓, 이후 호출당 6~9초 (CPU, 1.5B). 끝 줄의 장치(CPU/GPU)는 Ollama 가 실제로 올린 곳.

**녹화**: `venv\Scripts\python.exe run/run_record_play.py --model qa-qwen1.5b-r8` (PyCharm `17`, Windows) → `reports/recordings/<모델>_seed1.mp4` (원본 속도 1280×720) · `_skip.mp4` (LLM 응답 대기를 뺀 것 — 이 게임은 행동할 때만 세계가 흘러 대기 중 화면이 멈춰 있다 → 같은 프레임 제거) · `.gif` (대기 제거본 2배속, 폭 640). 게임 창 영역을 화면에서 복사하므로 녹화 중 게임 창이 맨 위에 고정된다. ffmpeg 는 `FFMPEG` 환경변수 → PATH → imageio-ffmpeg 순서. r8 CPU seed 1: 8분 26초 → 대기 제거 1분 37초.

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
| r3 | SFT 3 epoch (val 0.199→0.178→**0.165**, 52분) | 교사 7판 + DAgger 1 (교정 3배), 상황에 **"대상 보임/이 지역에 없음"** 추가 (`v5`) | **2.0** (형식 오류 0%, 7.7s) — 세 seed 모두 같음 | 퀘스트 1·2 완벽 (다른 지역 반납도 포털 경유로 해결). 퀘스트 3 "인벤토리에서 물약을 퀵슬롯에 등록"(목표 대상 hint 없음)에서 인벤토리 버튼 대신 대화 choice.0 → 촌장 대화 반복 |
| DAgger 2 | — | r3 학생, seed 22·23: 82단계 중 학생 정답 76 (**93%**), 교정 6 | — | 교정: 퀘스트 3 인벤토리 열기(정상 상태·실패 직후 4), 사거리 밖 약초 줍기(2). **그 두 곳만 고쳐 주면 학생이 늑대왕 처치까지 5개 완주** (교사 실행은 교정 단계뿐) |
| r4 | SFT 3 epoch | 교사 7판 + DAgger 1·2 (교정 11개 3배, train 357), **val = 교사 판 s5 고정** (`--val-runs`, 교정 판이 검증으로 빠지지 않게) (`v6`). 학습 loss 를 **답 구간 logits 만**(`logits_to_keep`)으로 바꿔 GPU 메모리 넘침 해소 (10스텝 1330s → 226s) | **2.0** (7.4s), val 0.170 | 여전히 퀘스트 3: 이번엔 대화 choice.0 대신 촌장 talk 반복. 교정 12개(3배)로는 "창 없음 + 직전 대화 → 대화" 습관을 못 이김 → 입력에 목표 글과 버튼을 잇는 단서가 없다 |
| r5 | SFT 3 epoch | v7 = v6 + 상황에 **"목표 글 '인벤토리' = 버튼 ui.hud.inventory"** (대상 표시 없는 목표에서, 목표 글에 들어 있는 버튼 글 → 그 버튼 id, 입력에서 그대로 옮김) | **3.0** (7.7s), val 0.169 | 퀘스트 3 통과 ("목표 글 '인벤토리' = 버튼 ui.hud.inventory → 인벤토리를 연다"). 퀘스트 4: 멀리 있는 상인(12.6m)에게 move_to 없이 talk → out_of_range → 인벤토리 열고 닫기 반복 |
| r6 | SFT 3 epoch | v8 = v7 + 상황의 보이는 대상에 **거리** ("npc_merchant(멂 12.6)" / "(가까움 2.1)", 입력 `entities[].distance`, 기준 3.0 = move_to 뒤 2.1~2.3) | **3.0** (seed 1, 7.2s), val 0.159 | 상황은 "npc_merchant(멂 12.6)" 으로 맞게 읽음. 인벤토리를 닫은 직후 없는 버튼 `ui.inventory.open` 을 지어내 반복 — 이 전환(인벤토리 닫음 → 상인) 장면이 데이터에 적다 (같은 seed 는 같은 결과라 seed 2·3 생략) |
| DAgger 3 | — | r6 학생, seed 24: 42단계, 교정 5 | — | 인벤토리 닫은 뒤 상인에게 move_to (정상·실패 직후), 두 번째 물약 구매 (학생은 상인에게 다시 가려 함), 숲 입구 move_to (대상 없는 move_to·사거리 밖 입장 — 교사가 잘못 승인한 2개는 `edited` 로 수정) |
| r7 | SFT 3 epoch (val 0.225→0.168→0.173) | v9 = v8 + DAgger 3 (교정 15개 3배, train 414) | **2.0** (seed 1, 7.0s) — 후퇴 | 퀘스트 3 인벤토리 창에서 생각은 "퀵슬롯 등록"인데 행동은 직전 버튼(물약 칸) 반복. 작은 모델은 재학습마다 막히는 곳이 바뀐다 (데이터 조금 바꾸면 다른 장면이 흔들림) |
| r8 | SFT 3 epoch | v10 = v9 + 상황의 **창 버튼 글=id** ("창 inventory [(선택) 작은 물약 x2=ui.inventory.slot.potion_small, 퀵슬롯 1에 등록=ui.inventory.assign, 닫기=…]") — 생각한 글을 id 로 옮겨 적게 (val 0.205→0.157→**0.156**) | **5.0 — seed 1·2·3 모두 완주** (행동 41·43·43, 형식 오류 0%, 호출당 8.4s CPU) | 촌장 → 약초 3개 → 반납 → 인벤토리에서 물약 등록 → 상인 2개 구매 → 숲 늑대왕(전투는 학습 BT) → 경비병 보고 → finish. **SFT(BC) + DAgger 3회 + 상황 읽기 단서 4종**으로 도달 |
| r9a | **DPO** (r8 위, 쌍 18개 `pairs_v5`, β 0.1, lr 3e-5, 3 epoch, 5분) | DAgger 1~3 교정 (chosen=교사, rejected=학생, 상황 접두 같은 형식) | **1.0** — 붕괴 | 선호 정확도 0.72→1.0, 손실 0.64→0.12 인데 플레이는 망가짐: 퀘스트 1 뒤 "모든 퀘스트를 완료했다" finish, 생각에 중국어(完成了) 섞임. 쌍 18개로 기준에서 너무 멀리 끌려감 (과최적화) |
| r9 | DPO 약하게 (lr 5e-6, β 0.3, 1 epoch) | 같은 쌍 | **1.0** (seed 1) | 손실 0.692 (거의 그대로) 인데도 숲 진입 직후 "목표 완료"로 잘못 읽고 마을로 → 약초 뒤 막힘. 1.5B 탐욕 디코딩은 갈림길이 아슬아슬해 작은 가중치 변화에도 뒤집힌다. **결론: 이 규모(쌍 18개)에서 DPO 는 득보다 실 — r8(SFT+DAgger) 유지** |
| r10 | **RFT (GRPO)** r8 위, seed 11 한 판 39단계 (K=4 샘플+greedy, lr 1e-5, KL 0.05, 40분) | 게임 = 채점기 (`play_agent/distill_reward.py`), 분기 = scratch 게임 reset(seed)+prefix 재생 (37행동 재생 2.2s) | **3.0** (seed 1~3) | 39단계 중 점수가 갈린 8단계만 갱신 (학생이 이미 대부분 맞힘). **보상 해킹**: "창 열린 채 ui_click 성공 +0.2" 규칙 → 이미 등록한 물약의 '퀵슬롯 등록'을 반복(매번 성공) 해 점수를 모음 → 인벤토리에서 등록 반복으로 퇴화. 보상을 "창이 실제로 바뀐 클릭만"으로 수정 |
| r11 | RFT (보상 수정) r8 위, 같은 설정 (39단계, 갱신 8, 39분) | 〃 | **0.0** (seed 1~3) — 붕괴 | 둘째 행동부터 퀘스트 창 열기·중국어 섞인 생각·0개로 finish. lr 1e-5·8회 갱신으로도 무너짐 → DPO 와 같은 현상: SFT 를 마친 1.5B 는 탐욕 디코딩 갈림길이 아슬아슬해 작은 정책 변화에도 뒤집힌다. 한 판(39단계)의 신호로는 부족 — 여러 seed·더 낮은 lr·더 큰 KL·SFT 손실 섞기가 필요 (다음 과제) |
| r8 GPU | — (r8 가중치 그대로, Ollama `num_gpu 99` 변형) | — | **1.0** (seed 1·2, 호출당 3.0s) | CPU 와 10단계까지 같다가 11단계에서 갈림: 9단계에 약초 1/3 을 "목표 완료"로 잘못 옮겨 적고 마을 입구로 간 뒤, CPU 는 "약초가 멀다"를 읽고 복구했지만 GPU 는 다시 입구로 → (입구 이동 ↔ 먼 약초 줍기 실패) 반복. GPU·CPU 연산 차이로 탐욕 디코딩 갈림길이 뒤집힘 — **r8 의 5/5 는 CPU 에서의 결과** |
| DAgger 4 | — | **r8 GPU 학생**, seed 1 (48단계) + seed 2 (41단계, 9단계 실수를 일부러 통과시켜 복구 상태 수집). 교정 28 (교사가 몰아 승인한 9개는 `edited`: 먼 촌장 talk 5, 상인 앞 인벤토리 3, 약초 1/3 에서 입구 1) | — | 약초 1/3 착각, 먼 NPC talk, 등록 반복, 상인 앞 인벤토리, 숲 진입 직후 퀘스트 창, 멀리서 포털 입장 |
| r12 | SFT 3 epoch (val 0.174→**0.148**→0.150, 85분) | v11 = v10 + DAgger 4 (교정 3배, train 550) | **GPU 3.0** (seed 1~5 모두, 호출당 2.9s) · CPU 미평가 | GPU 에서 퀘스트 1~3 통과 (r8 GPU 1.0 → 3.0). 퀘스트 4: 상인 앞(2.1)에서 생각은 "상인이 가깝다"인데 행동은 인벤토리 열기 → 닫힌 인벤토리 '닫기' 반복, 생각에 중국어. 고친 상인 장면 라벨(3배)과 기존 "인벤토리 열기/닫기" 라벨이 비슷한 입력에서 섞인 것으로 보임 (충돌 입력 4). **최종 모델은 r8 (CPU) 유지** |

**메모리**: 학습 중에는 Ollama 모델·게임을 내린다 (1.5B·4천 토큰 샘플에서 3060 12GB 가 차고 시스템 RAM 으로 넘친다 — 2026-11-25 새벽 r3 첫 시도가 PC 메모리 부족으로 강제 종료됨).
회차 번호: r4 = SFT(DAgger 2 반영), r5 = DPO (r4 위, 쌍 `pairs_v2.jsonl` 13개), r6 = RFT.

**데이터 백업 (커밋됨)**: 교사·DAgger 1~4 기록과 데이터셋 v0~v11·DPO 쌍 사본 = `distill_data/` (README). 새 데이터를 만들면 거기에도 복사한다. 모델은 커밋하지 않는다.

## 7. 결과 요약 (2026-11-25, 포트폴리오용)

**Qwen2.5-1.5B (Q4_K_M, CPU 추론 호출당 ~8s) 가 튜토리얼 퀘스트 5개를 seed 1~5 모두 완주** — 최종 모델 `qa-qwen1.5b-r8`.

| 단계 | 모델 | 퀘스트 (/5) | 한 일 |
|---|---|---|---|
| 원본 | qwen2.5-1.5b | 0.0 | 퀘스트 무시, 대화창 반복 |
| SFT (BC) | r1 | 1.0 | 교사(Claude Code 세션) 7판 모방 — 진행도를 안 읽고 지어냄 |
| + 상황 읽기 | r2 | 1.0 | 생각 앞에 입력에서 옮겨 적는 "상황:" 접두 → 약초 수집 정확 |
| + DAgger 1·2 | r3 → r4 | 2.0 | 학생이 실제로 간 상태에서 교사 라벨 (정답률 83%→93%) |
| + 단서: 목표 글 = 버튼 | r5 | 3.0 | "인벤토리에서 …" → `ui.hud.inventory` |
| + 단서: 거리 | r6 | 3.0 | "(멂 12.6)" → move_to 먼저 |
| + DAgger 3 | r7 | 2.0 | 재학습마다 다른 장면이 흔들림 |
| + 단서: 창 버튼 글=id | **r8** | **5.0 (5/5 seed)** | 생각한 버튼 글을 id 로 옮겨 적기 |
| DPO | r9a / r9 | 1.0 / 1.0 | 쌍 18개 — 강하게는 붕괴, 약하게도 갈림길이 뒤집힘 (실패 사례) |
| RFT (GRPO) | r10 | 3.0 | 게임 = 채점기, 같은 상태 분기(seed+prefix 재생). **보상 해킹**: "창 열린 채 ui_click 성공 +0.2" → 이미 등록한 물약의 '등록'을 반복(매번 성공) |
| RFT (보상 수정) | r11 | 0.0 | ui_click 은 창이 실제로 바뀔 때만 +0.2 — 해킹은 막았지만 한 판 신호로 정책이 무너짐 |
| r8 을 GPU 로 | r8-gpu | 1.0 | 같은 가중치, 추론 장치만 바꿈 — 갈림길이 뒤집혀 반복 |
| + DAgger 4 (GPU 학생) | r12-gpu | 3.0 | GPU 에서 나아졌지만 상인 장면에서 새로 막힘 |

**배운 것**
- 작은 모델에게 가장 효과가 컸던 것은 데이터 양이 아니라 **"입력에서 옮겨 적기만 하면 되는" 상황 읽기 단서** (진행도·대상 보임/없음·거리·목표 글=버튼·창 버튼 글=id). 판단을 복사 문제로 바꾼다. 단서는 입력에 있는 값만 쓴다 (교사가 학생이 못 보는 정보를 쓰지 않음).
- **DAgger** 는 막히는 장면을 정확히 찾아 준다 (교사 실행은 교정 단계뿐, 학생이 93~95% 스스로). 다만 교정 몇 개(3배 가중)로는 강한 습관을 못 이길 때가 있어 단서와 같이 써야 했다.
- **DPO** 는 이 규모(쌍 18개)에서 득보다 실 — 선호 정확도 1.0 이 플레이 품질을 뜻하지 않는다.
- **SFT 이후 단계(DPO·RFT)는 이 규모에서 모두 후퇴** — 최종 모델은 SFT+DAgger 의 r8. 작은 모델의 "잘 되는 상태"는 좁아서, 추가 최적화는 많은 데이터·강한 정규화(KL·SFT 손실 혼합)·여러 seed 평가와 함께 해야 한다.
- **RFT** 는 보상이 곧 목표가 된다 — "창 안 클릭 성공"에 준 작은 보상(+0.2)을 학생이 반복 클릭으로 모았다 (보상 해킹). 진척과 무관한 성공에 보상을 주지 말 것. 또 이미 잘하는 학생은 후보 점수가 거의 같아 갱신할 단계가 적다 (39단계 중 8).
- **추론 장치도 평가 조건이다** — 같은 r8 가중치가 CPU 5/5, GPU 1/5. 탐욕 디코딩이라도 연산 순서·정밀도 차이로 점수가 거의 같은 갈림길이 뒤집힌다. 작은 모델은 실제로 돌릴 장치·양자화로 평가하고, 어긋나면 그 장치의 학생으로 DAgger 를 돌린다.
- 학습 쪽: 3060 12GB 에서 전체 logits 가 GPU 메모리를 넘겨 시스템 RAM 으로 넘침 → 답 구간만 logits (`logits_to_keep`) 로 10스텝 1330s→226s.

**재생**: `venv\Scripts\python.exe run/run_play_local.py` (PyCharm 16, `MODEL = "qa-qwen1.5b-r8"`). 녹화 `run/run_record_play.py` (PyCharm 17). 데이터 백업 `distill_data/` (커밋 대상), 모델은 `distill_out/` 와 Ollama 에만 (커밋 금지).
