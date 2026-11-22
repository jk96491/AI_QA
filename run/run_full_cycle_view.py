"""[PyCharm ▶] 전체 사이클 점검 — Unity 빌드 + 화면(창) 1개로 전투를 보면서.

Unity 인스턴스(= IMPALA 액터) WORKERS 개 중 VIEW 개를 창으로 띄운다. 창마다 '학습 판 자동 따라보기' 를 켜면
그 인스턴스가 처리 중인 학습 판(표본)이 재생된다. 학습이 끝나면 같은 seed 로 손 튜닝 / CMA-ES / IMPALA 판을
창 1·2·3 에 동시에 보내 나란히 비교한다 (창이 3개 미만이면 창 1에 차례로).
판 사이·종료는 콘솔에서 Enter. (속도: 창에서 숫자키 1~6 = 0.5x~16x, Tab = 패널)
"""
import run_full_cycle as cycle

# ===================== 설정 =====================
CLASS = "warrior"         # 학습 여지가 큰 직업 (archer 는 이미 쉬움)
PERSONA = "stable"
WORKERS = 4               # Unity 인스턴스 수 (그중 VIEW 개가 창)
VIEW = 4                  # 창으로 띄울 수 (WORKERS 이하). 4 = 전부 보기
VIEW_SIZE = None          # (가로, 세로). None = 창 여러 개면 900x506
SHOWCASE_WAIT = None      # None = Enter 로 넘김 / 숫자 = 그 초만큼 기다렸다 자동으로 넘김
OPT_BUDGET = 600
IMPALA_BUDGET = 800
# ================================================

if __name__ == "__main__":
    cycle.GAME_CMD = cycle.UNITY
    cycle.GAME = None
    for name in ("CLASS", "PERSONA", "WORKERS", "VIEW", "VIEW_SIZE", "SHOWCASE_WAIT", "OPT_BUDGET", "IMPALA_BUDGET"):
        setattr(cycle, name, globals()[name])
    raise SystemExit(cycle.main())
