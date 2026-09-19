# Export manifest

- Fecha: 2026-09-17.
- Origen: `/home/usuario/Documentos/Proyectos IA/Giana-Turismo-3`.
- Destino: `/home/usuario/Documentos/Proyectos IA/gitboy-giana-turismo`.
- Propósito: snapshot portable para revisión y posterior publicación en GitHub.

## Incluido

Frontend React/Vite y lockfile; backend Flask; servicio Pipecat/SmallWebRTC; integraciones Moonshine y Piper; implementación RAG, embeddings, reranking, SQLite FTS5 y Qdrant; integración Ollama/Web; scripts de ingestión, indexado, smoke, arranque y parada; Docker Compose; requirements; documentación; tests y configuración de ejemplo.

## Excluido

Secretos y `.env` reales; modelos y pesos; voz Piper ONNX; corpus y datasets; SQLite/índices/vectores generados; almacenamiento Qdrant; caches; `node_modules`; virtualenv; logs, traces, reportes generados, audios y builds.

## Reconstrucción

1. Copiar `.env.example` a `.env` y completar la clave de Ollama Cloud.
2. Ejecutar `bash scripts/bootstrap.sh`.
3. Aportar externamente el corpus en `data/source/` y los modelos/voz requeridos.
4. Ejecutar `python scripts/ingest.py` y `python scripts/index_qdrant.py`.
5. Levantar Qdrant y ejecutar `bash scripts/start_giana_clean.sh`.

## Tamaño y conteo

- Archivos: 51.
- Tamaño: 0.28 MiB (298,144 bytes según `du -sb`).
- Archivos mayores a 10 MB: ninguno.
- Validación: compilación sintáctica Python completada y `frontend/package.json`/`package-lock.json` válidos.
