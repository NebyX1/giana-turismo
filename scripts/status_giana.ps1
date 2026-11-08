$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
Push-Location $Root
try { $LocalConfig = & $Python -m backend.app.model_policy }
finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'Configuración inválida.' }
$Port = ($LocalConfig | ConvertFrom-Json).port
try {
    Invoke-RestMethod "http://127.0.0.1:$Port/ready" -TimeoutSec 5 | ConvertTo-Json -Depth 5
    Invoke-RestMethod "http://127.0.0.1:$Port/api/diagnostics" -TimeoutSec 5 | ConvertTo-Json -Depth 5
} catch { Write-Output 'Gianna no está lista. Revisá logs\backend.err.log.'; exit 1 }
