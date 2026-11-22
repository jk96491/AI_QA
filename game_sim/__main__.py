"""게임 대역 서버 실행.

python -m game_sim serve --port 7777
python -m game_sim serve --port 0          # 빈 포트 자동 선택 (stdout 에 "LISTENING <port>" 출력)
python -m game_sim validate                # 게임 데이터 검사만
"""
from __future__ import annotations

import argparse
import sys

from game_sim.spec.loader import DATA_DIR, SpecRepository


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    p = argparse.ArgumentParser(prog="game_sim", description="BT 전투 게임 대역 서버 (추후 Unity 빌드로 대체)")
    p.add_argument("--data", default=str(DATA_DIR), help="게임 데이터 폴더")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=7777)
    sub.add_parser("validate")
    args = p.parse_args()

    repo = SpecRepository(args.data)
    if args.cmd == "validate":
        repo.validate_all()
        print("OK: classes=%s scenarios=%s" % (repo.class_names(), list(repo.scenarios())))
        return

    from game_sim.server.server import GameServer

    server = GameServer(args.host, args.port, repo)
    print("LISTENING %d" % server.address[1], flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
