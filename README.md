# Giana Turismo

Asistente turístico de Lavalleja con frontend React/Vite, voz en tiempo real y RAG híbrido local. Este snapshot contiene el core reproducible; no incluye corpus, índices, bases runtime, pesos ni secretos.

## Arquitectura

```text
Browser
  ↓
React/Vite frontend :5173
  ↓ SmallWebRTC / Pipecat :7860
Moonshine STT → RAG híbrido
                 ├ SQLite FTS5
                 ├ Qdrant :6333
                 ├ Granite embeddings en GPU
                 └ mMARCO reranker en GPU
                         ↓
                 Flask backend :5000
                         ↓
                 Ollama Cloud / Gemma o GLM
                         ↓
                 Piper es_AR-daniela-high :5001
                         ↓
                       Browser
```

## Requisitos

- Linux/Ubuntu recomendado.
- Python 3.12 y CUDA/GPU para el RAG configurado.
- Node 22 para el frontend; Docker para Qdrant y el contenedor de desarrollo frontend.
- `OLLAMA_API_KEY` válida para Ollama Cloud.
- Qdrant accesible en `http://localhost:6333`.
- Los modelos locales, la voz Piper y el corpus deben obtenerse aparte; no están incluidos.

## Instalación

```bash
cp .env.example .env
bash scripts/bootstrap.sh
```

Configurá `OLLAMA_API_KEY` en `.env` sin versionarlo. El bootstrap no descarga modelos ni datasets grandes.

## Componentes externos

| Componente | Finalidad | Ejecución/configuración |
|---|---|---|
| `ibm-granite/granite-embedding-97m-multilingual-r2` | Embeddings | Local, GPU; `EMBEDDING_MODEL` |
| `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Reranking | Local, GPU; `RERANKER_MODEL` |
| Moonshine ES | STT | Local, CPU; Pipecat lo carga desde `voice/pipeline.py` |
| `es_AR-daniela-high` | TTS | Piper local, CPU; `PIPER_VOICE` y `PIPER_URL` |
| Gemma/GLM cloud | Respuesta LLM | Ollama Cloud; `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_API_KEY` |
| Qdrant | Índice vectorial | Docker, `QDRANT_URL` |

Los nombres y pesos de modelos no se incluyen en GitHub. El servidor Piper espera que la voz exista localmente al iniciar `scripts/start_giana_clean.sh`.

## RAG

La implementación está en `backend/app/main.py`, `scripts/ingest.py` y `scripts/index_qdrant.py`. El snapshot no incluye `data/source`, `data/generated` ni la colección Qdrant. Para reconstruir:

1. Colocá el corpus turístico en `data/source/Guia_Turistica_Lavalleja_Consolidada_v4(2).md`.
2. Ejecutá `python scripts/ingest.py` para generar SQLite FTS5 y artefactos intermedios.
3. Ejecutá `python scripts/index_qdrant.py` para crear la colección y cargar vectores.

El corpus original y los modelos deben transferirse por un canal separado y no deben versionarse.

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
