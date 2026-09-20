# Progreso Giana V2

> **Estado de arquitectura actual:** el snapshot publicado usa Whisper
> large-v3-turbo con faster-whisper/CTranslate2 en CUDA como STT predeterminado;
> Moonshine queda como rollback. La voz conserva Silero + SmartTurn + Pipecat,
> la barrera `TurnState` y Piper HTTP como TTS operativo. Kokoro CUDA existe como
> adaptador preparado, pero no está conectado por los builders actuales. Ver
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) para el flujo vigente; las
> secciones M0-M5 siguientes conservan el historial de aceptación.

## M0 — Bootstrap y smoke de hardware

- Estado: PASS
- Fuente presente: `data/source/Guia_Turistica_Lavalleja_Consolidada_v4(2).md` (4088 líneas, 316167 bytes).
- Qdrant: PASS en el servicio Docker existente `localhost:6333` (no se modificó).
- CUDA: PASS, NVIDIA GeForce RTX 5060 Ti.
- Granite: PASS, `ibm-granite/granite-embedding-97m-multilingual-r2`, `cuda:0`, 384 dimensiones.
- mMARCO: PASS, `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, `cuda:0`, tres scores obtenidos.
- VRAM medida: 0 bytes antes, 196897792 bytes tras Granite, 667471872 bytes tras ambos modelos.
- Ollama Cloud/DeepSeek: PASS; `OLLAMA_API_KEY` sólo fue comprobada como presente y nunca impresa.
- Reporte: `reports/gpu.json`.

## M1 — Ingestión + RAG texto

- Estado: EN PROGRESO / vertical slice PASS.
- Parser determinista ejecutado con hash esperado: 510 bloques, 555 chunks, 133 fichas, 34 FAQ, 243 fuentes.
- Vistas JSONL y SQLite FTS5 generadas en `data/generated/`.
- Colección nueva `giana_granite_v2` creada en Qdrant: 555 vectores, 384 dimensiones, estado green.
- Retrieval híbrido activo: FTS5 + Granite dense + RRF + mMARCO condicional, con lock CUDA.
- `/api/ask-text` probado por HTTP real; devuelve respuesta, estado y evidencia con líneas/fuentes.
- Smoke de consultas reales ejecutado: té en Villa Serrana, Nico Pérez/Florida y carga eléctrica.
- Structured fast path y segunda oportunidad implementados.
- 20/20 consultas del corpus encontraron evidencia en `reports/m1_retrieval.json`.

## M2 — RAG robusto + web

- Estado: PASS.
- Consentimiento de web ligado a sesión/request, TTL y rechazo por expiración.
- Ollama Web Search/Web Fetch integrados; resultados marcados como web/efímeros.

## M3 — Voz local SmallWebRTC (histórico, actualizado)

- Estado: PASS de runner y componentes.
- Pipecat + Silero + Whisper large-v3-turbo CUDA por defecto (Moonshine ES CPU como rollback) + Piper `es_AR-daniela-high` HTTP CPU.
- Runner SmallWebRTC levantado y UI prebuilt verificada.

## M4 — Interrupciones + frontend

- Estado: PASS de build y cancelación lógica.
- React/Vite/TypeScript/Fluent UI compilado.
- `generation_id` evita que respuestas/audio viejos regresen tras interrupción.

## M5 — LiveKit + aceptación final

- Estado: PASS de integración automatizable.
- `LiveKitTransport` cableado; token endpoint y handshake real contra servidor local verificados.
- No se falsificó una prueba humana de micrófono; queda sólo validación manual de audio en navegador.

## Próxima misión

- Operación manual opcional: conectar micrófono desde la UI y verificar barge-in con hardware de audio.
