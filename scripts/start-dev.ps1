$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
& ".\.venv\Scripts\python.exe" -m flask --app backend.app.main run --host 0.0.0.0 --port 5000
