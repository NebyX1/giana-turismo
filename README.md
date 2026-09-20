# Giana Turismo

Asistente turístico de Lavalleja con frontend React/Vite, voz en tiempo real y RAG híbrido local. Este snapshot contiene el core reproducible; no incluye corpus, índices, bases runtime, pesos ni secretos.

## Arquitectura actual

La aplicación está separada en frontend, transporte/pipeline de voz, backend de
conocimiento y servicios locales. El frontend React/Vite usa HTTP para texto y
SmallWebRTC/Pipecat para voz. El runner de voz aplica Silero VAD, STT configurable
(`whisper_turbo` CUDA por defecto o Moonshine CPU), SmartTurn y una barrera
`TurnState` antes de enviar el turno completo al backend Flask. El backend combina
enrutamiento semántico, fast paths locales, SQLite FTS5, Granite + Qdrant, RRF,
mMARCO y respuestas verificadas. Las consultas actuales pueden activar búsqueda
web con consentimiento y evidencia efímera. Piper HTTP sigue siendo el TTS
operativo; existe un adaptador Kokoro CUDA seleccionable, pero no es el builder
activo por defecto.

```text
Browser :5173
  ├─ texto ──► Vite proxy ──► Flask :5000
  │                              ├─ router semántico / reloj / persona
  │                              ├─ SQLite FTS5 + Granite CUDA + Qdrant :6333
  │                              ├─ mMARCO reranker CUDA
  │                              ├─ web research + consentimiento
  │                              └─ Ollama Cloud
  │
  └─ voz WebRTC ──► Pipecat :7860
                    ├─ Silero VAD + Whisper Turbo CUDA / Moonshine CPU
                    ├─ SmartTurn + TurnState
                    ├─ HTTP ► Flask :5000
                    └─ Piper HTTP :5001 ──► audio WebRTC ──► Browser
```

El diagrama técnico completo, los contratos y los límites del snapshot están en
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Requisitos

- Windows 11 está soportado y es el entorno probado actualmente. Linux/Ubuntu y
  WSL2 también son válidos para los scripts Bash.
- Python 3.11 es la versión verificada en Windows; Node.js 22 y npm para el
  frontend.
- CUDA y una GPU NVIDIA son necesarias para el perfil actual: Whisper Turbo,
  Granite y mMARCO se ejecutan localmente en CUDA.
- Docker Desktop con el motor Linux/WSL2 ejecuta Qdrant. No hay un contenedor de
  desarrollo del frontend en `docker-compose.yml`; el frontend se ejecuta con
  npm/Vite.
- `OLLAMA_API_KEY` válida para Ollama Cloud.
- Qdrant debe estar accesible en `http://127.0.0.1:6333` cuando se inicia el
  backend.
- En esta instalación están preparados localmente el modelo Whisper Turbo, la
  voz Piper y el corpus. No se publican en GitHub y una instalación nueva debe
  obtenerlos o generarlos por separado.

## Instalación

En Windows 11, desde PowerShell:

```powershell
Copy-Item .env.example .env
py -3.11 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
& .\.venv\Scripts\python.exe -m pip install -r voice\requirements.txt
Push-Location frontend
npm ci
Pop-Location
docker compose up -d qdrant
```

Después de preparar el corpus, los pesos y el índice local, iniciá el stack con:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_production.ps1
```

En Linux o WSL2 se puede usar el bootstrap Bash:

```bash
cp .env.example .env
bash scripts/bootstrap.sh
```

Configurá `OLLAMA_API_KEY` en `.env` sin versionarlo. El bootstrap instala
dependencias y crea directorios, pero no descarga modelos ni datasets grandes.

## Componentes externos

| Componente | Finalidad | Ejecución/configuración |
|---|---|---|
| `ibm-granite/granite-embedding-97m-multilingual-r2` | Embeddings | Local, CUDA; `EMBEDDING_MODEL` |
| `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Reranking | Local, CUDA; `RERANKER_MODEL` |
| `mobiuslabsgmbh/faster-whisper-large-v3-turbo` (`openai/whisper-large-v3-turbo`) | STT predeterminado | Local, faster-whisper/CTranslate2, CUDA `int8_float16`; `STT_PROVIDER=whisper_turbo` |
| Moonshine ES | STT de rollback | Local, CPU; `STT_PROVIDER=moonshine` |
| Silero VAD + `LocalSmartTurnAnalyzerV3` | Detección y cierre de turnos | Local, CPU; Pipecat |
| `es_AR-daniela-high` | TTS activo | Piper local, CPU, HTTP en `:5001`; `TTS_PROVIDER=piper` |
| `hexgrad/Kokoro-82M` / `ef_dora` | TTS alternativo | Adaptador CUDA probado en `voice/tts/kokoro_service.py`; requiere `TTS_PROVIDER=kokoro` y no es el perfil activo |
| `deepseek-v4.1-flash:cloud` | Router semántico y respuesta principal | Ollama Cloud; `backend/app/runtime_config.json` |
| `gemma4:31b-cloud` | Fallback de router/respuesta e investigación web | Ollama Cloud; `backend/app/runtime_config.json` |
| DDGS + Ollama Web Search | Investigación web | DDGS primario y Ollama Cloud como fallback; `web_search_provider` |
| Qdrant | Índice vectorial | Docker Desktop/WSL2, `QDRANT_URL` |

`runtime_config.json` es la fuente efectiva de los modelos cloud; `OLLAMA_MODEL` y
`OLLAMA_FALLBACK_MODEL` heredados en un `.env` antiguo no sustituyen esa
configuración. Los pesos locales y la voz ONNX no se incluyen en GitHub. El
servidor Piper espera que `models/piper/es_AR-daniela-high.onnx` exista al iniciar
el perfil Piper.

## RAG

La implementación está en `backend/app/main.py`, `scripts/ingest.py` y `scripts/index_qdrant.py`. El snapshot no incluye `data/source`, `data/generated` ni la colección Qdrant. Para reconstruir:

1. Colocá el corpus turístico en `data/source/Guia_Turistica_Lavalleja_Consolidada_v4(2).md`.
2. Ejecutá `python scripts/ingest.py` para generar SQLite FTS5 y artefactos intermedios.
3. Ejecutá `python scripts/index_qdrant.py` para crear la colección y cargar vectores.

El corpus original, los pesos y la colección Qdrant deben transferirse o
generarse por un canal separado y no deben versionarse.

## Arranque

El arranque ordenado de producción es:

```bash
bash scripts/start_production.sh
```

En Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_production.ps1
```

Estos scripts verifican Qdrant, Piper, backend, voz y frontend en ese orden; la interfaz sólo se inicia después de que los servicios anteriores responden. Para desarrollo completo también se conserva:

```bash
bash scripts/start_giana_clean.sh
```

Requiere `.env`, corpus, pesos locales y dependencias instaladas. Para componentes individuales se conservan `scripts/start-dev.sh`, `scripts/start-dev.ps1`, `voice/bot.py -t webrtc` y el servidor Piper usado por `start_giana_clean.sh`. Qdrant se levanta con:

```bash
docker compose up -d qdrant
```

## Puertos

- Frontend Vite: `5173`
- Backend Flask: `5000`
- Piper HTTP: `5001`
- SmallWebRTC/Pipecat: `7860`
- Qdrant: `6333` y `6334`

## Estado del snapshot

Este repositorio contiene código fuente, configuración, scripts, tests y documentación. Se excluyen intencionalmente secretos, `.env` reales, modelos/pesos, voces ONNX, corpus, datasets, índices Qdrant, SQLite poblada, caches, logs, traces, audios, builds, `node_modules` y virtualenvs.
