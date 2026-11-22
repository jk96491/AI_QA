"""TMP Essential Resources(.unitypackage = tar.gz)를 Assets/TextMesh Pro/ 로 직접 푼다 (한 번만).
AssetDatabase.ImportPackage 는 비동기라 batchmode 빌드 안에서는 끝나지 않기 때문.
    python unity_game/QaTools~/import_tmp_essentials.py      (unity_game 폴더 기준 경로 자동)
"""
import glob
import os
import tarfile

game = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
pkgs = glob.glob(os.path.join(game, "Library", "PackageCache", "com.unity.ugui@*", "Package Resources", "TMP Essential Resources.unitypackage"))
if not pkgs:
    raise SystemExit("com.unity.ugui 패키지 캐시 없음 — 프로젝트를 Unity 로 한 번 연 뒤 실행")
t = tarfile.open(pkgs[0], "r:gz")
ent = {}
for m in t.getmembers():
    parts = m.name[2:].split("/") if m.name.startswith("./") else m.name.split("/")
    if len(parts) == 2 and parts[1] in ("asset", "asset.meta", "pathname"):
        ent.setdefault(parts[0], {})[parts[1]] = m
n = 0
for d in ent.values():
    rel = t.extractfile(d["pathname"]).read().decode("utf-8").splitlines()[0].strip()
    if not rel.startswith("Assets/TextMesh Pro"):
        raise SystemExit("예상 밖 경로: " + rel)
    path = os.path.join(game, rel)
    if "asset" in d:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(t.extractfile(d["asset"]).read())
        n += 1
    else:
        os.makedirs(path, exist_ok=True)
    if "asset.meta" in d:
        with open(path + ".meta", "wb") as f:
            f.write(t.extractfile(d["asset.meta"]).read())
print("TMP Essential Resources: %d files -> %s" % (n, os.path.join(game, "Assets", "TextMesh Pro")))
