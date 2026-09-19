param([string]$RepoRoot = 'D:\Ai Projects\Giana-Turismo-V2')
$ErrorActionPreference = 'Continue'
$session = (Get-Content (Join-Path $RepoRoot 'logs\test\CURRENT_SESSION.txt') -Raw).Trim()
$results = [ordered]@{}
$results.LOGGING = ((Test-Path (Join-Path $session 'manifest.json')) -and (Test-Path (Join-Path $session 'startup.log')) -and (Test-Path (Join-Path $session 'trace.jsonl')) -and ((Get-Item (Join-Path $session 'trace.jsonl')).Length -gt 0))
try { $results.QDRANT = ((Invoke-WebRequest 'http://127.0.0.1:6333/readyz' -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) } catch { $results.QDRANT = $false }
try { $results.PIPER = ((Invoke-WebRequest 'http://127.0.0.1:5001' -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) } catch { $results.PIPER = $false }
try { $results.BACKEND = ((Invoke-WebRequest 'http://127.0.0.1:5000/health' -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 -and (Invoke-WebRequest 'http://127.0.0.1:5000/ready' -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) } catch { $results.BACKEND = $false }
try { $results.'VOICE SERVER' = ((Invoke-WebRequest 'http://127.0.0.1:7860/' -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) } catch { $results.'VOICE SERVER' = $false }
try { $start = Invoke-RestMethod 'http://127.0.0.1:7860/start' -Method Post -ContentType 'application/json' -Body '{"transport":"webrtc","enableDefaultIceServers":true}' -TimeoutSec 10; $results.'VOICE /start' = [bool]$start.sessionId } catch { $results.'VOICE /start' = $false }
try { $results.FRONTEND = ((Invoke-WebRequest 'http://localhost:5173/' -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) } catch { $results.FRONTEND = $false }
$results.GetEnumerator() | ForEach-Object { '{0,-15} {1}' -f $_.Key, ($(if($_.Value){'PASS'}else{'FAIL'})) }
if($results.Values -contains $false){ exit 1 }; exit 0
