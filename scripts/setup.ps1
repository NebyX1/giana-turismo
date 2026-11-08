$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
Push-Location $Root
try {
    if (-not (Test-Path -LiteralPath $Python)) {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Se necesita Python 3.12 de 64 bits.' }
    }
    if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
    & $Python -m pip install -r backend\requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de Python.' }
    Push-Location frontend
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Falló npm ci.' }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación del frontend.' }
    } finally { Pop-Location }
    & $Python scripts\prepare_models.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló la preparación de modelos.' }
    if (-not (Test-Path -LiteralPath data\generated\giana.sqlite3)) {
        & $Python scripts\ingest.py
        if ($LASTEXITCODE -ne 0) { throw 'Falló la ingestión de la guía.' }
    }
    & $Python scripts\index_qdrant.py
    if ($LASTEXITCODE -ne 0) { throw 'Falló el indexado. Cerrá el backend antes de instalar.' }
    Write-Output 'Entorno listo. Ejecutá scripts\start_giana.ps1.'
} finally { Pop-Location }
