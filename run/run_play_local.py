"""[PyCharm ▶ 16] 로컬 LLM(Ollama, CPU 추론)이 게임을 플레이하는 것을 Unity 창으로 보기.

- Unity 를 플레이 모드 창으로 띄우고 (-qaPlay), 로컬 LLM 이 마을부터 플레이한다. 전투는 학습 결과 로드아웃의 BT.
- LLM 은 단계 형식 (대화 기록 없이 지금 관찰 + 직전 행동 결과 → JSON 행동 1개, `--tool-mode json --stateless` 와 같음).
  LLM 이 말한 이유(thought)는 게임 화면 "QA 플레이어" 패널과 이 콘솔에 한 줄씩 나온다.
- Ollama 는 GPU 가 있으면 자동으로 GPU 를 쓴다 → MODEL 이 CPU 전용 변형(num_gpu 0)이 아니면 BASE 로 만들어 쓴다.
- 기록: reports/distill/local-<시각>.jsonl (단계 기록, 증류 비교용) + reports/play-local-<시각>/run.json·play_log.json.

준비: Ollama 설치 + `ollama pull qwen2.5:1.5b` (docs/DISTILL.md 2장). 증류한 모델은 MODEL 에 그 이름 (예 "qa-qwen1.5b-r1").
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from _bootstrap import ROOT, setup

# ===================== 설정 =====================
MODEL = "qa-qwen1.5b-r8"     # Ollama 모델 이름 (CPU 전용). 증류 r8 = 튜토리얼 5개 완주 (2026-11-25). 원본 비교는 "qwen2.5-1.5b-cpu"
BASE = "qwen2.5:1.5b"        # MODEL 이 없을 때 CPU 전용 변형을 만들 원본 (ollama pull 로 받은 것)
OLLAMA_URL = "http://localhost:11434"
CLASS = "warrior"
SEED = 1
MAX_ACTIONS = 80             # 행동 상한
NO_PROGRESS = 15             # 이만큼 행동하는 동안 진척이 없으면 끝 (진척 = QaArena 스펙 progress_keys)
LOADOUT = "latest"           # "latest" = reports/ 의 최근 늑대왕 학습 결과 / "reports/<run>" / None = 손 튜닝 BT
SPEC = "play_agent/specs/qa_arena.play.json"   # 게임이 선언하지 않은 안내를 채움 (0.8.3 은 게임 선언이 우선)
PORT = 7800                  # 학습 쪽 포트 범위 7800~7809 (Unity 세션은 7810~7819)
PLAY_SPEED = 2               # 마을·필드 배속
COMBAT_SPEED = 6             # 전투 배속
WINDOW = (1280, 720)
RECORD = True                # 단계 기록 JSONL 남기기
CLOSE_GAME_AT_END = False    # 끝나도 창을 남겨 둔다 (직접 닫기)
# ================================================

EXE = ROOT / "unity_game" / "Build" / "QaArena.exe"


def ollama_models() -> list:
    with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=5) as r:
        return [m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])]


def ensure_model() -> Optional[str]:
    """MODEL 을 쓸 수 있게 한다. 문제가 있으면 안내 문구를 돌려준다."""
    try:
        names = ollama_models()
    except OSError:
        return "Ollama 서버에 접속 못 함 (%s) — Ollama 를 실행하라 (설치: https://ollama.com/download)" % OLLAMA_URL
    if MODEL in names or MODEL + ":latest" in names:
        return None
    if BASE not in names:
        return "모델 %s 도 %s 도 없음 — 먼저: ollama pull %s" % (MODEL, BASE, BASE)
    from btqa_distill.export import cpu_variant_modelfile, ollama_create   # 표준 라이브러리만 쓰는 부분
    mf = ROOT / "reports" / "distill" / ("%s.Modelfile" % MODEL.replace(":", "_"))
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(cpu_variant_modelfile(BASE), encoding="utf-8")
    print("CPU 전용 변형 만들기: %s = %s (num_gpu 0)" % (MODEL, BASE))
    ollama_create(MODEL, mf)
    return None


def device() -> str:
    """실제로 올라간 장치 (ollama ps 의 PROCESSOR, 모델 이름이 아니라). 모르면 '?'"""
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/ps", timeout=3) as r:
            for m in json.loads(r.read().decode("utf-8")).get("models", []):
                if m.get("name") in (MODEL, MODEL + ":latest"):
                    return "GPU" if m.get("size_vram") else "CPU"
    except OSError:
        pass
    return "?"


def port_open(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
        return True
    except OSError:
        return False


def launch_game() -> subprocess.Popen:
    log = ROOT / "unity_game" / "Logs" / ("play_local_%d.log" % PORT)
    log.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([str(EXE), "-qaPlay", "-qaPort", str(PORT), "-qaPlaySpeed", str(PLAY_SPEED),
                             "-qaPlayCombatSpeed", str(COMBAT_SPEED), "-screen-fullscreen", "0",
                             "-screen-width", str(WINDOW[0]), "-screen-height", str(WINDOW[1]), "-logFile", str(log)])
    end = time.time() + 90
    while time.time() < end:
        if proc.poll() is not None:
            raise RuntimeError("Unity 가 바로 종료됨 (exit %s), 로그 %s" % (proc.returncode, log))
        if port_open(PORT):
            return proc
        time.sleep(0.3)
    raise TimeoutError("Unity 플레이 서버가 90초 안에 열리지 않음")


def print_step(s: Dict[str, Any]) -> None:
    r = s["result"]
    status = r.get("status") or ("오류: " + str(r.get("error"))[:80] if r.get("error") else "")
    extra = (" (%s)" % r["reason"]) if r.get("reason") else ""
    args = json.dumps(s["input"], ensure_ascii=False)
    print("%3d  %5.1fs  %-9s %-48s → %s%s" % (s["step"], s["latency_s"], s["tool"] or "?", args[:48], status, extra), flush=True)
    if s["thought"]:
        print("            ↳ %s" % s["thought"][:110], flush=True)
    for c in s.get("combats") or []:
        print("            ⚔ %s: %s, 사망 %s, 물약 %s 사용" % (c.get("enemy"), "승리" if c.get("cleared") else "패배",
                                                         c.get("deaths"), c.get("potions_used")), flush=True)
    obs = s.get("observation") or {}
    for q in obs.get("quests") or []:
        if q.get("state") == "ready":
            print("            ✓ 퀘스트 목표 완료: %s" % q.get("title"), flush=True)


def _args() -> None:
    """명령줄로 설정 덮기 (PyCharm 은 위 설정 블록): --model qa-qwen1.5b-r1 --seed 2 --cls mage --max-actions 60"""
    import argparse
    global MODEL, SEED, CLASS, MAX_ACTIONS
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--cls", default=CLASS)
    ap.add_argument("--max-actions", type=int, default=MAX_ACTIONS)
    a = ap.parse_args()
    MODEL, SEED, CLASS, MAX_ACTIONS = a.model, a.seed, a.cls, a.max_actions


def main() -> int:
    setup()
    _args()
    from btqa_play.client import PlayClient
    from btqa_play.evaluate import quests_completed
    from btqa_play.llm.json_action import JsonActionBackend
    from btqa_play.pilot import LlmPilot, PilotConfig
    from btqa_play.record import StepRecorder
    from play_agent.loadout import LoadoutBuilder

    problem = ensure_model()
    if problem:
        print(problem)
        return 1
    if not EXE.exists():
        print("Unity 빌드가 없음: %s" % EXE)
        return 1
    proc = None
    if port_open(PORT):
        print("포트 %d 에 이미 게임이 떠 있다 — 그 게임에 붙는다 (플레이 모드여야 함)" % PORT)
    else:
        print("Unity 창 띄우는 중 (포트 %d)..." % PORT)
        proc = launch_game()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    rec = StepRecorder(ROOT / "reports" / "distill" / ("local-%s.jsonl" % stamp), run="local-%s-s%d" % (stamp, SEED),
                       source="model", model=MODEL) if RECORD else None
    try:
        with PlayClient.connect("127.0.0.1:%d" % PORT) as c:
            c.hello()
            desc = c.describe()
            lb, bt = LoadoutBuilder(), "손 튜닝 BT"
            if LOADOUT:
                path = ROOT / LOADOUT if LOADOUT != "latest" else \
                    LoadoutBuilder.find_latest(ROOT / "reports", CLASS, "forest_wolf_king")
                if path:
                    e = lb.add_file(path)
                    problems = lb.check_against(desc)
                    if problems:
                        print("로드아웃 문제 — 손 튜닝 BT 로: %s" % "; ".join(problems))
                        lb = LoadoutBuilder()
                    else:
                        c.set_loadout(lb.wire_entries(desc), persona=lb.persona())
                        bt = e.source
            print("게임 %s %s | LLM %s | 직업 %s, seed %d | 전투 BT: %s"
                  % (desc.get("game"), desc.get("game_version"), MODEL, CLASS, SEED, bt))
            print(" 단계  호출   도구      인자                                             → 결과")
            obs = c.reset(seed=SEED, cls=CLASS)
            backend = JsonActionBackend(MODEL, base_url=OLLAMA_URL + "/v1", max_tokens=300, temperature=0.0)
            pilot = LlmPilot(c, responder=lb.responder() if lb.entries else None, backend=backend, spec=str(ROOT / SPEC),
                             config=PilotConfig(stateless=True, max_actions=MAX_ACTIONS, max_calls=MAX_ACTIONS * 2,
                                                no_progress_actions=NO_PROGRESS),
                             recorder=rec, on_step=print_step)
            run = pilot.run(obs)
            log = c.get_log()
        done = quests_completed(log)
        out = ROOT / "reports" / ("play-local-" + stamp)
        out.mkdir(parents=True, exist_ok=True)
        (out / "run.json").write_text(json.dumps(dict(run.to_dict(), model=MODEL, seed=SEED, cls=CLASS, loadout=bt,
                                                      record=str(rec.path) if rec else None),
                                                 ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (out / "play_log.json").write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")
        lat = run.latency_s or [0.0]
        print("\n끝: %s | 완료 퀘스트 %d/%d %s | 행동 %d, 형식 오류 %d | 호출당 %.1fs (%s) | 기록 %s"
              % (run.end_reason, len(done), len(desc.get("quests") or []), done, run.actions, run.invalid_outputs,
                 sum(lat) / len(lat), device(), out))
    finally:
        if proc is not None and CLOSE_GAME_AT_END:
            proc.terminate()
    if proc is not None and not CLOSE_GAME_AT_END:
        print("게임 창은 열어 둠 — 다 보면 창을 닫는다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
