"""게임 대역 (BT 전투 시뮬레이터 + 프로토콜 서버).

학습 플랫폼(balance_qa)과는 docs/PROTOCOL.md 의 TCP JSON Lines 프로토콜로만 통신한다.
추후 Unity 빌드가 같은 프로토콜을 구현하면 이 패키지를 대체한다.

이 패키지는 balance_qa 나 torch 를 import 하지 않는다 (tests/test_independence.py 가 검사).

모듈
- core   : 게임 내부 타입 (Action, Observation, EpisodeResult)
- spec   : 게임 데이터 (직업·보스·시나리오) 로드와 검증, BT 파라미터 정의
- bt     : 2층 BT (전략 선택 노드 S = N × w + 고정 행동 블록)
- sim    : 틱 기반 전투 시뮬레이터
- server : TCP 프로토콜 서버
"""

__version__ = "0.2.0"
