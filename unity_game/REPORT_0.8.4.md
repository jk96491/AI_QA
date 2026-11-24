# QaArena 0.8.4 보고 — 시야 밖 퀘스트 대상 (`OFFSCREEN_TARGET_REQUEST.md`, 2026-11-24)

- 빌드: `Build/QaArena.exe` **0.8.4**, 2026-11-24 21:47:42. 플레이 hello "0.3" 유지. 밸런스·전투·상점 함정은 바꾸지 않았다.
- 한 것: 권장안 **A** 만. B(마을 NPC 를 `always_known` 으로)는 하지 않았다 — A 만으로 튜토리얼이 끝까지 풀린다.

## 바뀐 동작과 필드

- 관찰 `entities[]` 에 새 필드 **`"known": "marker"`** 를 추가했다. 시야 밖이지만 퀘스트 마커로 위치를 아는 엔티티에 붙는다. 시야 안이면 이 필드가 없다 (지금처럼). omniscient 모드의 `hidden:true` 와는 따로다.
- 마커 대상이 되는 엔티티:
  - 진행 중(active) 퀘스트에서 완료 안 된 목표의 `target`·`hint_targets`. 반납 목표는 빼는데, 이는 기존 `marker:"objective"` 규칙과 같다.
  - 반납 가능(ready) 퀘스트에서 반납 목표의 `target`·`hint_targets`.
  - 지금 지역의 엔티티만 해당한다 (다른 지역 대상은 넣지 않음). 비활성 엔티티(이미 주운 약초 등)는 제외한다.
- `move_to(target)`·`interact`·`engage` 의 지각 판정에도 마커 대상을 넣었다. 그래서 시야 밖이어도 `not_visible` 이 나지 않고 길찾기로 간다.
- 선언 문구: `move_to.description` 과 `pilot_guide.system_prompt` 의 entities 줄에 `known:"marker"` 의 뜻을 적었다.
- 코드: `World/WorldState.cs: IsQuestMarkerTarget`, `Perception/Observers.cs` (Entities, EntityPerceivable), `Server/PlaySession.cs` (지각 판정에 world 전달, 문구).

## 장면 관찰 (`QaTools~/offscreen_check.py 127.0.0.1:7810`, 14/14 PASS)

장면 A — 촌장 옆, q_tut_04 수락 직후 (player.pos [4.4, 0, 4.4]):
```json
{"id": "npc_merchant", "role": "npc", "label": "상인", "pos": [-5.0, 0.0, -4.0], "distance": 12.6, "actions": ["talk"], "tags": ["merchant"], "marker": "objective", "known": "marker"}
```
`move_to(npc_merchant)` → done. 도착 뒤 관찰에서는 시야 안이라 `known` 이 없다.

장면 B — 늑대왕 처치 뒤 마을 입구, q_tut_05 ready (player.pos [0, 0, 0]):
```json
{"id": "npc_guard", "role": "npc", "label": "경비병", "pos": [34.0, 0.0, -22.0], "distance": 40.5, "actions": ["talk"], "tags": ["guard"], "marker": "quest_turn_in", "known": "marker"}
```
`move_to(npc_guard)` → done.

그 밖에 확인한 것:
- 숲에 들어간 직후 시야 밖 약초(herb_03·04)가 `known:marker` 로 보인다. 3개를 주운 뒤에는 남은 herb_04 가 마커가 아니다.
- q_tut_05 가 active 인 동안(늑대왕 처치 전)에는 경비병이 마커가 아니다.
- 늑대왕도 `move_to(wolf_king)` 로 바로 간다 (처치 목표 대상).

## 회귀

- check-play 127/127 PASS (T-D game/game 그대로), play_check 120/120 PASS — **T3 지각 필터 기대값은 고칠 필요가 없었다**. 시작할 때 경비병은 목표 대상이 아니라 여전히 관찰에 없다.
- T1 21/21 동일 (밸런스 영향 없음).

## 학습 쪽 참고

- 교사 기록에서 좌표로 이동하던 부분(상인·경비병 찾기)은 이제 id 로 이동할 수 있다. relay `--record` 로 grounding 0건인지 확인하는 일은 학습 쪽에 맡긴다.
- 약초도 마커 대상이 되므로 숲에서 약초 위치를 탐색할 필요가 없다. 요청서 A 규칙(미완료 목표의 hint_targets)을 그대로 따른 결과다. 너무 쉽다고 보면 collect 목표를 빼는 쪽으로 바꿀 수 있다.
