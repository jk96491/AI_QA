"""BT-QA SDK(별도 레포 btqa_sdk)에서 **Python 이 아닌 것**(Unity 패키지·계약 문서)을 이 저장소로 복사한다.

Python 패키지(btqa_game·btqa_play)는 복사하지 않는다 — btqa_sdk 를 venv 에 편집 설치해 직접 참조한다
(사용자 결정 2026-11-24, requirements.txt 참고). Unity 는 embedded 패키지라 사본이 필요하고, 계약 문서는 저장소 문서가 가리키는 곳이다.

    원본 (btqa_sdk 레포)                 사본 (이 저장소)
    unity/com.btqa.game/             →  unity_game/Packages/com.btqa.game  Unity embedded 패키지
    docs/PROTOCOL.md                 →  docs/PROTOCOL.md                  계약 문서 (밸런스)
    docs/PLAY_PROTOCOL.md            →  docs/PLAY_PROTOCOL.md             계약 문서 (플레이 모드)

SDK 를 고치는 곳은 원본뿐이다. 원본을 고친 뒤 이 스크립트를 실행하고 (Unity 면 재빌드), 사본을 직접 고치지 않는다.
tests/sdk/test_sdk_copies.py 가 원본이 있을 때 사본과 비교한다 (원본이 없으면 건너뜀).

    venv\\Scripts\\python.exe run/run_sync_sdk.py                 # 복사 (원본에 없는 사본 파일은 삭제)
    venv\\Scripts\\python.exe run/run_sync_sdk.py --check         # 비교만 (다르면 exit 1)
    venv\\Scripts\\python.exe run/run_sync_sdk.py --sdk D:/btqa-sdk   # 원본 위치 (기본: 이 저장소의 btqa_sdk/, 환경변수 BTQA_SDK)
"""
from __future__ import annotations

import filecmp
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {"__pycache__"}
SKIP_SUFFIX = (".pyc", ".pyo")

#: (원본 상대 경로, 사본 경로)
TARGETS: Tuple[Tuple[str, Path], ...] = (
    ("unity/com.btqa.game", ROOT / "unity_game" / "Packages" / "com.btqa.game"),
    ("docs/PROTOCOL.md", ROOT / "docs" / "PROTOCOL.md"),
    ("docs/PLAY_PROTOCOL.md", ROOT / "docs" / "PLAY_PROTOCOL.md"),
)


def sdk_root(arg: Optional[str] = None) -> Path:
    return Path(arg or os.environ.get("BTQA_SDK") or (ROOT / "btqa_sdk")).resolve()


def _files(base: Path) -> List[str]:
    if base.is_file():
        return [""]
    return sorted(
        str(p.relative_to(base)).replace("\\", "/") for p in base.rglob("*")
        if p.is_file() and not (SKIP_PARTS & set(p.parts)) and not p.name.endswith(SKIP_SUFFIX)
    )


def _join(base: Path, rel: str) -> Path:
    return base / rel if rel else base


def differences(sdk: Optional[Path] = None) -> List[str]:
    """원본·사본 차이 (빈 목록 = 같음)."""
    sdk = sdk or sdk_root()
    out: List[str] = []
    for src_rel, dst in TARGETS:
        src = sdk / src_rel
        name = str(dst.relative_to(ROOT))
        if not src.exists():
            out.append("원본 없음: %s" % src)
            continue
        if not dst.exists():
            out.append("사본 없음: %s" % name)
            continue
        a, b = set(_files(src)), set(_files(dst))
        out += ["%s: 사본에 없음 %s" % (name, f) for f in sorted(a - b)]
        out += ["%s: 사본에만 있음 %s" % (name, f) for f in sorted(b - a)]
        out += ["%s: 내용 다름 %s" % (name, f or "") for f in sorted(a & b)
                if not filecmp.cmp(str(_join(src, f)), str(_join(dst, f)), shallow=False)]
    return out


def sync(sdk: Optional[Path] = None) -> List[str]:
    sdk = sdk or sdk_root()
    done: List[str] = []
    for src_rel, dst in TARGETS:
        src = sdk / src_rel
        if not src.exists():
            raise FileNotFoundError("SDK 원본 없음: %s (--sdk 로 위치 지정)" % src)
        name = str(dst.relative_to(ROOT))
        if src.is_file():
            if not dst.exists() or not filecmp.cmp(str(src), str(dst), shallow=False):
                shutil.copy2(str(src), str(dst))
                done.append("복사 %s" % name)
            continue
        for rel in (_files(dst) if dst.exists() else []):
            if not (src / rel).exists():
                (dst / rel).unlink()
                done.append("삭제 %s/%s" % (name, rel))
        for rel in _files(src):
            s, d = src / rel, dst / rel
            if not d.exists() or not filecmp.cmp(str(s), str(d), shallow=False):
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(s), str(d))
                done.append("복사 %s/%s" % (name, rel))
        for d in sorted((p for p in dst.rglob("*") if p.is_dir() and "__pycache__" not in p.parts), key=lambda p: -len(p.parts)):
            if not any(d.iterdir()):
                d.rmdir()
    return done


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    argv = sys.argv[1:]
    sdk = sdk_root(argv[argv.index("--sdk") + 1] if "--sdk" in argv else None)
    print("SDK 원본: %s" % sdk)
    if "--check" in argv:
        diff = differences(sdk)
        print("\n".join(diff) if diff else "같음 (%d곳)" % len(TARGETS))
        return 1 if diff else 0
    done = sync(sdk)
    print("\n".join(done) if done else "변경 없음")
    diff = differences(sdk)
    print("동기화 완료 — Unity 패키지가 바뀌었으면 Unity 를 다시 빌드" if not diff else "남은 차이: %s" % diff)
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
