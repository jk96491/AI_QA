# 밸런스 측정: .NET 하네스를 (재)빌드·기동하고 직업별 손 튜닝 default 성능을 학습 쪽 evaluate 로 본다.
#   pwsh unity_game/QaTools~/tune.ps1 [-n 300] [-personas stable,aggressive] [-port 7791] [-keep]
# 데이터(JSON)는 하네스 기동 시 읽으므로, 값을 바꾼 뒤 다시 실행하면 반영된다. -keep 이면 하네스를 띄운 채로 둔다
# (그동안 optimize / peek.py / retune.py 를 같은 포트로 돌릴 수 있다).
param([int]$n = 200, [string[]]$personas = @('stable'), [int]$port = 7791, [switch]$keep)
$ErrorActionPreference = 'Stop'
$tools = $PSScriptRoot
$game = Resolve-Path (Join-Path $tools '..')
$root = Resolve-Path (Join-Path $game '..')
$h = Join-Path $tools 'harness'

Get-Process Harness -ErrorAction SilentlyContinue | Stop-Process -Force
$b = dotnet build (Join-Path $h 'Harness.csproj') -c Release -nologo -v q 2>&1 | Select-String -Pattern ' error ' | Select-Object -Unique
if ($b) { $b; exit 1 }
$exe = Get-ChildItem -Recurse (Join-Path $h 'bin\Release') -Filter Harness.exe | Select-Object -First 1 -ExpandProperty FullName
$data = Join-Path $game 'Assets\QA\Data\Resources\QaData'
$null = Start-Process -FilePath $exe -ArgumentList "`"$data`"", "$port" -PassThru -NoNewWindow `
    -RedirectStandardOutput (Join-Path $h 'out.txt') -RedirectStandardError (Join-Path $h 'err.txt')
Start-Sleep -Milliseconds 1200

Push-Location $root
try {
  foreach ($per in $personas) {
    foreach ($c in 'warrior','mage','archer') {
      $o = & venv\Scripts\python.exe -m balance_qa --game "127.0.0.1:$port" evaluate --cls $c --persona $per -n $n 2>&1
      $d = ($o | Select-String -Pattern "'clear_rate'" | Select-Object -First 1).Line
      if ($d -match "clear_rate': '([^']*)'.*effective_time_s': '([^ ]*) .*stalled': '([^ ]*) .*deaths': '([^ ]*) ") {
        "{0,-8} {1,-10} clear={2,-20} eff_t={3,-7} stalled={4,-5} deaths={5}" -f $c,$per,$Matches[1],$Matches[2],$Matches[3],$Matches[4]
      } else { "$c $per : $d"; $o | Select-Object -Last 5 }
    }
  }
} finally {
  Pop-Location
  if (-not $keep) { Get-Process Harness -ErrorAction SilentlyContinue | Stop-Process -Force }
}
Get-Content (Join-Path $h 'err.txt') -ErrorAction SilentlyContinue | Select-Object -First 5
