# Unity 작업 묶음 → QaArena 0.8.3 (학습 쪽 → Unity 세션, 2026-11-24)

시작 전에 `CLAUDE.md`·`AGENT_GUIDE.md`·`SDK_MIGRATION.md` 를 읽는다. 아래 3건을 **한 빌드(0.8.3)** 로 묶는다. 순서는 위에서부터 권장.

| # | 요청서 | 무엇 | 바뀌는 곳 | 밸런스 결과 |
|---|---|---|---|---|
| 1 | `PROTOCOL_UPDATE_1.4.md` | 밸런스 프로토콜 1.4 `run_episode.initial_state` — 선언 2줄 + 적용 (`CombatSim.SetStartHpRatio` 추가) | `QaArenaHost`, `CombatSim` | `initial_state` 없는 판은 **0.8.2 와 동일** (T1 21/21) |
| 2 | `PLAY_SDK_DECLARATION_REQUEST.md` | 플레이 `play_description` 에 행동 `description`·`schema` 6개 + `pilot_guide`(system_prompt·about·rules·default_goal) + `progress_keys` | `Assets/QA/Play/Server/PlaySession.cs: Describe()` | 변화 없음 (전투 무관) |
| 3 | `UI_FOLLOWUP_0.8.2.md` | 화면 겹침 H1(QA 메모 패널 ↔ 대화창)·H3(전투 로그 ↔ QA 패널)·H4(스킬 이름 ↔ 쿨 숫자) | Presentation (화면만) | 변화 없음 |

## 바뀐 배경 (알고만 있으면 됨)

- **SDK 0.3.0**: SDK 레포에 플레이 모드 LLM 클라이언트(`btqa_play`)가 추가됐다. **Unity 패키지 `Packages/com.btqa.game` 은 코드 변화 없음** — `package.json` 버전만 0.2.0 → 0.3.0 (학습 쪽이 `run/run_sync_sdk.py` 로 이미 반영). 1번 요청서의 "SDK 0.2.0" 은 Runtime 코드 기준으로 그대로 맞다. 패키지는 여전히 **수정 금지**.
- **SDK 에는 게임 내용이 없다** (사용자 결정): LLM 도구 설명·관찰 읽는 법·목표는 지금 학습 쪽 `play_agent/specs/qa_arena.play.json` 이 채우고 있다. 2번은 그 내용을 게임이 직접 선언하게 하는 것 — **그 파일을 그대로 옮기는 것이 출발점** (형식이 같다). 게임 선언이 있으면 스펙 파일보다 우선한다.
- 학습 쪽 Python 은 이제 `btqa_sdk` 레포를 직접 참조한다 (루트 `btqa_game/` 사본 없음). Unity 쪽 영향 없음.

## 하지 않을 것

- `Packages/com.btqa.game` 수정, `unity_game/` 밖 파일 수정.
- 플레이 hello 버전 변경 — **"0.3" 유지** (2번 필드는 선택 필드). 0.4(computer use raw 입력)는 **사용자 결정 대기** 그대로, `actions_raw` 손대지 않는다.
- 밸런스 데이터 변경 (재학습이 필요해진다).

## 검증 (Unity 쪽 포트 7810~7819만)

```bash
# 밸런스 (1번)
python -m btqa_game check --game 127.0.0.1:7811                          # v1.4 항목 4개 포함 전부 PASS
venv\Scripts\python.exe -m balance_qa check-game --game 127.0.0.1:7811   # initial_state 2항목 PASS
# + T1 회귀 (QaTools~/t1_baseline_0.8.1.json 21/21)

# 플레이 (2번)
venv\Scripts\python.exe -m play_agent tools --game 127.0.0.1:7812 --spec none
#   → 행동 6개 모두 "설명/스키마 출처 = game/game", "선언 검사: 통과", 프롬프트에 system_prompt·"qa_arena 안내:" 블록
venv\Scripts\python.exe -m play_agent check-play --exe unity_game/Build/QaArena.exe
#   → 전부 PASS (0.8.2 = 127/127), T-D 줄 "출처 ...=game/game, pilot_guide 있음"
# + play_check.py 그대로 PASS

# 화면 (3번): 창 모드 스크린샷 — 대화창 열린 장면, 전투 중 장면, 스킬 바
```

## 주의

- `build.ps1` 은 **모든 QaArena 프로세스를 끈다** → 빌드 전에 학습 세션(`ai-qa-c7`)에 먼저 알린다. 학습 쪽 포트는 7800~7809.
- `game_version` 0.8.3, `README.md` 에 한 줄.

## 보고 (학습 쪽에 돌려줄 것)

1. 빌드 번호·빌드 시각
2. 1번: `btqa_game check`·`check-game` 결과 줄, T1 21/21
3. 2번: `play_agent tools --spec none` 출력의 출처 표와 "안내" 블록, `pilot_guide.rules` 최종 문구, `check-play` 합계
4. 3번: 스크린샷 경로
5. 요청서와 다르게 한 것과 그 이유
