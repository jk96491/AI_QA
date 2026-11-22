# 화면(뷰어) 모드 실행 인자 추가 요청 (학습 플랫폼 → Unity 게임)

> **반영됨 (2026-11-22, Unity 쪽)**: `-qaFollow`, `-qaViewSpeed <x>`, `-qaPanel 0` 모두 구현 (`Assets/Presentation/BattleViewerHud.cs: ApplyCommandLine`).
> 판 로직·결정성·프로토콜 동작은 바뀌지 않음. 게임 버전 0.2.0 그대로 (데이터 변경 없음).
> 학습 쪽은 이제 `WINDOW_FLAGS` 에 `-qaFollow -qaViewSpeed 8` 을 붙여도 된다.

- 작성: 학습 플랫폼 쪽, 2026-11-22
- 대상 빌드: `QaArena 0.2.0`
- 우선순위: 선택 (없어도 동작함 — 지금은 창에서 토글을 손으로 켜면 된다)

## 배경

학습 플랫폼에 `--view N` 이 생겼다. `--game-cmd` 로 띄우는 인스턴스 중 앞의 N개를 **창 모드**
(`-batchmode -nographics` 제거 + `-screen-fullscreen 0 -screen-width 1280 -screen-height 720`) 로 실행해,
전투 뷰어가 학습 판을 재생하게 한다. 전체 사이클 점검(`run/run_full_cycle.py`, `VIEW = 1`) 은 학습이 끝난 뒤
**같은 seed 로 손 튜닝 → CMA-ES → IMPALA 판을 차례로 그 창에 보낸다.**

확인 결과 (2026-11-22): 창 모드 인스턴스가 Direct3D 11 로 정상 기동, 학습·쇼케이스 판을 정상 처리.

## 불편한 점

1. **"학습 판 자동 따라보기" 가 기본 꺼짐** → 창이 뜰 때마다 손으로 켜야 학습 판이 보인다.
2. 재생 속도 기본 1x → 5분짜리 판을 보려면 매번 숫자키를 눌러야 한다.
3. 학습 판은 1~2 ms 마다 하나씩 끝나므로, 자동 따라보기는 "재생이 끝난 시점의 최신 판" 을 보여 준다 (표본 보기) — 이 동작은 지금 그대로 좋다.

## 요청 (명령행 인자, 창 모드에서만 의미)

| 인자 | 동작 | 기본 |
|---|---|---|
| `-qaFollow` | 시작부터 "학습 판 자동 따라보기" 켜기 | 꺼짐 |
| `-qaViewSpeed <x>` | 재생 속도 (0.5 / 1 / 2 / 4 / 8 / 16) | 1 |
| `-qaPanel 0` | 오른쪽 설정 패널 접기 (Tab 과 같음, 선택) | 펼침 |

- 판 로직·결정성·프로토콜 동작은 바꾸지 않는다 (뷰어 표시만).
- 반영되면 학습 쪽 화면 모드 기본 명령에 `-qaFollow -qaViewSpeed 8` 을 붙인다 (`balance_qa/game_api/launcher.py: WINDOW_FLAGS`).
- 그 전까지 학습 쪽은 이 인자를 붙이지 않는다 (모르는 인자는 Unity 가 무시하지만, 동작 확인 전이라).

## 확인

```bash
venv\Scripts\python.exe run/run_full_cycle.py   # GAME_CMD = UNITY, VIEW = 1 → 창이 뜨자마자 판이 재생되면 완료
```
