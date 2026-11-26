"""[PyCharm ▶ 17] 로컬 LLM 플레이를 녹화 (Windows) — run_play_local.py 를 띄우고 게임 창만 찍어 mp4 + 대기 제거 mp4 + gif.

- 게임 창(클라이언트 영역)을 화면에서 복사한다 → 녹화 중 게임 창을 맨 위에 고정 (매초 다시 찾아 고정 — Unity 는 시작 중 창을 다시 만든다).
  녹화 중에는 다른 창을 그 위로 올리지 말 것. (PrintWindow 는 DirectX 창에서 빈 화면이라 쓰지 않는다)
- 대기 제거: 이 게임은 플레이어가 행동할 때만 세계가 흐른다 → LLM 응답을 기다리는 동안 화면이 멈춰 있다 → 같은 프레임을 떨군다 (mpdecimate).
- ffmpeg: 환경변수 FFMPEG → PATH 의 ffmpeg → (있으면) imageio_ffmpeg 순서로 찾는다. 프로젝트 의존성은 늘리지 않는다.
- 출력: reports/recordings/<이름>.mp4 (원본 속도) · <이름>_skip.mp4 (대기 제거) · <이름>.gif (대기 제거본 2배속, 폭 640) · <이름>.log (콘솔)
  reports/ 는 git 제외.

    venv\\Scripts\\python.exe run/run_record_play.py --model qa-qwen1.5b-r8 --seed 1
"""
from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Optional

from _bootstrap import ROOT, setup

# ===================== 설정 =====================
MODEL = "qa-qwen1.5b-r8"     # run_play_local.py 의 MODEL 과 같은 뜻 (CPU 전용 변형 / GPU 는 "-gpu" 변형)
SEED = 1
NAME = None                  # 출력 이름 (None = <모델>_seed<seed>)
FPS = 15
GIF_SPEED = 2                # GIF 배속 (대기 제거본 기준)
GIF_WIDTH = 640
WINDOW_TITLE = "QaArena"
# ================================================

OUT_DIR = ROOT / "reports" / "recordings"


def find_ffmpeg() -> str:
    if os.environ.get("FFMPEG"):
        return os.environ["FFMPEG"]
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit("ffmpeg 를 찾지 못함 — PATH 에 두거나 환경변수 FFMPEG 로 지정 (또는 다른 venv 의 pip install imageio-ffmpeg)")


class Window:
    """Win32 창 찾기·맨 위 고정·클라이언트 영역 화면 복사 (ctypes, 표준 라이브러리만)."""

    def __init__(self) -> None:
        self.u32 = ctypes.windll.user32
        self.g32 = ctypes.windll.gdi32
        self.u32.SetProcessDPIAware()
        self.h = None
        self._dc = None

    def find(self, title: str) -> Optional[int]:
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(h, _):
            buf = ctypes.create_unicode_buffer(256)
            self.u32.GetWindowTextW(h, buf, 256)
            if buf.value == title and self.u32.IsWindowVisible(h):
                found.append(h)
            return True
        self.u32.EnumWindows(cb, 0)
        return found[0] if found else None

    def size(self, h) -> tuple:
        r = wintypes.RECT()
        self.u32.GetClientRect(h, ctypes.byref(r))
        return r.right - r.left, r.bottom - r.top

    def origin(self, h) -> tuple:
        p = wintypes.POINT(0, 0)
        self.u32.ClientToScreen(h, ctypes.byref(p))
        return p.x, p.y

    def topmost(self, h, on: bool = True) -> None:
        self.u32.SetWindowPos(h, -1 if on else -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)

    def start_grab(self, w: int, h: int) -> None:
        class BMI(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
        self.w, self.ht = w, h
        self.sdc = self.u32.GetDC(0)
        self.mdc = self.g32.CreateCompatibleDC(self.sdc)
        self.bmp = self.g32.CreateCompatibleBitmap(self.sdc, w, h)
        self.g32.SelectObject(self.mdc, self.bmp)
        self.bi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        self.buf = ctypes.create_string_buffer(w * h * 4)

    def grab(self, x: int, y: int) -> bytes:
        self.g32.BitBlt(self.mdc, 0, 0, self.w, self.ht, self.sdc, x, y, 0x00CC0020)   # SRCCOPY
        self.g32.GetDIBits(self.mdc, self.bmp, 0, self.ht, self.buf, ctypes.byref(self.bi), 0)
        return self.buf.raw


def main() -> int:
    setup()
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--name", default=NAME)
    ap.add_argument("--history", type=int, default=0, help="그 모델이 학습한 recent_actions 개수 (r15~ = 4)")
    a = ap.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Windows 전용 (Win32 화면 복사)")
    ff = find_ffmpeg()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = OUT_DIR / (a.name or "%s_seed%d" % (a.model, a.seed))
    log = open(str(stem) + ".log", "w", encoding="utf-8")
    play = subprocess.Popen([sys.executable, "-u", str(ROOT / "run" / "run_play_local.py"), "--model", a.model, "--seed", str(a.seed),
                             "--history", str(a.history)],
                            cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    win = Window()
    h = None
    for _ in range(240):
        h = win.find(WINDOW_TITLE)
        if h and win.size(h)[0] >= 640:
            break
        time.sleep(0.5)
    if not h:
        play.terminate()
        raise SystemExit("게임 창을 찾지 못함 (%s)" % WINDOW_TITLE)
    w, ht = win.size(h)
    win.topmost(h)
    win.u32.SetForegroundWindow(h)
    time.sleep(1)
    mp4 = str(stem) + ".mp4"
    rec = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", "%dx%d" % (w, ht), "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", mp4],
                           stdin=subprocess.PIPE)
    win.start_grab(w, ht)
    stop = threading.Event()
    state = {"h": h}

    def loop() -> None:
        nxt, last_fix = time.time(), 0.0
        while not stop.is_set():
            now = time.time()
            if now - last_fix > 1.0:
                hh = win.find(WINDOW_TITLE)
                if hh:
                    state["h"] = hh
                    win.topmost(hh)
                last_fix = now
            x, y = win.origin(state["h"])
            rec.stdin.write(win.grab(x, y))
            nxt += 1.0 / FPS
            time.sleep(max(0.0, nxt - time.time()))

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    print("녹화 중 %s (%dx%d) — 끝날 때까지 게임 창 위로 다른 창을 올리지 말 것" % (mp4, w, ht), flush=True)
    try:
        play.wait()
        time.sleep(4)   # 마지막 화면
    finally:
        stop.set()
        th.join()
        rec.stdin.close()
        rec.wait()
        win.topmost(state["h"], False)
        log.close()
    skip = str(stem) + "_skip.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", mp4, "-vf", "mpdecimate=hi=768:lo=320:frac=0.5,setpts=N/%d/TB" % FPS,
                    "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-an", skip], check=True)
    gif = str(stem) + ".gif"
    vf = ("setpts=PTS/%d,fps=10,scale=%d:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer"
          % (GIF_SPEED, GIF_WIDTH))
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", skip, "-vf", vf, gif], check=True)
    for f in (mp4, skip, gif):
        print("%s  %.1f MB" % (f, Path(f).stat().st_size / 1e6))
    tail = Path(str(stem) + ".log").read_text(encoding="utf-8").strip().splitlines()
    print(next((x for x in reversed(tail) if x.startswith("끝:")), tail[-1] if tail else ""))
    return play.returncode or 0


if __name__ == "__main__":
    sys.exit(main())
