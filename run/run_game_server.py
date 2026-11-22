"""[PyCharm ▶] 파이썬 게임 대역 서버를 단독 실행 (Unity 빌드 대신 포트로 띄워 두고 테스트할 때).

실행해 두고 다른 실행 스크립트에서 GAME = "127.0.0.1:<PORT>" 로 접속한다. 정지는 PyCharm ■ 버튼.
"""
from _bootstrap import setup

# ===================== 설정 =====================
HOST = "127.0.0.1"
PORT = 7777
# ================================================

if __name__ == "__main__":
    setup()
    from game_sim.server.server import GameServer

    server = GameServer(HOST, PORT)
    print("게임 대역 서버 대기 중: %s:%d  (정지: ■)" % server.address, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
