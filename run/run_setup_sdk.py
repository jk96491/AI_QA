"""[PyCharm ▶ 15] BT-QA SDK 설치·업데이트·확인 (docs/INSTALL.md 3장).

이 저장소의 Python 은 별도 레포 btqa_sdk 를 **직접 참조**한다 (사본 없음). 이 스크립트가 하는 일:
  1. btqa_sdk/ 가 없으면 clone (있으면 그대로, UPDATE=True 면 git pull)
  2. 지금 인터프리터(venv)에 편집 설치: pip install --no-deps --no-build-isolation -e ./btqa_sdk
  3. 확인: 새 프로세스에서 btqa_game·btqa_play 가 btqa_sdk/python 에서 로드되는지, 버전, Unity·문서 사본 일치

여러 번 실행해도 된다. 실행 인터프리터 = 설치 대상 (PyCharm 프로젝트 인터프리터 venv\\Scripts\\python.exe).

    venv\\Scripts\\python.exe run/run_setup_sdk.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _bootstrap import ROOT, setup

# ===================== 설정 =====================
SDK_URL = "https://github.com/jk96491/btqa_sdk.git"
SDK_DIR = ROOT / "btqa_sdk"   # 이 저장소 안 (.gitignore 로 제외됨)
UPDATE = False                # True = 이미 있으면 git pull (SDK 최신으로)
# ================================================

CHECK = r"""
import json, btqa_game, btqa_play
print(json.dumps({"btqa_game": btqa_game.__file__, "btqa_play": btqa_play.__file__,
                  "version": btqa_game.__version__, "play_version": btqa_play.__version__,
                  "protocol": btqa_game.PROTOCOL_VERSION, "play_protocol": btqa_play.PROTOCOL_VERSION}))
"""


def run(cmd, **kw) -> int:
    print(">", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call([str(c) for c in cmd], **kw)


def main() -> int:
    setup()
    py = sys.executable
    print("인터프리터:", py)
    if "venv" not in py.replace("\\", "/").split("/"):
        print("주의: 프로젝트 venv 가 아닌 인터프리터다 — 이 인터프리터에 설치된다 (보통 venv\\Scripts\\python.exe)")

    # 1. clone / pull
    if not (SDK_DIR / "python" / "btqa_game").exists():
        if SDK_DIR.exists() and any(SDK_DIR.iterdir()):
            print("실패: %s 가 있는데 SDK 레포가 아니다 — 비우거나 옮긴 뒤 다시 실행" % SDK_DIR)
            return 1
        if run(["git", "clone", SDK_URL, SDK_DIR]) != 0:
            print("실패: clone (git 설치·네트워크 확인)")
            return 1
    elif UPDATE:
        if run(["git", "-C", SDK_DIR, "pull", "--ff-only"]) != 0:
            print("실패: git pull — btqa_sdk 에 커밋 안 한 변경이 있으면 정리 후 다시")
            return 1
    else:
        print("btqa_sdk 있음 (UPDATE=False → pull 안 함)")

    # 2. 편집 설치 (setuptools < 64 → setup.py develop 경로, --no-build-isolation 필요)
    if run([py, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "-e", SDK_DIR]) != 0:
        print("실패: pip 편집 설치")
        return 1

    # 3. 확인 (새 프로세스, 저장소 밖 폴더에서 — 방금 설치한 경로가 보이는지. 저장소 루트가 끼어들지 않게)
    out = subprocess.run([py, "-c", CHECK], cwd=str(ROOT.parent), capture_output=True, text=True)
    if out.returncode != 0:
        print("실패: import 확인\n" + out.stderr)
        return 1
    info = json.loads(out.stdout.strip().splitlines()[-1])
    want = (SDK_DIR / "python").resolve()
    ok = True
    for name in ("btqa_game", "btqa_play"):
        loc = Path(info[name]).resolve().parent.parent
        good = loc == want
        ok &= good
        print("[%s] %s ← %s" % ("OK" if good else "FAIL", name, loc))
    good = info["version"] == info["play_version"]
    ok &= good
    print("[%s] SDK %s (btqa_play %s), 밸런스 프로토콜 %s, 플레이 프로토콜 %s"
          % ("OK" if good else "FAIL", info["version"], info["play_version"], info["protocol"], info["play_protocol"]))
    pkg = json.loads((ROOT / "unity_game" / "Packages" / "com.btqa.game" / "package.json").read_text(encoding="utf-8"))
    good = pkg["version"] == info["version"]
    ok &= good
    print("[%s] Unity 패키지 사본 %s%s" % ("OK" if good else "FAIL", pkg["version"],
                                      "" if good else " — run/run_sync_sdk.py 로 사본 갱신 (Unity 재빌드)"))
    if run([py, str(ROOT / "run" / "run_sync_sdk.py"), "--check"]) != 0:
        ok = False
        print("[FAIL] 사본(Unity 패키지·docs/PROTOCOL.md·docs/PLAY_PROTOCOL.md) ≠ SDK — run/run_sync_sdk.py")
    print("\n" + ("완료 — PyCharm 빨간 줄이 남으면 docs/INSTALL.md 4장" if ok else "확인 실패 — 위 FAIL 참고 (docs/INSTALL.md 5장)"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
