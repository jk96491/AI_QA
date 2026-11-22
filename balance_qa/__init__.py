"""BT 파라미터 최적화 기반 밸런스 QA — 학습 플랫폼 (퍼블리셔 쪽).

게임(game_sim 대역 또는 Unity 빌드)과는 docs/PROTOCOL.md 의 TCP JSON Lines 프로토콜로만 통신한다.
이 패키지는 game_sim 을 import 하지 않는다 (tests/test_independence.py 가 검사).

모듈 구성
- core     : 타입 (EpisodeResult, TriggerState, GameError)
- spec     : 게임 describe 정보(ClassInfo, GameDescription), 파라미터 공간, 페르소나
- game_api : 프로토콜 클라이언트, 게임 인스턴스 풀, 실행기, 적합성 검사
- control  : BT 파라미터 공급자 (고정값 / 트리거 정책)
- policy   : 결정 트리거용 MLP 정책 (torch CPU)
- optim    : 최적화 엔진 (무작위 탐색, CMA-ES, OpenAI-ES — torch CPU) 과 학습 루프
- reward   : 페르소나별 보상 함수
- runner   : 에피소드 실행 인터페이스, 시드 풀
- analysis : 평가·통계·민감도 분석
- report   : 진단 리포트 생성
"""

__version__ = "0.3.0"
