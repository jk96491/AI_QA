"""[PyCharm ▶] 게임 describe 정보(직업·파라미터·시나리오·트리거) + 페르소나 목록."""
from _bootstrap import connection_args, run_cli

# ===================== 설정 =====================
GAME = None              # "127.0.0.1:7777" 이면 그 게임에 접속, None 이면 파이썬 게임 대역
WORKERS = 1
# ================================================

if __name__ == "__main__":
    run_cli(connection_args(GAME, WORKERS) + ["list"])
