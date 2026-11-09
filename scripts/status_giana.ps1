$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
function PortStatus($name, $port) {
  $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($c) { "$name : OK (PID $($c.OwningProcess), puerto $port)" } else { "$name : DOWN (puerto $port)" }
}
PortStatus 'Backend' 5000
PortStatus 'Piper' 5001
PortStatus 'Voice/SmallWebRTC' 7860
PortStatus 'Frontend' 5173
PortStatus 'Qdrant' 6333
Write-Output '--- Hardware ---'
Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name
Get-CimInstance Win32_ComputerSystem | Select-Object @{N='RAM_GB';E={[math]::Round($_.TotalPhysicalMemory/1GB,1)}}
nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv,noheader 2>$null
Write-Output '--- Services ---'
try { (Invoke-WebRequest http://127.0.0.1:5000/health -UseBasicParsing -TimeoutSec 3).Content } catch { 'backend health unavailable' }
try { (Invoke-WebRequest http://127.0.0.1:5000/ready -UseBasicParsing -TimeoutSec 3).Content } catch { 'backend ready unavailable' }
try { (Invoke-WebRequest http://127.0.0.1:6333/collections/giana_granite_v2 -UseBasicParsing -TimeoutSec 3).Content } catch { 'qdrant collection unavailable' }
Write-Output '--- Config ---'
Select-String -Path .env -Pattern '^(OLLAMA_MODEL|OLLAMA_FALLBACK_MODEL|EMBEDDING_MODEL|RERANKER_MODEL|PIPER_VOICE|QDRANT_COLLECTION)=' | ForEach-Object { $_.Line }
