$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$qaSessionId = ''
if (Test-Path (Join-Path $Root 'logs\test\CURRENT_QA_SESSION_ID.txt')) { $qaSessionId = (Get-Content (Join-Path $Root 'logs\test\CURRENT_QA_SESSION_ID.txt') -Raw).Trim() }
$py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw 'Falta .venv; ejecutá la instalación del proyecto.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker no está instalado.' }
docker compose up -d qdrant | Out-Host
for($i=0;$i -lt 60;$i++){ try { if((Invoke-WebRequest 'http://127.0.0.1:6333/readyz' -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200){break} } catch {}; Start-Sleep 2 }
if (-not (Invoke-WebRequest 'http://127.0.0.1:6333/readyz' -UseBasicParsing).StatusCode -eq 200) { throw 'Qdrant no llegó a ready.' }
$exists = $false; try { $exists = [bool](Invoke-RestMethod 'http://127.0.0.1:6333/collections/giana_granite_v2' -TimeoutSec 5) } catch {}
if (-not $exists) { & $py scripts\index_qdrant.py }
if (-not (Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue)) {
  $model = (Get-ChildItem models\piper -Filter '*.onnx' | Select-Object -First 1).FullName
  Start-Process $py -ArgumentList "-m piper.http_server --host 127.0.0.1 --port 5001 --model `"$model`"" -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $Root 'logs\piper.log') -RedirectStandardError (Join-Path $Root 'logs\piper.err')
}
if (-not (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue)) {
  $env:GIANA_DIAGNOSTICS='true'; $env:QA_SESSION_ID=$qaSessionId
  Start-Process $py -ArgumentList '-m backend.app.main' -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $Root 'logs\backend.log') -RedirectStandardError (Join-Path $Root 'logs\backend.err')
}
for($i=0;$i -lt 90;$i++){ try { if((Invoke-WebRequest 'http://127.0.0.1:5000/ready' -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200){break} } catch {}; Start-Sleep 2 }
if (-not (Get-NetTCPConnection -LocalPort 7860 -State Listen -ErrorAction SilentlyContinue)) {
  $env:PYTHONUTF8='1'; $env:GIANA_DIAGNOSTICS='true'; $env:GIANA_TRACE_SOURCE='human'; $env:QA_SESSION_ID=$qaSessionId
  Start-Process $py -ArgumentList '-m voice.bot -t webrtc' -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $Root 'logs\voice.log') -RedirectStandardError (Join-Path $Root 'logs\voice.err')
}
if (-not (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)) { Start-Process 'npm.cmd' -ArgumentList @('run','dev','--','--host=0.0.0.0') -WorkingDirectory (Join-Path $Root 'frontend') -RedirectStandardOutput (Join-Path $Root 'logs\frontend.log') -RedirectStandardError (Join-Path $Root 'logs\frontend.err') }
Write-Output 'Giana iniciada.'
Write-Output 'Frontend: http://localhost:5173'
Write-Output 'Debug:    http://localhost:5173/?debug=1'
Write-Output 'Backend:  http://localhost:5000'
Write-Output 'Voice:    http://localhost:7860'
Write-Output 'Qdrant:   http://localhost:6333'
