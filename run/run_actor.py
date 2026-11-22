"""[PyCharm ▶] IMPALA 액터 1개를 따로 실행 — 학습기(external 모드)에 접속해 판을 돌린다.

사용: run_impala.py 를 ACTORS = "external" 로 먼저 실행 → 출력된 학습기 주소를 LEARNER 에 넣고 이 스크립트 실행.
여러 개 띄우려면 이 실행 구성을 여러 번 실행 (PyCharm: Run 구성 'Allow multiple instances') 하거나 ACTOR_ID 를 바꿔 실행.
나중에 클라우드에서는 각 머신에서 `python -m balance_qa --game ... actor --learner <학습기>` 로 같은 일을 한다.
"""
from _bootstrap import opt, run_cli

# ===================== 설정 =====================
LEARNER = "127.0.0.1:7000"   # 학습기 주소 (run_impala.py 의 LISTEN 포트)
TOKEN = None                 # 학습기와 같은 값
ACTOR_ID = None              # None = 호스트이름-포트

GAME = None                  # 이 액터가 쓸 게임 "127.0.0.1:7777" / None = 파이썬 게임 대역 1개 자동 실행
GAME_CMD = None              # 명령으로 게임 1개 실행: "Build/Game.exe -batchmode -nographics -qaPort {port}"
# ================================================

if __name__ == "__main__":
    conn = opt("--game", GAME) + opt("--game-cmd", GAME_CMD if not GAME else None)
    run_cli(conn + ["actor", "--learner", LEARNER] + opt("--token", TOKEN) + opt("--actor-id", ACTOR_ID))
