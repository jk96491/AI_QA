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
| `datasets/pairs_v1.jsonl` | DPO 선호 쌍 `btqa-play-pref/1` 8쌍 (chosen=교사, rejected=학생) — r4 용 | 〃 |

다시 만들기: `docs/DISTILL.md` (dataset → distill_prep → train).
