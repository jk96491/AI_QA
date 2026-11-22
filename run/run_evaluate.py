"""[PyCharm ▶] 고정 파라미터 평가 (기본: 정의서 default = 손 튜닝 값)."""
from _bootstrap import UNITY, connection_args, opt, run_cli  # noqa: F401

# ===================== 설정 =====================
CLASSES = ["warrior", "mage", "archer"]
PERSONAS = ["stable"]                     # aggressive / stable / efficient / speedrun
N = 200                                   # 판수 (평가 시드)
PARAMS_FILE = None                        # 학습 결과로 평가: "reports/<run_id>/params.json"
SCENARIO = None                           # 패치 시나리오: "patch_boss_hp_up5" 등

GAME = None                               # Unity 등 접속: "127.0.0.1:7777,127.0.0.1:7778"
WORKERS = 4                               # GAME 이 None 일 때 띄울 게임 대역 수 (= 병렬 판 수)
GAME_CMD = None           # Unity 빌드: UNITY (헤드리스 WORKERS 개) / 직접 명령 템플릿
VIEW = 0                  # GAME_CMD 인스턴스 중 화면(창) 모드 수 — 1 이면 전투 뷰어로 학습 판이 보인다
# ================================================

if __name__ == "__main__":
    run_cli(
        connection_args(GAME, WORKERS, GAME_CMD, VIEW)
        + ["evaluate", "--cls", *CLASSES, "--persona", *PERSONAS, "-n", str(N)]
        + opt("--params", PARAMS_FILE)
        + opt("--scenario", SCENARIO)
    )
