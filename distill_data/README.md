# 증류 학습 데이터 백업 (커밋 대상)

모델·어댑터·GGUF 는 **절대 커밋하지 않는다** (`distill_out/`, `.gitignore`). 이 폴더는 그 모델을 만든 **데이터만** 보관한다
(사용자 결정 2026-11-25: 교사 기록은 다시 만들기 어려우므로 백업해 커밋). 작업 원본은 여전히 `reports/distill/`·`distill_out/data/` 이고,
새 데이터를 만들면 여기에도 복사해 둔다.

| 경로 | 내용 | 원본 |
|---|---|---|
| `raw/teacher.jsonl` | 교사(Claude Code 세션) 플레이 기록 7판, `btqa-play-step/1` | `reports/distill/teacher.jsonl` |
| `raw/dagger.jsonl` | DAgger 1판 (r2 학생 실행 + 교사 라벨, `extra.student`) 48단계 | `reports/distill/dagger.jsonl` |
| `datasets/v0`~`v2` | SFT 데이터셋 `btqa-play-sft/1` (교사 판 수 증가) — r1 = v2 | `distill_out/data/` |
| `datasets/v3` | v2 + 상황 읽기 thought 접두 (`play_agent/distill_prep.py`) — r2 | 〃 |
| `datasets/v4` | v3 + "대상 보임/이 지역에 없음" | 〃 |
| `datasets/v5raw`, `v5` | 교사 + DAgger (교정 3배), v5 = 전처리본 — r3 | 〃 |
| `datasets/pairs_v1.jsonl` | DPO 선호 쌍 `btqa-play-pref/1` 8쌍 (chosen=교사, rejected=학생), DAgger 1 | 〃 |
| `raw/dagger2.jsonl` | DAgger 2 (r3 학생, seed 22·23) 82단계, 교정 6 (1개는 교사가 잘못 승인 → `edited`) | `reports/distill/dagger2.jsonl` |
| `datasets/v6raw`, `v6` | 교사 + DAgger 1·2, 교정 11개 3배, val = 교사 s5 — r4 | `distill_out/data/` |
| `datasets/v7raw`, `v7` | v6 + 상황 "목표 글 '인벤토리' = 버튼 ui.hud.inventory" — r5 | 〃 |
| `datasets/v8raw`, `v8` | v7 + 보이는 대상 거리 "(가까움 2.1)/(멂 12.6)" — r6 | 〃 |
| `datasets/pairs_v2.jsonl`, `pairs_v3.jsonl` | DAgger 1·2 쌍 13개 (v3 = chosen·rejected 모두 v8 형식 상황 접두) | 〃 |
| `raw/dagger3.jsonl` | DAgger 3 (r6 학생, seed 24) 42단계, 교정 5 (2개 `edited`) | `reports/distill/dagger3.jsonl` |
| `datasets/v9raw`, `v9` | + DAgger 3 (교정 15개 3배, train 414) — r7 | `distill_out/data/` |
| `datasets/v10raw`, `v10` | v9 + 창 버튼 글=id (선택 표시) — **r8 (최종, 5/5 완주)** | 〃 |
| `datasets/pairs_v4.jsonl`, `pairs_v5.jsonl` | DAgger 1~3 쌍 18개 (v5 = v10 형식) — r9 DPO | 〃 |
| `raw/dagger4.jsonl`, `dagger4b.jsonl` | DAgger 4 (r8 **GPU** 추론 학생, seed 1·2) 48·41단계 — GPU 에서 r8 이 약초 1/3 에 "목표 완료"로 착각 후 반복에 빠져서. `dagger4b` 는 그 실수를 일부러 통과시켜 복구 상태를 모음. 교사가 잘못 승인한 9개는 `edited` | `reports/distill/` |
| `datasets/v11raw`, `v11` | v10 + DAgger 4 (교정 28개 3배, train 550) — r12 | `distill_out/data/` |
| `logs/` | r8·r12 SFT·r9 DPO·r10/r11 RFT 학습 로그 (손실·보상, 가중치 아님), r12 설정·GPU 평가 | `distill_out/r*/` |

다시 만들기: `docs/DISTILL.md` 3장 (`btqa_play dataset --correction-weight 3 --prep play_agent.distill_prep:prep_sample` → `btqa_distill train`). v5~v11 은 예전 손 스크립트(교정과 입력이 같은 샘플까지 3배)로 만든 것이라 SDK 명령 결과와 train 수가 다르다 (v11: 550 ↔ 442) — 그 회차 재현은 이 사본으로.
