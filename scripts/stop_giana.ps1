$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root 'run\backend.pid'
if (-not (Test-Path -LiteralPath $PidFile)) { Write-Output 'Gianna no tiene un proceso registrado.'; return }
$BackendPid = [int](Get-Content -LiteralPath $PidFile)
$Backend = Get-CimInstance Win32_Process -Filter "ProcessId=$BackendPid"
if ($Backend) {
    if (-not ($Backend.CommandLine -like '*backend.app.main*' -and $Backend.CommandLine.Contains($Root))) {
        throw 'El PID registrado pertenece a otro proceso; no se detuvo.'
    }
    $Children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$BackendPid"
    foreach ($Child in $Children) {
        if ($Child.CommandLine -like '*backend.app.main*') { Stop-Process -Id $Child.ProcessId -Force }
    }
    Stop-Process -Id $BackendPid -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $PidFile
Write-Output 'Gianna detenida.'
