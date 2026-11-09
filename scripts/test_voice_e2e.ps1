param([string]$QaSessionId = '', [switch]$Install)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $QaSessionId) { $QaSessionId = (Get-Content (Join-Path $root 'logs/test/CURRENT_QA_SESSION_ID.txt') -Raw).Trim() }
$qaDir = (Get-Content (Join-Path $root 'logs/test/CURRENT_QA_SESSION.txt') -Raw).Trim()
if ($Install -or -not (Test-Path (Join-Path $root 'tests/e2e/node_modules/@playwright/test'))) { npm install --prefix (Join-Path $root 'tests/e2e') }
$env:QA_SESSION_ID = $QaSessionId
$env:QA_DIR = $qaDir
node (Join-Path $root 'tests/e2e/run_voice_e2e.mjs')
exit $LASTEXITCODE
