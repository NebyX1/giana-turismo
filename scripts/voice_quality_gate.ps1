param([string]$QaSessionId = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $QaSessionId) { $QaSessionId = (Get-Content (Join-Path $root 'logs/test/CURRENT_QA_SESSION_ID.txt') -Raw).Trim() }
$qaDir = (Get-Content (Join-Path $root 'logs/test/CURRENT_QA_SESSION.txt') -Raw).Trim()
$file = Join-Path $qaDir 'E2E_RESULTS.json'
if (-not (Test-Path $file)) { Write-Error 'E2E_RESULTS.json not found'; exit 1 }
$result = Get-Content $file -Raw | ConvertFrom-Json
if (-not $result.pass) { Write-Error 'GIANA voice quality gate failed'; exit 1 }
Write-Output 'GIANA voice quality gate PASS'
exit 0
