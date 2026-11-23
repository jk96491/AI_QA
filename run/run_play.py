"""[PyCharm ▶] 각자 고른 LLM 으로 튜토리얼 플레이 (docs/LLM_SETUP.md, PLAY_PROTOCOL 5장).

LLM 은 저장소 루트의 llm.json (git 에 안 올라감, 예시 play_agent/llm.example.json) 또는 아래 LLM·MODEL 로 고른다.
  - "openai"    : OpenAI 호환 — 로컬 Ollama·LM Studio·llama.cpp·vLLM 또는 호환 클라우드. 이 venv(3.8) 그대로
  - "anthropic" : Claude API — Python ≥ 3.10 + anthropic venv(venv_play) 에서 실행해야 함, 키 = 환경변수 ANTHROPIC_API_KEY
API 를 쓰지 않으려면 이 스크립트 대신 `python -m play_agent relay` (Claude Code 같은 대화형 에이전트가 직접 플레이).
키는 여기 쓰지 않는다 — API_KEY_ENV 에 환경변수 **이름**만.
"""
import subprocess
import sys
import time

from _bootstrap import setup

# ===================== 설정 =====================
EXE = "unity_game/Build/QaArena.exe"   # 창 모드로 띄움. 이미 떠 있으면 None 으로 두고 GAME 만
PORT = 7800
GAME = "127.0.0.1:7800"
LOADOUT = ["reports/20261123-203248"]  # 0.7.0 warrior/forest_wolf_king CMA 결과 (IMPALA: reports/20261123-203257)
LLM_CONFIG = None      # None = ./llm.json (있으면)
LLM = None             # None = llm.json 값. "openai" | "anthropic"
MODEL = None           # 예: "qwen2.5:14b" (openai), "claude-opus-5-5" (anthropic)
BASE_URL = None        # 예: "http://localhost:11434/v1" (Ollama), "http://localhost:1234/v1" (LM Studio)
API_KEY_ENV = None     # 예: "OPENAI_API_KEY" — 환경변수 이름
MAX_ACTIONS = 40       # 처음엔 짧게
# ================================================

if __name__ == "__main__":
    setup()
    from play_agent.__main__ import main

    proc = None
    if EXE:
        proc = subprocess.Popen([EXE, "-qaPlay", "-qaPort", str(PORT), "-qaPlaySpeed", "4",
                                 "-screen-fullscreen", "0", "-screen-width", "1280", "-screen-height", "720"])
        time.sleep(8)
    argv = ["play", "--game", GAME, "--max-actions", str(MAX_ACTIONS)]
    if LOADOUT:
        argv += ["--loadout"] + list(LOADOUT)
    for flag, v in (("--llm-config", LLM_CONFIG), ("--llm", LLM), ("--model", MODEL), ("--base-url", BASE_URL),
                    ("--api-key-env", API_KEY_ENV)):
        if v:
            argv += [flag, v]
    try:
        sys.exit(main(argv))
    finally:
        if proc is not None:
            proc.terminate()
