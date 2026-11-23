"""창 캡처 도우미 (play_shots.py 와 같은 PowerShell 방식)."""
import subprocess
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




def shot(out, name):
    path = out + "/" + name + ".png"
    r = subprocess.run(["powershell", "-NoProfile", "-Command", PS % path], capture_output=True, text=True)
    print("shot", name, r.stdout.strip(), r.stderr.strip()[:200])
