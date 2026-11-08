param([switch]$NoBuild)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw 'Primero ejecutá scripts\setup.ps1.' }
Push-Location $Root
try {
    if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
    $LocalConfig = & $Python -m backend.app.model_policy
    if ($LASTEXITCODE -ne 0) { throw 'Configuración inválida.' }
    $Port = ($LocalConfig | ConvertFrom-Json).port
    $Url = "http://127.0.0.1:$Port"
    $Listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($Listener) {
        $Existing = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener[0].OwningProcess)"
        if ($Existing.CommandLine -like '*backend.app.main*') {
            # Windows virtualenv launchers may own a base-Python child process.
            $Owner = $Existing
            if (-not $Owner.CommandLine.Contains($Root)) {
                $Owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($Existing.ParentProcessId)"
            }
            if ($Owner -and $Owner.CommandLine -like '*backend.app.main*' -and $Owner.CommandLine.Contains($Root)) {
                Write-Output "Gianna ya está iniciada: $Url"
                return
            }
        }
        throw "El puerto $Port está ocupado por otro proceso."
    }
    if (-not $NoBuild -or -not (Test-Path -LiteralPath frontend\dist\index.html)) {
        Push-Location frontend
        try { npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación del frontend.' } }
        finally { Pop-Location }
    }
    New-Item -ItemType Directory -Path logs,run -Force | Out-Null
    $env:PYTHONUTF8 = '1'
    $Process = Start-Process -FilePath $Python -ArgumentList '-m','backend.app.main' -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Root 'logs\backend.log') -RedirectStandardError (Join-Path $Root 'logs\backend.err.log') -PassThru
    $Process.Id | Set-Content -LiteralPath run\backend.pid -Encoding ascii
    for ($Attempt = 0; $Attempt -lt 120; $Attempt++) {
        if ($Process.HasExited) { throw 'El backend terminó. Revisá logs\backend.err.log.' }
        try {
            $Ready = Invoke-RestMethod "$Url/ready" -TimeoutSec 2
            if ($Ready.status -eq 'ready') { Write-Output "Gianna lista: $Url"; return }
        } catch { }
        Start-Sleep -Seconds 1
        $Process.Refresh()
    }
    throw 'El arranque sigue en curso. Consultá scripts\status_giana.ps1 y los logs.'
} finally { Pop-Location }
