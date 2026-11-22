# Unity 명령행 빌드 → Build/QaArena.exe  (에디터가 이 프로젝트를 열고 있으면 실패한다)
#   pwsh unity_game/QaTools~/build.ps1 [-check]     -check: 빌드 후 7777 로 띄워 check-game + edge_cases 실행
param([switch]$check, [string]$unity = 'C:\Program Files\Unity\Hub\Editor\6000.0.60f1\Editor\Unity.exe')
$game = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$root = (Resolve-Path (Join-Path $game '..')).Path
if (Test-Path (Join-Path $game 'Temp\UnityLockfile')) {
  if (@(Get-Process Unity -ErrorAction SilentlyContinue).Count -gt 0) { Write-Error "Unity 에디터가 프로젝트를 열고 있음 — 닫거나 메뉴 QA > Build Windows 사용"; exit 1 }
}
Get-Process QaArena -ErrorAction SilentlyContinue | Stop-Process -Force
New-Item -ItemType Directory -Force (Join-Path $game 'Logs') | Out-Null
$log = Join-Path $game 'Logs\build.log'
$p = Start-Process -FilePath $unity -ArgumentList @('-batchmode','-quit','-projectPath',"`"$game`"",'-executeMethod','Qa.EditorTools.QaBuild.BuildWindows','-logFile',"`"$log`"") -Wait -PassThru -NoNewWindow
"build exit=$($p.ExitCode)"
Select-String -Path $log -Pattern 'error CS|warning CS|\[QaBuild\]' | ForEach-Object Line | Select-Object -Unique
if ($p.ExitCode -ne 0 -or -not $check) { exit $p.ExitCode }

$exe = Join-Path $game 'Build\QaArena.exe'
$plog = '"' + (Join-Path $game 'Logs\player7777.log') + '"'   # 경로에 공백이 있을 수 있음
$null = Start-Process -FilePath $exe -ArgumentList '-batchmode','-nographics','-qaPort','7777','-logFile',$plog -PassThru -RedirectStandardOutput (Join-Path $game 'Logs\stdout7777.txt')
$t = Get-Date
while (((Get-Date) - $t).TotalSeconds -lt 30) { try { $c = New-Object Net.Sockets.TcpClient('127.0.0.1', 7777); $c.Close(); break } catch { Start-Sleep -Milliseconds 200 } }
Push-Location $root
try {
  & venv\Scripts\python.exe -m balance_qa --game 127.0.0.1:7777 check-game
  & venv\Scripts\python.exe (Join-Path $PSScriptRoot 'edge_cases.py') --game 127.0.0.1:7777 | Select-String -Pattern 'FAIL|결과'
} finally {
  Pop-Location
  Get-Process QaArena -ErrorAction SilentlyContinue | Stop-Process -Force
}
