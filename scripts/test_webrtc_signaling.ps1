$ErrorActionPreference = 'Stop'
$voice = 'http://127.0.0.1:7860'
$checks = @{}
$checks.voice_server = ((Invoke-WebRequest "$voice/" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200)
$checks.client = ((Invoke-WebRequest "$voice/client/" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200)
$startBody = @{transport='webrtc';enableDefaultIceServers=$true} | ConvertTo-Json
$start = Invoke-WebRequest "$voice/start" -Method Post -ContentType 'application/json' -Body $startBody -UseBasicParsing -TimeoutSec 10
$checks.start_http_200 = ($start.StatusCode -eq 200)
$session = ($start.Content | ConvertFrom-Json).sessionId
$checks.session_id = [bool]$session
$offerUrl = "$voice/sessions/$session/api/offer"
$options = Invoke-WebRequest $offerUrl -Method Options -Headers @{Origin='http://localhost:5173';'Access-Control-Request-Method'='POST';'Access-Control-Request-Headers'='content-type'} -UseBasicParsing -TimeoutSec 5
$checks.offer_endpoint_cors_options = ($options.StatusCode -eq 200)
$debug = Invoke-WebRequest 'http://127.0.0.1:5173/api/debug/last-turn' -UseBasicParsing -TimeoutSec 5
$checks.debug_last_turn_http_200 = ($debug.StatusCode -eq 200)
$checks | ConvertTo-Json | Write-Output
if ($checks.Values -contains $false) { exit 1 }
Write-Output 'WEBRTC_SIGNALING_BASELINE_PASS'
