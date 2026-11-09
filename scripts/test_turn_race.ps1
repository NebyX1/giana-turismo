# GIANA TURN RACE QUALITY GATE
# Ejecuta: order A, order B, timing permutations, 100 repetitions, generation lifecycle.
# exit 0 SOLO si todo pasa.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw 'Falta .venv\Scripts\python.exe' }
$env:GIANA_DIAGNOSTICS = 'true'
$env:PYTHONUTF8 = '1'
& $py 'scripts\test_turn_race.py'
if ($LASTEXITCODE -ne 0) {
  Write-Output 'TURN_RACE_QUALITY_GATE: FAIL'
  exit 1
}
Write-Output 'TURN_RACE_QUALITY_GATE: PASS'
exit 0