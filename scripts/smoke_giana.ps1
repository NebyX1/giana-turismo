$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
function Get-Json($url) { Invoke-RestMethod $url -TimeoutSec 10 }
Get-Json 'http://127.0.0.1:5000/health' | Out-Host
Get-Json 'http://127.0.0.1:5000/ready' | Out-Host
Get-Json 'http://127.0.0.1:6333/collections/giana_granite_v2' | Out-Host
$wav = Join-Path $Root 'logs\piper_smoke_script.wav'
curl.exe -sS -X POST -H 'Content-Type: application/json' --data-binary '{"text":"Hola, soy Giana."}' 'http://127.0.0.1:5001/synthesize' -o $wav
if ((Get-Item $wav).Length -le 44) { throw 'Piper no generó un WAV válido.' }
foreach ($q in '¿Dónde puedo comer algo vegano en Minas?','¿Qué puedo hacer en Minas un día de lluvia?') {
  $body = @{question=$q;session_id='windows-smoke';generation_id=[guid]::NewGuid().ToString()} | ConvertTo-Json
  $result = Invoke-RestMethod 'http://127.0.0.1:5000/api/ask-text' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 90
  if ($result.state -ne 'ANSWERABLE') { throw "RAG no answerable: $q" }
  $result | Select-Object state,route,answer | Out-Host
}
if (-not (Get-NetTCPConnection -LocalPort 7860 -State Listen -ErrorAction SilentlyContinue)) { throw 'SmallWebRTC no está escuchando.' }
if ((Invoke-WebRequest 'http://127.0.0.1:5173/' -UseBasicParsing).StatusCode -ne 200) { throw 'Frontend no responde.' }
Write-Output 'SMOKE GIANA PASS; la prueba de micrófono real queda pendiente del usuario.'
