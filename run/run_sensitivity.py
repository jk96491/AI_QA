"""[PyCharm ▶] OAT 민감도 분석 — 어떤 파라미터가 결과를 크게 바꾸는가 (원문 6장)."""
from _bootstrap import UNITY, connection_args, opt, run_cli  # noqa: F401

# ===================== 설정 =====================
CLASS = "archer"
PERSONA = "stable"
N = 100                   # 레벨당 판수
LEVELS = 5                # 파라미터당 시험 값 개수
PARAMS_FILE = None        # 기준 파라미터: "reports/<run_id>/params.json" (None = 정의서 default)
SCENARIO = None

GAME = None
WORKERS = 4
GAME_CMD = None           # Unity 빌드: UNITY (헤드리스 WORKERS 개) / 직접 명령 템플릿
VIEW = 0                  # GAME_CMD 인스턴스 중 화면(창) 모드 수 — 1 이면 전투 뷰어로 학습 판이 보인다
# ================================================

if __name__ == "__main__":
    run_cli(
        connection_args(GAME, WORKERS, GAME_CMD, VIEW)
        + ["sensitivity", "--cls", CLASS, "--persona", PERSONA, "-n", str(N), "--levels", str(LEVELS)]
        + opt("--params", PARAMS_FILE)
        + opt("--scenario", SCENARIO)
    )
