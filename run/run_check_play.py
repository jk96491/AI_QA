"""[PyCharm ▶] 플레이 모드 적합성 검사 (docs/PLAY_PROTOCOL.md v0.2) — LLM 없음, 스크립트로 튜토리얼 완주.

EXE 를 주면 헤드리스 인스턴스 4개(play·omniscient·play2·balance)를 직접 띄운다. 이미 띄운 인스턴스를 쓰려면 EXE = None, GAME 등 설정.
LOADOUT 을 주면 T9: 학습 결과(params.json / policy.json)로 필드 늑대왕 전투 + 밸런스 run_episode 와 result 비교.
"""
import sys

from _bootstrap import setup

# ===================== 설정 =====================
EXE = "unity_game/Build/QaArena.exe"
GAME = None            # 예: "127.0.0.1:7800" (EXE = None 일 때)
OMNI = None            # -qaPlayOmniscient 인스턴스
BALANCE = None         # 같은 빌드의 밸런스 모드 인스턴스
GAME2 = None           # T7 교차 비교용 (예: 창 모드)
LOADOUT = []           # 예: ["reports/20261123-003306"]  (warrior/forest_wolf_king 학습 결과)
# ================================================

if __name__ == "__main__":
    setup()
    from play_agent.__main__ import main

    argv = ["check-play"]
    for flag, v in (("--exe", EXE), ("--game", GAME), ("--omni", OMNI), ("--balance", BALANCE), ("--game2", GAME2)):
        if v:
            argv += [flag, v]
    if LOADOUT:
        argv += ["--loadout"] + list(LOADOUT)
    sys.exit(main(argv))
