# Regresión de conversaciones de voz en Windows

## Dependencia de tokenización

Pipecat usa NLTK al separar las oraciones tanto en TTS como en el observador RTVI.
En Windows Store, APPDATA puede redirigirse a otra ruta que NLTK no reconoce como
permitida. El síntoma era un `PermissionError [pathsec.open]`: morían el TTS y el
observador del chat. No desactivar la seguridad de NLTK ni modificar site-packages.

La aplicación valida al arrancar `data/nltk_data/tokenizers/punkt_tab/english`.
Para preparar una instalación nueva, desde la raíz del proyecto:

```powershell
.venv\Scripts\python.exe -m nltk.downloader -d data/nltk_data punkt_tab
.venv\Scripts\python.exe -c "from voice.runtime import prepare_text_runtime; print(prepare_text_runtime())"
```

También se puede transferir el corpus existente a esa carpeta. Es un recurso de
runtime excluido del snapshot, igual que los modelos. `GIANA_NLTK_DATA` permite
una carpeta alternativa explícita. Si falta, el servicio falla antes de aceptar
sesiones, no en medio de la conversación.

## Invariantes

- El texto completo usa eventos `giana-turn-event` con sesión/turno/generación.
- Un segmento de STT actualiza la misma fila del turno; no borra el historial.
- Una continuación durante la pausa conserva los segmentos previos.
- El fin de síntesis de una oración no significa fin de reproducción.
- El historial se conserva en sessionStorage al recargar la misma pestaña.
- El saludo espera `on_client_ready`, no un temporizador arbitrario.
- La conexión usa trickle ICE; el endpoint PATCH recibe candidatos sin provocar
  una renegociación anticipada por finalizar la recolección de candidatos.
- La desconexión cancela el pipeline y cierra sus clientes HTTP.

## Pruebas

```powershell
.venv\Scripts\python.exe scripts/test_conversation_regressions.py
npm run build --prefix frontend
powershell -ExecutionPolicy Bypass -File scripts/start_production.ps1 -Dev
node tests/e2e/conversation_audio.mjs
# Prueba adicional de una frase partida por 900 ms de silencio:
$env:GIANA_E2E_MODE = 'pauses'
node tests/e2e/conversation_audio.mjs
Remove-Item Env:GIANA_E2E_MODE
```

La prueba Python usa colas reales de Pipecat y un backend simulado: diez turnos
con continuaciones, separación de oraciones, timeout, error HTTP y recuperación.
No demuestra audio extremo a extremo por sí sola.

La prueba Chrome usa WebRTC, STT Whisper, backend y Piper reales. Únicamente
controla la fuente del micrófono del navegador de prueba con frases habladas por
Piper. Ejecuta ocho turnos, recarga/reconecta y ejecuta dos más. Compara el texto
completo con el DOM, el texto reproducido por el transporte y todos los segmentos
TTS; comprueba aumento de energía RTP y conserva grabaciones WebM recibidas.
No modifica el micrófono del navegador del usuario. Los WAV de
`tests/e2e/fixtures/conversation` fijan entradas previamente reconocidas; no se
regeneran aleatoriamente en cada corrida. Si un fixture no existe se sintetiza y
se conserva en el resultado. La síntesis de una entrada de prueba también puede
producir audio mal reconocido: eso es un FAIL, no una razón para relajar el assert.

Los resultados se guardan en `logs/test/CURRENT_SESSION.txt` → `browser-<timestamp>`:
`RESULTS.json`, mensajes RTVI por turno, capturas, HAR, consola y audio recibido.
Los intentos fallidos se conservan. Se requiere un marcador de sesión válido.

Un PASS automático no certifica el micrófono físico, altavoces, eco acústico,
ruido ambiente ni todos los acentos. Esas condiciones requieren validación humana.
Los traces antiguos llevan `source=human` por defecto; para estas ejecuciones la
clasificación fiable es `level=E2E_BROWSER` y `humanValidation=PENDING` del resultado.
