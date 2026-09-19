# Puesta en producción ordenada de Giana (Windows).
# Cada servicio se levanta y se verifica FUNCIONALMENTE antes de pasar al siguiente.
# Orden: Qdrant -> Piper -> Backend -> Voz -> Frontend. La interfaz sólo abre al final.
[CmdletBinding()]
param(
    [switch]$Dev,                 # Frontend con Vite dev server en lugar de build + preview.
    [int]$BackendTimeoutSec = 300,
    [int]$VoiceTimeoutSec = 120
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$Py = Join-Path $Root '.venv\Scripts\python.exe'
$Logs = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Started = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Step([string]$Message) { Write-Host "[GIANA] $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message)   { Write-Host "[GIANA]   OK  $Message" -ForegroundColor Green }

function Stop-Started {
    foreach ($proc in $Started) {
        if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    }
}

function Fail([string]$Message) {
    Write-Host "[GIANA] ERROR: $Message" -ForegroundColor Red
    Write-Host "[GIANA] Deteniendo los servicios que este script levantó." -ForegroundColor Red
    Stop-Started
    exit 1
}

function Wait-Until([scriptblock]$Check, [int]$TimeoutSec, [string]$What) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try { if (& $Check) { return $true } } catch { }
        Start-Sleep -Seconds 2
    }
    Fail "$What no respondió correctamente en $TimeoutSec s."
}

function Port-Listening([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Start-Service-Process([string]$Name, [string]$File, [string[]]$Arguments, [string]$WorkDir, [hashtable]$Env) {
    foreach ($key in $Env.Keys) { Set-Item -Path "Env:$key" -Value $Env[$key] }
    $proc = Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $WorkDir -PassThru `
        -RedirectStandardOutput (Join-Path $Logs "$Name.log") -RedirectStandardError (Join-Path $Logs "$Name.err")
    $Started.Add($proc)
    return $proc
}

# ---------- Requisitos ----------
Write-Step 'Verificando requisitos'
if (-not (Test-Path $Py)) { Fail 'Falta .venv\Scripts\python.exe. Instalá el entorno primero.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'Docker no está instalado o no está en PATH.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail 'npm no está instalado o no está en PATH.' }
if (-not (Test-Path (Join-Path $Root '.env'))) { Fail 'Falta .env en la raíz (OLLAMA_API_KEY es obligatoria).' }
if (-not (Select-String -Path (Join-Path $Root '.env') -Pattern '^OLLAMA_API_KEY=.+' -Quiet)) { Fail 'OLLAMA_API_KEY no está definida en .env.' }
$PiperModel = Get-ChildItem (Join-Path $Root 'models\piper') -Filter '*.onnx' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $PiperModel) { Fail 'No hay modelo Piper (*.onnx) en models\piper.' }
if (-not (Test-Path (Join-Path $Root 'data\generated\giana.sqlite3'))) { Fail 'Falta data\generated\giana.sqlite3. Ejecutá scripts\ingest.py.' }
Write-Ok 'requisitos'

# ---------- 1. Qdrant ----------
Write-Step '1/5 Qdrant'
docker compose up -d qdrant | Out-Null
Wait-Until { (Invoke-WebRequest 'http://127.0.0.1:6333/readyz' -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } 90 'Qdrant'
$collection = $null
try { $collection = Invoke-RestMethod 'http://127.0.0.1:6333/collections/giana_granite_v2' -TimeoutSec 5 } catch { }
if (-not $collection -or $collection.result.points_count -lt 1) {
    Write-Step 'Colección ausente o vacía: indexando'
    $env:HF_HUB_OFFLINE = '1'
    & $Py scripts\index_qdrant.py
    if ($LASTEXITCODE -ne 0) { Fail 'La indexación en Qdrant falló.' }
    $collection = Invoke-RestMethod 'http://127.0.0.1:6333/collections/giana_granite_v2' -TimeoutSec 5
}
Write-Ok "Qdrant listo ($($collection.result.points_count) vectores)"

# ---------- 2. Piper ----------
Write-Step '2/5 Piper TTS'
if (-not (Port-Listening 5001)) {
    Start-Service-Process 'piper' $Py @('-m', 'piper.http_server', '--host', '127.0.0.1', '--port', '5001', '--model', $PiperModel.FullName) $Root @{} | Out-Null
}
Wait-Until {
    $resp = Invoke-WebRequest 'http://127.0.0.1:5001/synthesize' -Method Post -ContentType 'application/json' -Body '{"text":"Hola"}' -UseBasicParsing -TimeoutSec 15
    $resp.StatusCode -eq 200 -and $resp.RawContentLength -gt 1000
} 90 'Piper (síntesis de prueba)'
Write-Ok 'Piper sintetiza audio'

# ---------- 3. Backend ----------
Write-Step '3/5 Backend RAG (carga modelos CUDA; puede tardar)'
if (-not (Port-Listening 5000)) {
    Start-Service-Process 'backend' $Py @('-m', 'backend.app.main') $Root @{ GIANA_DIAGNOSTICS = 'true'; PYTHONUTF8 = '1'; HF_HUB_OFFLINE = '1' } | Out-Null
}
Wait-Until { (Invoke-WebRequest 'http://127.0.0.1:5000/ready' -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } $BackendTimeoutSec 'Backend /ready'
$probe = Invoke-RestMethod 'http://127.0.0.1:5000/api/ask-text' -Method Post -ContentType 'application/json' -Body '{"question":"hola","session_id":"startup-probe","source":"probe"}' -TimeoutSec 30
if (-not $probe.answer) { Fail 'El backend respondió /ready pero no contesta preguntas.' }
Write-Ok 'Backend responde consultas'

# ---------- 4. Voz ----------
Write-Step '4/5 Servidor de voz (Pipecat)'
if (-not (Port-Listening 7860)) {
    Start-Service-Process 'voice' $Py @('-m', 'voice.bot', '-t', 'webrtc') $Root @{ GIANA_DIAGNOSTICS = 'true'; GIANA_TRACE_SOURCE = 'human'; PYTHONUTF8 = '1'; PIPER_URL = 'http://127.0.0.1:5001/synthesize'; BACKEND_URL = 'http://127.0.0.1:5000' } | Out-Null
}
Wait-Until {
    $start = Invoke-RestMethod 'http://127.0.0.1:7860/start' -Method Post -ContentType 'application/json' -Body '{"transport":"webrtc","enableDefaultIceServers":true}' -TimeoutSec 10
    [bool]$start.sessionId
} $VoiceTimeoutSec 'Voz /start'
Write-Ok 'Voz acepta sesiones WebRTC'

# ---------- 5. Frontend (sólo cuando TODO lo anterior está listo) ----------
Write-Step '5/5 Interfaz web'
$FrontendDir = Join-Path $Root 'frontend'
if (-not (Port-Listening 5173)) {
    if ($Dev) {
        Start-Service-Process 'frontend' 'npm.cmd' @('run', 'dev', '--', '--host', '0.0.0.0', '--port', '5173') $FrontendDir @{} | Out-Null
    } else {
        Push-Location $FrontendDir
        npm run build | Out-Null
        if ($LASTEXITCODE -ne 0) { Pop-Location; Fail 'La compilación del frontend falló.' }
        Pop-Location
        Start-Service-Process 'frontend' 'npm.cmd' @('run', 'preview', '--', '--host', '0.0.0.0', '--port', '5173', '--strictPort') $FrontendDir @{} | Out-Null
    }
}
Wait-Until { (Invoke-WebRequest 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } 120 'Frontend'
Write-Ok 'Interfaz publicada'

Write-Host ''
Write-Host '[GIANA] Todos los servicios están arriba y verificados.' -ForegroundColor Green
Write-Host '  Interfaz : http://localhost:5173'
Write-Host '  Debug    : http://localhost:5173/?debug=1'
Write-Host '  Backend  : http://localhost:5000/ready'
Write-Host '  Voz      : http://localhost:7860'
Write-Host '  Qdrant   : http://localhost:6333'
Write-Host "  Logs     : $Logs"
