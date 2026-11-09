# Independent Spanish input voice for the browser test, not production TTS.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Target = Join-Path $Root 'tests/e2e/fixtures/time-web'
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Add-Type -AssemblyName System.Speech
$speech = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speech.SelectVoice('Microsoft Helena Desktop')
    $speech.Rate = -1
    $questions = @(
        'Giana, ¿qué día y hora es?',
        '¿Qué eventos culturales hay esta semana en Minas?',
        '¿No podés buscar en la web algún evento cultural para recomendarme en Minas?',
        'Buscá en la web la página oficial del Teatro Lavalleja.',
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
