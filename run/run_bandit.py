"""[PyCharm ▶] IMPALA 컨텍스트 밴딧 — 판 시작 상황(직업·시나리오·시작 체력/물약) → 블록 가중치 (docs/BANDIT_IMPALA_DESIGN.md).

판 하나 = 결정 1번 (트리거 없음, run_episode.params). 시작 상태는 프로토콜 v1.4 run_episode.initial_state —
게임이 describe.initial_state 를 선언해야 한다 (game_sim 은 선언함, Unity 는 unity_game/PROTOCOL_UPDATE_1.4.md 반영 후).
선언이 없으면 컨텍스트 = 조합만.

결과: reports/<run_id>/report.md (칸별 손튜닝 vs 밴딧), policy.json (play_agent 로드아웃으로 바로 쓸 수 있음), impala_model.pt
비교 실험(CMA-가득/전역/칸별 vs 밴딧)은 run_experiment.py 의 e8_bandit.
"""
from _bootstrap import UNITY, connection_args, opt, run_cli  # noqa: F401

# ===================== 설정 =====================
COMBOS = ["warrior:forest_wolf_king", "mage:forest_wolf_king"]   # class:scenario
PERSONA = "stable"
BUDGET = 8000             # 총 판수 (모든 액터 합)
BATCH = 32                # 갱신당 판 수 (밴딧은 분산이 커서 32)
HIDDEN = [64, 64]
LR = 3e-3
ENTROPY = 3e-3
CONCENTRATION = 10.0
P_FULL = 0.4              # 가득 찬 시작으로 뽑을 확률 (나머지는 시작 상태를 섞음)
LEVELS = ["potions_ratio=0,0.333,0.667,1"]          # 학습 시작 상태 단계 (없는 키는 범위 균등)
EVAL_LEVELS = ["potions_ratio=0,0.333,0.667,1", "hp_ratio=1,0.5"]   # 평가 격자
EVAL_N = 100              # 칸마다
NO_BASELINE = False       # 칸별 손 튜닝 평가 생략
LOG_EVERY = 10
SEED = 0

ACTORS = "processes"      # "processes" | "threads" | "external"
LISTEN = "127.0.0.1:0"
TOKEN = None
IDLE_TIMEOUT = 300

GAME = None               # 이미 떠 있는 게임: "127.0.0.1:7777,127.0.0.1:7778"
WORKERS = 8               # GAME 이 None 일 때 인스턴스 수 = 액터 수
GAME_CMD = None           # Unity 빌드: UNITY (1.4 반영 빌드여야 시작 상태를 쓴다) / None = 게임 대역(game_sim)
VIEW = 0
TORCH_THREADS = None
# ================================================

if __name__ == "__main__":
    run_cli(
        connection_args(GAME, WORKERS, GAME_CMD, VIEW)
        + opt("--torch-threads", TORCH_THREADS)
        + ["bandit", "--combos"] + list(COMBOS)
        + ["--persona", PERSONA, "--budget", str(BUDGET), "--batch", str(BATCH), "--lr", str(LR),
           "--entropy", str(ENTROPY), "--concentration", str(CONCENTRATION), "--p-full", str(P_FULL),
           "--eval-n", str(EVAL_N), "--log-every", str(LOG_EVERY), "--seed", str(SEED), "--actors", ACTORS,
           "--listen", LISTEN, "--idle-timeout", str(IDLE_TIMEOUT)]
        + opt("--hidden", HIDDEN)
        + (["--levels"] + list(LEVELS) if LEVELS else [])
        + (["--eval-levels"] + list(EVAL_LEVELS) if EVAL_LEVELS else [])
        + (["--no-baseline"] if NO_BASELINE else [])
        + opt("--token", TOKEN)
    )
