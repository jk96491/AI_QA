"""[PyCharm ▶] 결정 트리거 정책 학습 — MLP + OpenAI-ES (IMPALA 와 비교용)."""
from _bootstrap import UNITY, connection_args, opt, run_cli  # noqa: F401

# ===================== 설정 =====================
CLASS = "warrior"
PERSONA = "stable"
BUDGET = 6000
K = 8
POPSIZE = 16
HIDDEN = [16]
SIGMA = 0.1
LR = 0.05
INIT_PARAMS = None        # "reports/<run_id>/params.json"
EVAL_N = 300
SCENARIO = None
SEED = 0

GAME = None
WORKERS = 4
GAME_CMD = None           # Unity 빌드: UNITY (헤드리스 WORKERS 개) / 직접 명령 템플릿
VIEW = 0                  # GAME_CMD 인스턴스 중 화면(창) 모드 수 — 1 이면 전투 뷰어로 학습 판이 보인다
# ================================================

if __name__ == "__main__":
    run_cli(
        connection_args(GAME, WORKERS, GAME_CMD, VIEW)
        + ["policy", "--cls", CLASS, "--persona", PERSONA, "--budget", str(BUDGET), "-k", str(K),
           "--pop", str(POPSIZE), "--sigma", str(SIGMA), "--lr", str(LR), "--eval-n", str(EVAL_N),
           "--seed", str(SEED)]
        + opt("--hidden", HIDDEN)
        + opt("--init-params", INIT_PARAMS)
        + opt("--scenario", SCENARIO)
    )
