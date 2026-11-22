"""[PyCharm ▶] 결정 트리거 정책 IMPALA 학습 (액터 = 게임 인스턴스, V-trace, torch CPU).

액터 모드
- "processes": 게임 인스턴스마다 로컬 액터 프로세스 1개 (기본, 로컬 다중 액터)
- "threads"  : 학습기 안 스레드 (가벼운 실행)
- "external" : 학습기는 LISTEN 에서 대기, 액터는 run_actor.py / `python -m balance_qa actor` 로 따로 접속
               (다른 PC·클라우드 머신). 이때 GAME/WORKERS 의 게임은 평가에만 쓰임.

결과: reports/<run_id>/report.md, policy.json, impala_model.pt
"""
from _bootstrap import UNITY, connection_args, opt, run_cli  # noqa: F401

# ===================== 설정 =====================
CLASS = "warrior"
PERSONA = "stable"
BUDGET = 8000             # 총 판수 (모든 액터 합)
BATCH = 16                # 갱신당 궤적 수
HIDDEN = [64, 64]
LR = 3e-3
ENTROPY = 3e-3
GAMMA = 1.0
CONCENTRATION = 10.0      # 초기 Beta 집중도 (클수록 초기 탐색 좁음)
INIT_PARAMS = None        # 시작 평균: "reports/<run_id>/params.json" (optimize 결과 권장)
EVAL_N = 300
LOG_EVERY = 10
SCENARIO = None
SEED = 0

ACTORS = "processes"      # "processes" | "threads" | "external"
LISTEN = "127.0.0.1:0"    # 학습기 서버 주소. external/다른 PC 접속: "0.0.0.0:7000"
TOKEN = None              # external 에서 권장 (액터도 같은 값)
IDLE_TIMEOUT = 300        # 이 시간(초) 동안 판이 안 오면 중단

GAME = None               # Unity 등 접속: "127.0.0.1:7777,127.0.0.1:7778" (processes: 액터 수 = 엔드포인트 수)
WORKERS = 8               # GAME 이 None 일 때 게임 대역 수 = 로컬 액터 수
GAME_CMD = None           # Unity 빌드: UNITY (헤드리스 WORKERS 개) / 직접 명령 템플릿
VIEW = 0                  # GAME_CMD 인스턴스 중 화면(창) 모드 수 — 1 이면 전투 뷰어로 학습 판이 보인다
TORCH_THREADS = None
# ================================================

if __name__ == "__main__":
    run_cli(
        connection_args(GAME, WORKERS, GAME_CMD, VIEW)
        + opt("--torch-threads", TORCH_THREADS)
        + ["impala", "--cls", CLASS, "--persona", PERSONA, "--budget", str(BUDGET), "--batch", str(BATCH),
           "--lr", str(LR), "--entropy", str(ENTROPY), "--gamma", str(GAMMA),
           "--concentration", str(CONCENTRATION), "--eval-n", str(EVAL_N), "--log-every", str(LOG_EVERY),
           "--seed", str(SEED), "--actors", ACTORS, "--listen", LISTEN, "--idle-timeout", str(IDLE_TIMEOUT)]
        + opt("--token", TOKEN)
        + opt("--hidden", HIDDEN)
        + opt("--init-params", INIT_PARAMS)
        + opt("--scenario", SCENARIO)
    )
