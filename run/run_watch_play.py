"""[PyCharm ▶] 플레이 모드를 Unity 화면으로 보기 — 마을에서 시작해 튜토리얼 끝까지, 전투는 학습한 BT 가.

Unity 를 플레이 모드(-qaPlay) 창으로 띄우고, 정해진 행동열로 튜토리얼 퀘스트 5개를 진행한다:
  1 촌장과 대화 → 2 숲에서 약초 3개 → 촌장에게 보고 → 3 물약 퀵슬롯 등록 → 4 상인에게서 물약 구매
  → 5 숲의 늑대왕 처치 (전투 = 학습 결과 로드아웃: CMA-ES/IMPALA 가 정한 블록 가중치로 BT 가 싸움) → 경비에게 보고
비전투 행동은 이 스크립트가 고정 순서로 보낸다 (LLM 없음). LLM 이 직접 플레이하는 건 `python -m play_agent play`
(Python ≥3.10 + ANTHROPIC_API_KEY 필요, docs/STATUS.md 5-5).

학습 결과는 reports/ 에서 (직업, 필드 조우 시나리오 forest_wolf_king) 의 최근 IMPALA → 없으면 CMA-ES 를 찾는다.
없으면 손 튜닝 BT(정의서 default)로 싸운다. 학습: run/run_optimize.py · run/run_impala.py 에서 SCENARIO = "forest_wolf_king".
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from _bootstrap import ROOT, setup

# ===================== 설정 =====================
CLASS = "warrior"          # warrior | mage | archer
SEED = 3                   # 게임 seed (같은 seed = 같은 게임 — 조우 전투 seed 도 여기서 정해진다)
LOADOUT = "latest"         # "latest" = reports/ 자동 / ["reports/<run>", ...] 직접 / None = 손 튜닝 BT
PREFER = "impala"          # "latest" 일 때 먼저 찾을 방법: "impala" | "cma"
PLAY_SPEED = 2             # 마을·필드 이동 배속 (1 = 실시간)
COMBAT_SPEED = 4           # 전투 장면 배속 (6분 전투 = 4배속 약 1.5분)
STEP_PAUSE = 0.8           # 단계 사이 쉬는 시간(초) — 화면에서 따라가기 좋게
MAX_TRIES = 5              # 늑대왕에게 지면 다시 도전하는 횟수
WINDOW = (1280, 720)       # 창 크기
# ================================================

EXE = ROOT / "unity_game" / "Build" / "QaArena.exe"
REPORTS = ROOT / "reports"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_port(port: int, proc: subprocess.Popen, timeout: float = 90.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if proc.poll() is not None:
            raise RuntimeError("Unity 가 바로 종료됨 (exit %s)" % proc.returncode)
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return
        except OSError:
            time.sleep(0.3)
    raise TimeoutError("Unity 플레이 서버가 %d초 안에 열리지 않음" % timeout)


def set_title(pid: int, title: str) -> None:
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: List[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    end = time.time() + 15
    while not found and time.time() < end:
        user32.EnumWindows(enum, 0)
        time.sleep(0.3)
    for h in found[:1]:
        user32.SetWindowTextW(h, title)


def find_results(scenarios: List[str], game_version: str) -> List[Tuple[Path, str]]:
    """(직업, 시나리오)마다 최근 결과 1개. 현재 빌드 결과 우선, PREFER 방법 우선."""
    order = [PREFER] + [m for m in ("impala", "cma") if m != PREFER]
    out = []
    for sc in scenarios:
        best: Optional[Tuple[int, str, Path, str]] = None
        for run in sorted(REPORTS.iterdir()) if REPORTS.exists() else []:
            for name in ("policy.json", "params.json"):
                f = run / name
                if not f.exists():
                    continue
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if d.get("class") != CLASS or (d.get("scenario") or "base") != sc or d.get("method") not in order:
                    continue
                same = (d.get("game") or {}).get("version") == game_version
                rank = (0 if same else 2) + order.index(d["method"])      # 작을수록 좋음
                if best is None or rank <= best[0]:                       # 같은 순위면 더 최근 것
                    best = (rank, run.name, f, "%s, 빌드 %s%s" % (d["method"], (d.get("game") or {}).get("version"),
                                                                "" if same else " — 현재 빌드와 다름"))
        if best:
            out.append((best[2], best[3]))
    return out


def main() -> int:
    setup()
    from btqa_play.client import PlayClient
    from play_agent.loadout import LoadoutBuilder

    if not EXE.exists():
        print("Unity 빌드가 없음: %s" % EXE)
        return 1
    port = free_port()
    log = ROOT / "unity_game" / "Logs" / ("play_watch_%d.log" % port)
    log.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([str(EXE), "-qaPlay", "-qaPort", str(port), "-qaPlaySpeed", str(PLAY_SPEED),
                             "-qaPlayCombatSpeed", str(COMBAT_SPEED), "-screen-fullscreen", "0",
                             "-screen-width", str(WINDOW[0]), "-screen-height", str(WINDOW[1]), "-logFile", str(log)])
    try:
        wait_port(port, proc)
        c = PlayClient.connect("127.0.0.1:%d" % port)
        c.hello()
        desc = c.describe()
        scenarios = sorted({e["scenario"] for e in (desc.get("combat") or {}).get("encounters", [])})
        print("게임: %s %s (플레이 모드), 직업 %s, seed %d, 필드 조우 시나리오 %s"
              % (desc.get("game"), desc.get("game_version"), CLASS, SEED, scenarios))

        # ---------------- 학습 결과 → 로드아웃
        lb, responder, bt_label = LoadoutBuilder(), None, "손 튜닝 BT (정의서 default)"
        picks: List[Tuple[Path, str]] = []
        if LOADOUT == "latest":
            picks = find_results(scenarios, str(desc.get("game_version")))
        elif LOADOUT:
            picks = [(ROOT / p, "지정") for p in LOADOUT]
        for path, note in picks:
            entry = lb.add_file(path)
            print("  로드아웃: %s/%s ← %s (%s)" % (entry.cls, entry.scenario, path.relative_to(ROOT), note))
        if lb.entries:
            problems = lb.check_against(desc)
            for p in problems + lb.notes:
                print("  주의:", p)
            c.set_loadout(lb.wire_entries(desc), persona=lb.persona())
            responder = lb.responder()
            bt_label = "학습 BT (%s)" % ", ".join(sorted({e.method for e in lb.entries.values()}))
        else:
            print("  로드아웃: 없음 — %s/%s 학습 결과가 reports/ 에 없어 손 튜닝 BT 로 싸운다" % (CLASS, ",".join(scenarios)))
        set_title(proc.pid, "QaArena — 플레이 모드 · %s · 전투: %s" % (CLASS, bt_label))

        # ---------------- 진행
        n = [0]

        def step(text: str) -> None:
            n[0] += 1
            print("\n[%02d] %s" % (n[0], text), flush=True)
            time.sleep(STEP_PAUSE)

        def act(action: str, _quiet: bool = False, **args):
            r = c.act(action, args, responder=responder)
            for cb in r.combats:
                st, en = cb.started, cb.ended or {}
                res = en.get("result") or {}
                matched = (st.get("loadout") or {}).get("matched")
                print("     ⚔ 전투 %s vs %s — %s %.0fs, 사망 %s, 물약 %s, 트리거 응답 %d회 (%s)" % (
                    st.get("encounter_id"), st.get("enemy"), "승리" if res.get("cleared") else "패배",
                    float(res.get("elapsed", 0)), res.get("deaths"), res.get("consumables_used"), len(cb.triggers),
                    "학습 BT" if matched else "손 튜닝 BT"), flush=True)
            if r.status not in (None, "done") and not (_quiet and r.reason == "not_visible"):
                print("     → %s %s" % (r.status, r.reason or ""), flush=True)
            return r

        def goto(target: str, near: Optional[List[float]] = None):
            r = act("move_to", _quiet=near is not None, target=target)   # 안 보이면 근처로 갔다가 다시
            if r.reason == "not_visible" and near is not None:
                act("move_to", pos=near)
                r = act("move_to", target=target)
            return r

        def talk_and_choose(npc: str, choices: int, near: Optional[List[float]] = None) -> None:
            goto(npc, near)
            act("interact", target=npc, verb="talk")
            for _ in range(choices):
                act("ui_click", ui_id="ui.dialog.choice.0")

        def zone() -> str:
            return str(c.observe()["player"]["zone"])

        step("새 게임 — 마을에서 시작")
        c.reset(seed=SEED, cls=CLASS)
        step("퀘스트 1·2: 촌장과 대화하고 약초 채집을 맡는다")
        talk_and_choose("npc_elder", 2)
        step("숲으로")
        goto("portal_forest")
        act("interact", target="portal_forest", verb="enter")
        step("약초 3개 줍기")
        for h, near in (("herb_01", [-4, 0, -28]), ("herb_02", [4, 0, -23]), ("herb_03", [-6, 0, -15])):
            goto(h, near)
            act("interact", target=h, verb="pickup")
        step("마을로 돌아가 촌장에게 보고 (보상: 골드, 작은 물약 2)")
        goto("portal_village")
        act("interact", target="portal_village", verb="enter")
        talk_and_choose("npc_elder", 2)
        step("퀘스트 3: 인벤토리에서 작은 물약을 퀵슬롯에 등록")
        act("ui_click", ui_id="ui.hud.inventory")
        act("ui_click", ui_id="ui.tip.ok")
        act("ui_click", ui_id="ui.inventory.slot.potion_small")
        act("ui_click", ui_id="ui.inventory.assign")
        act("ui_click", ui_id="ui.inventory.close")
        step("퀘스트 4: 상인에게서 작은 물약 2개 구매")
        talk_and_choose("npc_merchant", 1, near=[-2, 0, -8])
        act("ui_click", ui_id="ui.shop.buy.potion_small")
        act("ui_click", ui_id="ui.shop.buy.potion_small")
        act("ui_click", ui_id="ui.shop.close")
        step("퀘스트 5: 숲의 늑대왕 — 전투는 %s 가 맡는다" % bt_label)
        goto("portal_forest")
        act("interact", target="portal_forest", verb="enter")
        won = False
        for t in range(1, MAX_TRIES + 1):
            if zone() != "forest":
                goto("portal_forest")
                act("interact", target="portal_forest", verb="enter")
            act("move_to", pos=[0, 0, 8])
            r = act("engage", target="wolf_king")
            won = any((cb.ended or {}).get("result", {}).get("cleared") for cb in r.combats)
            if won:
                break
            step("패배 — 다시 도전 (%d/%d)" % (t + 1, MAX_TRIES))
        if won:
            step("마을로 돌아가 경비에게 보고")
            goto("portal_village")
            act("interact", target="portal_village", verb="enter")
            talk_and_choose("npc_guard", 2, near=[30, 0, -30])
        o = c.observe()
        done = [e[2].get("quest") for e in c.get_log()["entries"] if e[1] == "quest_completed"]
        print("\n결과: 완료 퀘스트 %d개 %s, 골드 %s, 남은 퀘스트 %s" % (
            len(done), done, o["player"]["gold"], [q["id"] for q in o["quests"]]))
        c.close()
        input("\n창을 닫고 끝내려면 Enter ▶ ")
        return 0 if won else 1
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
