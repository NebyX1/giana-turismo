# Independent input audio; only the test browser's microphone uses these files.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Target = Join-Path $Root 'tests/e2e/fixtures/web-research'
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Add-Type -AssemblyName System.Speech
$speech = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speech.SelectVoice('Microsoft Helena Desktop')
    $speech.Rate = -1
    $questions = @(
        '¿Qué día y hora es?',
        '¿Podés buscar por mí en la web qué eventos culturales hay en Minas?',
        'Necesito que busques en la web qué eventos culturales hay en estas fechas en Minas.',
        '¿Qué podés contarme del Cerro Arequita?',
        '¿Qué fecha es hoy?'
    )
    for ($index = 0; $index -lt $questions.Count; $index++) {
        $speech.SetOutputToWaveFile((Join-Path $Target "input-$($index + 1)-1.wav"))
        $speech.Speak($questions[$index])
        $speech.SetOutputToNull()
    }
} finally {
    $speech.Dispose()
}
Write-Output "Fixtures guardados en $Target"
