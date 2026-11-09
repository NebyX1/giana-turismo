# Reporte de tests

## M0 — PASS

- `docker ps` y `curl http://localhost:6333/`: Qdrant saludable, HTTP 200.
- `.venv/bin/python scripts/verify_gpu.py`: Granite y mMARCO en `cuda:0`; vector 384; tres scores; reporte escrito en `reports/gpu.json`.
- `.venv/bin/python scripts/smoke_m0.py`: clave presente sin imprimir valor, Qdrant PASS y DeepSeek PASS.

Pendiente: suite de ingestión y RAG de M1.

## M1 — vertical slice PASS / misión abierta

- `.venv/bin/python scripts/ingest.py`: hash esperado y conteos 510/555/133/34/243.
- `.venv/bin/python scripts/index_qdrant.py`: colección `giana_granite_v2`, 555 vectores, 384d, estado green.
- `.venv/bin/python scripts/smoke_rag.py`: tres preguntas reales respondidas con evidencia y DeepSeek.
- `GET /health`: HTTP 200.
- `POST /api/ask-text` con teléfono de Catedral de Minas: HTTP 200, respuesta + líneas + fuentes.

Pendiente: completar los 20 casos obligatorios de M1 y las rutas estructuradas/segunda oportunidad.

## M2 — PASS

- `scripts/smoke_m1_retrieval.py`: 20/20 consultas con evidencia local.
- `scripts/smoke_m2.py`: consentimiento ausente 403, consentimiento creado, búsqueda consentida 200, consentimiento expirado 403.

## M3 — PASS de componentes y runner

- Pipecat 1.10 importado con Moonshine, Piper, Silero, SmallWebRTC y LiveKit.
- Moonshine español cargado en CPU; Piper configurado como `es_AR-daniela-high` por HTTP en CPU.
- Piper HTTP real: sintetizó WAV PCM mono 22050 Hz.
- `voice/smoke_voice.py`: cancelación de generación PASS.
- `voice/bot.py -t webrtc`: runner levantó en `localhost:7860`; UI prebuilt respondió HTTP 200.

## M4 — PASS funcional de interfaz y cancelación

- Frontend React/Vite/Fluent UI compilado con Node 22 en contenedor, sin vulnerabilidades npm reportadas.
- UI mínima incluye conexión, estado, pregunta, respuesta y evidencia expandible.
- Barge-in lógico verificado con `GenerationController`; resultados de generaciones viejas se descartan.

## M5 — PASS de integración LiveKit

- `LiveKitTransport` construido con la misma tubería de voz.
- `/api/livekit/token` probado con credenciales de smoke sin imprimirlas.
- `scripts/smoke_livekit.py`: handshake real contra LiveKit self-hosted local PASS.
- `scripts/start-dev.sh` con backend real: `/health` HTTP 200; endpoint de token devuelve 503 explícito cuando las variables LiveKit no están configuradas, sin degradar a un token falso.

Pendiente operativo: prueba humana de micrófono/barge-in en navegador y Piper HTTP desplegado como servicio persistente; la infraestructura y los runners están cableados y probados hasta el límite automatizable sin dispositivo de audio.
