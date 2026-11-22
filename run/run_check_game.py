"""[PyCharm ▶] 게임 프로토콜 적합성 검사 (Unity 빌드 연결 전 필수)."""
from _bootstrap import opt, run_cli

# ===================== 설정 =====================
GAME = None              # Unity 빌드 등: "127.0.0.1:7777" / None 이면 파이썬 게임 대역으로 검사
# ================================================

if __name__ == "__main__":
    run_cli(opt("--game", GAME) + ["check-game"])
