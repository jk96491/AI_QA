"""직업 JSON 을 임시 패치해 하네스(7791)를 재기동하고 default 평가 + CMA 최적점을 본다 (stable).
python unity_game/QaTools~/try_patch.py <cls> '<patch json>' [budget]
  patch: {"stats":{"armor":0.6}, "skills":{"shield_block":{"cooldown":10}}, "defaults":{"potion_hp":0.36}}
주의: 실행 후 classes/<cls>.json 이 패치된 상태로 남는다 (indent 2 로 다시 씀). 원본은 <cls>.json.bak 으로 처음 한 번 백업.
"""
import json, subprocess, sys, time, os, copy, shutil
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "unity_game", "Assets", "QA", "Data", "Resources", "QaData")
EXE = os.path.join(ROOT, "unity_game", "QaTools~", "harness", "bin", "Release", "net9.0", "Harness.exe")
cls = sys.argv[1]; patch = json.loads(sys.argv[2]); budget = sys.argv[3] if len(sys.argv) > 3 else "1200"
path = os.path.join(DATA, "classes", cls + ".json"); bak = path + ".bak"
if not os.path.exists(bak): shutil.copy(path, bak)
w = copy.deepcopy(json.load(open(bak, encoding="utf-8")))
w["stats"].update(patch.get("stats", {}))
for s in w["skills"]: s.update(patch.get("skills", {}).get(s["name"], {}))
for k, v in patch.get("defaults", {}).items(): w["params"][k]["default"] = v
json.dump(w, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
subprocess.run("taskkill /F /IM Harness.exe", shell=True, capture_output=True)
subprocess.Popen([EXE, DATA, "7791"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.2)
py = os.path.join(ROOT, "venv", "Scripts", "python.exe")
o = subprocess.run([py, "-m", "balance_qa", "--game", "127.0.0.1:7791", "optimize", "--cls", cls, "--persona", "stable",
                    "--budget", budget, "--eval-n", "200"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
def short(line):
    d = eval(line.split(":", 1)[1].strip())
    return "clear=%s deaths=%s t=%s R=%s" % (d["clear_rate"].split()[0], d["deaths"].split()[0], d["effective_time_s"].split()[0], d["reward"].split()[0])
rp = None
for line in o.splitlines():
    if line.startswith("기준선"): print("  default:", short(line))
    if line.startswith("최적화"): print("  cma    :", short(line))
    if line.startswith("리포트"): rp = line.split(":", 1)[1].strip()
if rp:
    p = json.load(open(os.path.join(ROOT, rp, "params.json")))["source"]["params"]
    print("  best   :", json.dumps({k: round(v, 2) for k, v in p.items() if k not in ("survival_hp_threshold", "dps_hp_floor")}))
