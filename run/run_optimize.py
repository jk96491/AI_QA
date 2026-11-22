"""[PyCharm ▶] 판당 1회 파라미터 최적화 (CMA-ES / 무작위 탐색, torch CPU).

결과: reports/<run_id>/report.md, params.json (다음 단계 --init-params 로 사용)
"""
from _bootstrap import UNITY, connection_args, opt, run_cli  # noqa: F401

# ===================== 설정 =====================
CLASS = "mage"
PERSONA = "stable"
METHOD = "cma"            # "cma" | "random"
BUDGET = 3000             # 총 학습 판수
K = 10                    # 후보당 판수
POPSIZE = None            # None = CMA-ES 기본값
EVAL_N = 300              # 최종 평가 판수
SCENARIO = None
SEED = 0

GAME = None               # Unity 등 접속: "127.0.0.1:7777,127.0.0.1:7778"
WORKERS = 4
GAME_CMD = None           # Unity 빌드: UNITY (헤드리스 WORKERS 개) / 직접 명령 템플릿
VIEW = 0                  # GAME_CMD 인스턴스 중 화면(창) 모드 수 — 1 이면 전투 뷰어로 학습 판이 보인다
TORCH_THREADS = None      # 학습 연산 스레드 수 (None = torch 기본값)
# ================================================

if __name__ == "__main__":
    run_cli(
        connection_args(GAME, WORKERS, GAME_CMD, VIEW)
        + opt("--torch-threads", TORCH_THREADS)
        + ["optimize", "--cls", CLASS, "--persona", PERSONA, "--method", METHOD,
           "--budget", str(BUDGET), "-k", str(K), "--eval-n", str(EVAL_N), "--seed", str(SEED)]
        + opt("--pop", POPSIZE)
        + opt("--scenario", SCENARIO)
    )
