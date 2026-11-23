"""[PyCharm ▶] 학습 결과를 Unity 화면으로 보기 — 학습 없이, 저장된 결과를 바로 재생.

reports/ 에서 가장 최근 결과(CMA-ES params.json, IMPALA policy.json)를 찾아, 같은 seed 판을
Unity 창에 나란히 보낸다:  창 1 = 손 튜닝(정의서 default)  |  창 2 = CMA-ES  |  창 3 = IMPALA 정책
창은 화면에 나란히 배치되고, 각 창의 전투 뷰어가 그 판을 재생한다 (결정성 — 같은 seed·params → 같은 전투).

조작: 콘솔에서 Enter = 다음 seed, q + Enter = 종료.  창에서 숫자키 1~6 = 0.5x~16x 배속, Tab = 패널.
결과가 없으면 손 튜닝만 보인다 — 먼저 `run/run_full_cycle.py` (Unity) 나 `run/run_measure_build.py` 로 학습해 둔다.
학습하면서 보려면 `run/run_full_cycle_view.py`.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from _bootstrap import ROOT, UNITY, setup

# ===================== 설정 =====================
CLASS = "warrior"         # warrior | mage | archer (archer 는 손 튜닝도 거의 완벽해서 차이가 작다)
SCENARIO = "base"         # describe 의 시나리오 (예: patch_boss_fast, forest_wolf_king)
PERSONA = "stable"        # 손 튜닝 판의 페르소나 설정값 (학습 결과 판은 그 결과의 페르소나)
CMA_RESULT = "latest"     # "latest" = reports/ 에서 자동 / reports/<run> 또는 params.json 경로 / None = 보지 않음
IMPALA_RESULT = "latest"  # "latest" / reports/<run> 또는 policy.json 경로 / None
SEEDS = None              # None = 평가 시드 차례로 / [11, 222] 처럼 지정
VIEW_SPEED = 4            # 재생 배속 (0.5 1 2 4 8 16). 6분 전투 = 4배속 약 1.5분
AUTO_NEXT = False         # True = 재생이 끝날 즈음 자동으로 다음 seed (Enter 없이)
VIEW_SIZE = None          # 창 크기 (가로, 세로). None = 화면 너비를 창 수로 나눔
# ================================================

REPORTS = ROOT / "reports"


def find_result(kind: str, spec: Optional[str], game_version: str) -> Tuple[Optional[Path], str]:
    """→ (파일, 메모). kind = 'cma' | 'impala'."""
    if spec is None:
        return None, "보지 않음 (설정 None)"
    name = "params.json" if kind == "cma" else "policy.json"
    if spec != "latest":
        p = (ROOT / spec) if not Path(spec).is_absolute() else Path(spec)
        p = p / name if p.is_dir() else p
        return (p, "지정") if p.exists() else (None, "파일 없음: %s" % p)
    same, other = None, None
    for run in sorted(REPORTS.iterdir()) if REPORTS.exists() else []:
        f = run / name
        if not f.exists():
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if d.get("class") != CLASS or (d.get("scenario") or "base") != SCENARIO or d.get("method") != kind:
            continue
        if (d.get("game") or {}).get("version") == game_version:
            same = f
        other = f
    if same:
        return same, "현재 빌드 %s 결과" % game_version
    if other:
        return other, "주의: 다른 빌드의 결과 (현재 %s) — 다시 학습 권장" % game_version
    return None, "%s/%s 의 %s 결과가 reports/ 에 없음" % (CLASS, SCENARIO, kind)


def impala_source(path: Path):
    """policy.json → balance_qa ParamSource (play_agent 의 numpy 정책 실행기 사용, torch 불필요)."""
    from balance_qa.control.param_source import ParamSource
    from play_agent.responder import ImpalaPolicy

    pol = ImpalaPolicy.from_file(path)

    class PolicySource(ParamSource):
        trigger_thresholds = tuple(pol.thresholds)

        def base_params(self) -> Dict[str, float]:
            return dict(pol.fixed)

        def on_trigger(self, state) -> Dict[str, float]:
            return pol({"index": state.index, "state": dict(state.state)})

        def describe(self):
            return {"type": "impala-policy-file", "path": str(path)}

    return PolicySource()


def tile_windows(pids: List[int], size: Optional[Tuple[int, int]], titles: List[str]) -> None:
    """Unity 창을 왼쪽부터 나란히 배치하고 제목을 붙인다 (Windows 만, 실패해도 무시)."""
    if sys.platform != "win32" or not pids:
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: Dict[int, int] = {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd) and pid.value not in found:
            found[pid.value] = hwnd
        return True

    deadline = time.time() + 20
    while len(found) < len(pids) and time.time() < deadline:
        user32.EnumWindows(enum, 0)
        time.sleep(0.3)
    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    w, h = size or (sw // len(pids), int(sw // len(pids) * 9 / 16))
    for i, pid in enumerate(pids):
        if pid in found:
            user32.MoveWindow(found[pid], i * w, max(0, (sh - h) // 3), w, h, True)
            if i < len(titles):
                user32.SetWindowTextW(found[pid], "QaArena — %d. %s" % (i + 1, titles[i]))


def main() -> int:
    setup()
    from balance_qa.control.param_source import StaticParamSource
    from balance_qa.game_api.client import EpisodeRequest
    from balance_qa.game_api.launcher import view_command_from
    from balance_qa.runner.seed_pool import EVAL_SEEDS
    from balance_qa.session import QASession

    exe = ROOT / "unity_game" / "Build" / "QaArena.exe"
    if not exe.exists():
        print("Unity 빌드가 없음: %s (unity_game 에서 빌드 먼저)" % exe)
        return 1

    # 결과 파일 먼저 찾고 (창 수를 정하려고), 게임 버전은 창을 띄운 뒤 describe 로 확인
    probe_version = ""
    try:
        probe_version = json.loads((ROOT / "unity_game/Assets/QA/Data/Resources/QaData/game.json").read_text(encoding="utf-8"))["game_version"]
    except (OSError, ValueError, KeyError):
        pass
    cma_path, cma_note = find_result("cma", CMA_RESULT, probe_version)
    imp_path, imp_note = find_result("impala", IMPALA_RESULT, probe_version)
    print("결과 파일:")
    print("  CMA-ES : %s  (%s)" % (cma_path.relative_to(ROOT) if cma_path else "-", cma_note))
    print("  IMPALA : %s  (%s)" % (imp_path.relative_to(ROOT) if imp_path else "-", imp_note))

    def persona_of(path: Path) -> str:
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("persona", "?")
        except (OSError, ValueError):
            return "?"

    titles = ["손 튜닝 (%s)" % PERSONA]
    if cma_path:
        titles.append("CMA-ES (%s)" % persona_of(cma_path))
    if imp_path:
        titles.append("IMPALA (%s)" % persona_of(imp_path))
    runs = len(titles)
    headless = UNITY.split() + ["-qaFollow", "-qaViewSpeed", str(VIEW_SPEED), "-qaPanel", "0"]
    with QASession(game_command=UNITY.split(), spawn=runs, view=runs,
                   view_command=view_command_from(headless, VIEW_SIZE or (1280, 720))) as s:
        tile_windows([p.pid for p in s.launcher.procs], VIEW_SIZE, titles)
        print("\n게임: %s %s, 직업 %s, 시나리오 %s, 창 %d개, %s배속" % (
            s.game.game, s.game.game_version, CLASS, SCENARIO, runs, VIEW_SPEED))

        sources = [(titles[0], StaticParamSource(s.base_params(CLASS, PERSONA)))]
        if cma_path:
            sources.append((titles[1], StaticParamSource(json.loads(cma_path.read_text(encoding="utf-8"))["source"]["params"])))
        if imp_path:
            try:
                sources.append((titles[-1], impala_source(imp_path)))
            except Exception as exc:  # 예전 형식 policy.json 등 — 그 창은 비워 둔다
                print("  IMPALA 정책을 불러오지 못함: %s" % exc)
        viewers = s.view_clients

        seeds = list(SEEDS) if SEEDS else list(EVAL_SEEDS.first(50))
        for n, seed in enumerate(seeds, 1):
            print("\n[%d] seed %d" % (n, seed))
            longest = 0.0
            for i, (label, src) in enumerate(sources):
                r = viewers[i].run_episode(EpisodeRequest(CLASS, seed, scenario=SCENARIO), src)
                longest = max(longest, r.elapsed)
                print("  창 %d %-18s %s  %5.0fs  사망 %d  물약 %d%s" % (
                    i + 1, label, "클리어" if r.cleared else "실패  ", r.elapsed, r.deaths, r.consumables_used,
                    "  (멈춤)" if r.stalled else ""), flush=True)
            if AUTO_NEXT:
                wait = longest / max(0.5, VIEW_SPEED) + 3
                print("  재생 중… %.0f초 뒤 다음 seed (Ctrl+C 종료)" % wait, flush=True)
                time.sleep(wait)
            elif input("  재생을 보고 Enter = 다음 seed, q = 종료 ▶ ").strip().lower() == "q":
                break
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
