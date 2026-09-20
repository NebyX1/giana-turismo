# Arquitectura actual

Estado verificado contra el código del repositorio el 20/09/2026. Giana V2 ya no es un flujo lineal de navegador a Flask: separa la interfaz, el transporte de voz, el procesamiento de turnos, el backend de conocimiento y los servicios de infraestructura.

## Flujo general

```text
															 ┌──────────────────────────────────────┐
															 │ Navegador                            │
															 │ React 19 + Vite 7 + TypeScript       │
															 │ Fluent UI + Zustand + Pipecat client │
															 │ http://localhost:5173               │
															 └───────────────┬──────────────────────┘
																							 │
										texto: HTTP /api/ask-text │ voz: WebRTC + data channel
																							 │
								 ┌───────────────────────────┴───────────────────────────┐
								 │                                                        │
								 ▼                                                        ▼
		 ┌────────────────────────────┐                         ┌────────────────────────┐
		 │ Vite proxy                  │                         │ Pipecat runner         │
		 │ /api -> Flask :5000         │                         │ SmallWebRTC :7860      │
		 └──────────────┬─────────────┘                         │ LiveKit opcional       │
										│                                       └───────────┬────────────┘
										▼                                                   │
		 ┌────────────────────────────┐                                     ▼
		 │ Flask / backend            │◄──────── HTTP ───────────────┐  ┌───────────────┐
		 │ routing + RAG + web + LLM │                                │  │ voz Pipecat   │
		 │ :5000                      │                                │  │ VAD + STT     │
		 └──────────────┬─────────────┘                                │  │ SmartTurn     │
										│                                              │  │ RAG processor │
										▼                                              │  │ TTS           │
		 ┌────────────────────────────┐                                │  └──────┬────────┘
		 │ Ollama Cloud               │                                │         │ audio WebRTC
		 │ selector + respuesta + web │                                │         ▼
		 └────────────────────────────┘                                └───► Navegador

		 Qdrant :6333 (Docker)     Piper HTTP :5001 (TTS activo por defecto)
		 SQLite FTS5 (runtime)     Kokoro CUDA (adaptador disponible, no cableado por defecto)
```

El frontend usa el proxy de Vite para texto. La voz no pasa por el endpoint de texto del navegador: el runner de Pipecat envía la pregunta al backend por HTTP y devuelve audio, texto y eventos de estado por el transporte WebRTC. `LiveKitTransport` comparte la misma tubería, pero el arranque local de producción utiliza SmallWebRTC.

## Frontend

`frontend/src/AppShell.tsx` coordina la conversación escrita, el consentimiento web, los estados visibles y los errores. `frontend/src/hooks.ts` crea un `PipecatClient` con `SmallWebRTCTransport`, inicia `http://localhost:7860/start`, conecta el audio remoto y procesa los `server-message` RTVI. `frontend/src/store.ts` mantiene el historial en `sessionStorage`, el `conversationId`, el estado de voz y el `generation_id` activo.

Estados relevantes: `CONNECTING`, `LISTENING`, `WAITING_TRANSCRIPT`, `RETRIEVING`, `THINKING`, `WEB_SEARCHING`, `SPEAKING` y `ERROR`. `RETRIEVING` se muestra cuando el backend recibe la pregunta (`backend_dispatch_started`), no sólo porque exista una transcripción visible.

## Voz y turn-taking

La implementación está en `voice/bot.py`, `voice/pipeline.py`, `voice/stt.py` y `voice/tts/`.

```text
WebRTC audio in
	-> Silero VAD (CPU)
	-> STT configurable:
			 whisper_turbo (predeterminado, faster-whisper/CTranslate2, CUDA int8_float16)
			 moonshine (rollback explícito, CPU)
	-> UserTurnProcessor + LocalSmartTurnAnalyzerV3 (CPU)
	-> TurnState / try_finalize_turn()
	-> GianaRAGProcessor
	-> POST http://localhost:5000/api/ask-text
	-> respuesta canónica compartida por texto y TTS
	-> PiperHttpTTSService -> http://localhost:5001/synthesize
	-> audio PCM 16 kHz -> WebRTC
```

La barrera `TurnState` permite que SmartTurn y el transcript final lleguen en cualquier orden. Sólo `try_finalize_turn()` puede despachar el turno; el watchdog y el timeout de gracia son mecanismos de diagnóstico y recuperación, no rutas paralelas de finalización. El `generation_id` permite cancelar una respuesta antigua durante un barge-in sin cancelar la generación nueva del usuario.

El adaptador `voice/tts/kokoro_service.py` implementa Kokoro 82M con CUDA, voz `ef_dora` y conversión de 24 kHz a 16 kHz. Es una integración seleccionable y preparada para pruebas, pero los builders actuales de `voice/pipeline.py` instancian explícitamente Piper; por eso Piper es el TTS operativo del snapshot publicado.

## Backend y enrutamiento

`backend/app/main.py` es el proceso Flask que carga una sola instancia de `ModelManager` para Granite y mMARCO en CUDA. Antes de acceder al RAG, normaliza el transcript y resuelve una ruta:

- conversación pura: respuesta local sin red, índice ni LLM;
- reloj: hora real de Uruguay;
- persona: identidad y misión de Gianna;
- fuera de alcance: respuesta territorial controlada;
- conocimiento: RAG híbrido local;
- información actual o búsqueda explícita: investigación web con consentimiento o fallback permitido.

`backend/app/semantic_router.py` puede seleccionar una herramienta acotada con el modelo configurado en `backend/app/runtime_config.json`: `conversation`, `knowledge`, `web`, `clock`, `persona` u `out_of_scope`. La ejecución no es un bucle de agente abierto: valida la herramienta, limita argumentos y usa un fallback acotado.

El endpoint principal es `POST /api/ask-text`. Cada solicitud lleva `session_id`/`conversation_id`, `turn_id`, `generation_id` y `source`. El historial y las generaciones activas son memoria de proceso; no se promete persistencia conversacional después de reiniciar Flask.

## RAG híbrido

Para consultas de conocimiento local, la ruta es:

```text
consulta original
	-> normalización y consulta independiente de seguimiento
	-> fast path estructurado para entidades y contactos
	-> SQLite FTS5 / BM25
	-> Granite multilingual 97M en CUDA
	-> Qdrant :6333, colección giana_granite_v2
	-> Reciprocal Rank Fusion (RRF)
	-> resolución de bloques padre y preservación de coincidencias exactas
	-> mMARCO MiniLM cross-encoder en CUDA
	-> máximo 8 evidencias finales
	-> respuesta validada por contrato
```

Granite produce vectores de 384 dimensiones. La colección y SQLite son artefactos runtime generados desde el corpus; no se versionan. El backend serializa el acceso a los modelos CUDA con un lock y los carga/calienta antes de aceptar tráfico en el arranque de producción.

## Web y tiempo

Las consultas de agenda, vigencia, horarios o búsqueda explícita se encaminan a `web_research.py` y `web_tools.py` cuando corresponde. El flujo puede usar DDGS con caché corta y Ollama Cloud como fallback, restringe URLs públicas para evitar SSRF, limita búsquedas y páginas, valida el territorio de Lavalleja y conserva las fuentes como evidencia efímera. La UI pide consentimiento para la búsqueda web cuando la ruta lo exige; el consentimiento está ligado a sesión/request y expira.

## Servicios y contratos HTTP

| Servicio | Puerto | Responsabilidad |
|---|---:|---|
| Frontend Vite/preview | 5173 | UI, texto y cliente WebRTC |
| Flask | 5000 | routing, RAG, web, LLM, diagnósticos |
| Pipecat runner | 7860 | señalización SmallWebRTC y pipeline de voz |
| Piper HTTP | 5001 | TTS `es_AR-daniela-high` en CPU |
| Qdrant | 6333/6334 | índice vectorial HTTP/gRPC en Docker |

Endpoints principales: `/api/ask-text`, `/api/time`, `/ready`, `/health`, `/api/diagnostics`, `/api/debug/last-turn`, `/api/web/consent`, `/api/web/search`, `/api/web/fetch` y `/api/livekit/token`.

`/ready` del backend sólo devuelve éxito cuando los modelos CUDA están cargados y calentados, Qdrant contiene la colección y la configuración LLM está disponible. El script `scripts/start_production.ps1` levanta y prueba en orden Qdrant, Piper, Flask, Pipecat y frontend; la variante `.sh` mantiene el mismo contrato para Linux.

## Límites del snapshot

GitHub contiene código, configuración de ejemplo, scripts, tests y documentación. Quedan fuera deliberadamente `.env` reales, claves, corpus, SQLite runtime, colección Qdrant, modelos/pesos, voz ONNX, caches, logs, traces, audios, builds, `node_modules` y virtualenvs. Para ejecutar la aplicación se deben preparar esos artefactos localmente con `scripts/ingest.py`, `scripts/index_qdrant.py` y `scripts/prepare_whisper_turbo.py` cuando corresponda.
