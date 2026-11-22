"""창 모드 플레이 인스턴스(-qaPlay -qaPort 7800)를 늑대왕까지 몰고 가며 창을 캡처한다 — 전투 장면 전환·연출 육안 확인용.
    python unity_game/QaTools~/play_shots.py <출력 폴더>
예) QaArena.exe -qaPlay -qaPort 7800 -qaPlaySpeed 8 -qaPlayCombatSpeed 60  을 먼저 띄운다.
"""
import os, subprocess, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from play_check import Conn, hello

OUT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else "."
os.makedirs(OUT, exist_ok=True)
PS = r'''
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W { [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out R r);
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 public struct R { public int L, T, Rt, B; } }
"@
$p = Get-Process QaArena | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
[W]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
$r = New-Object W+R; [W]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
$w = $r.Rt - $r.L; $h = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
$bmp.Save("%s"); "$w x $h"
'''


def shot(name):
    path = OUT + "/" + name + ".png"
    r = subprocess.run(["powershell", "-NoProfile", "-Command", PS % path], capture_output=True, text=True)
    print("shot", name, r.stdout.strip(), r.stderr.strip()[:200])


c = Conn("127.0.0.1:7800"); hello(c)
c.rq({"type": "reset", "seed": 5, "class": "warrior"})
time.sleep(1.0); shot("1_village")
c.act("move_to", target="portal_forest"); c.act("interact", target="portal_forest", verb="enter")
c.act("move_to", pos=[0, 0, 8])
time.sleep(0.5); shot("2_forest")

# 전투는 별도 스레드에서 진행, 그동안 시간차로 캡처
res = {}
def fight():
    log = []
    res["r"] = c.act("engage", log=log, target="wolf_king")
    res["log"] = log
t = threading.Thread(target=fight); t.start()
for name, wait in [("3_transition", 0.35), ("4_fight_a", 1.6), ("5_fight_b", 4.0), ("6_fight_c", 5.0)]:
    time.sleep(wait); shot(name)
t.join()
en = next(m for m in res["log"] if m["type"] == "combat_ended")
print("cleared", en["result"]["cleared"], "elapsed", en["result"]["elapsed"], "status", res["r"]["status"])
time.sleep(0.8); shot("7_after")
c.close()
