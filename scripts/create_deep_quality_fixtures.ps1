$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Ejecutar con pwsh/PowerShell 7: Windows PowerShell 5 interpreta incorrectamente el UTF-8 de estas frases.' }
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Target = Join-Path $Root 'tests/e2e/fixtures/deep-quality'
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Add-Type -AssemblyName System.Speech
$speech = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speech.SelectVoice('Microsoft Helena Desktop')
    $speech.Rate = -1
    $questions = @(
        'Hola Giana, necesito que me digas si hay algún lugar donde comer un asado en la ciudad de Minas.',
        'Salud.',
        'No, no, te pedí que me recomendaras un lugar donde comer un asado en la ciudad de Minas.',
        '¿Cuál es el teléfono de Don Jorgito?',
        '¿Qué eventos culturales hay esta semana en la ciudad de Minas?',
        'Buscá en la web información sobre eventos culturales.',
        '¿Qué podés contarme del Cerro Arequita?',
        'Quiero saber dónde podemos || comer algo vegano en la ciudad de Minas.',
        '¿Puedo llevar un perro al Penitente?',
        '¿Qué día y hora es?',
        'Hola Giana, ¿estás ahí?',
        'Hola, ¿me recibís bien? Quiero comer asado en Minas.',
        '¿Qué eventos culturales hay en octubre de 2026 en Minas?',
        'Buenas noches Giana, ¿seguís ahí conmigo?'
    )
    for ($index = 0; $index -lt $questions.Count; $index++) {
        $parts = $questions[$index] -split ' \|\| '
        for ($part = 0; $part -lt $parts.Count; $part++) {
            $speech.SetOutputToWaveFile((Join-Path $Target "input-$($index + 1)-$($part + 1).wav"))
            $speech.Speak($parts[$part]); $speech.SetOutputToNull()
        }
    }
    $ExtraTarget = Join-Path $Root 'tests/e2e/fixtures/voice-resilience'
    New-Item -ItemType Directory -Force -Path $ExtraTarget | Out-Null
    $extraQuestions = @('Hola Giana, ¿estás ahí?', 'Contame en detalle todo lo que se puede visitar en el Cerro Arequita y su entorno.', 'Pará, decime qué día y hora es ahora.', 'Hola, ¿me recibís bien? Quiero comer asado en Minas.', 'Gracias, hasta después.')
    for($index=0; $index -lt $extraQuestions.Count; $index++) {
        $speech.SetOutputToWaveFile((Join-Path $ExtraTarget "input-$($index+1)-1.wav"))
        $speech.Speak($extraQuestions[$index]); $speech.SetOutputToNull()
    }
    $ContextTarget = Join-Path $Root 'tests/e2e/fixtures/voice-context'
    New-Item -ItemType Directory -Force -Path $ContextTarget | Out-Null
    $contextQuestions = @('¿Y su teléfono?', '¿Y su dirección?', 'Quiero comer vegano en Minas.', '¿Y su dirección?')
    for($index=0; $index -lt $contextQuestions.Count; $index++) {
        $speech.SetOutputToWaveFile((Join-Path $ContextTarget "input-$($index+1)-1.wav"))
        $speech.Speak($contextQuestions[$index]); $speech.SetOutputToNull()
    }
} finally { $speech.Dispose() }
Write-Output "Fixtures guardados en $Target"
