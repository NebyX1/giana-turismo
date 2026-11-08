# Gianna Turismo

Chat turístico de Lavalleja, Uruguay. Conserva la guía, el catálogo, la recuperación
híbrida, la memoria de conversación, el reloj de Uruguay, las fuentes y la
investigación web. La interfaz es exclusivamente de texto.

## Modelos y ejecución

| Función | Modelo | Ejecución |
|---|---|---|
| Embeddings | `ibm-granite/granite-embedding-97m-multilingual-r2` | ONNX INT8 AVX2, CPU, vectores de 384 dimensiones |
| Reranking | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | ONNX INT8 AVX2, CPU |
| Router y respuestas | `deepseek-v4.1-flash:cloud` | Ollama Cloud mediante la aplicación local de Ollama |

Los dos modelos de recuperación están fijados por ID, revisión y SHA256 en
`backend/app/model_policy.py`. No hay selección de otros embeddings o rerankers.
Se descargan únicamente los pesos cuantizados y los tokenizadores: unos 259 MB
en total. ONNX Runtime ejecuta la inferencia directamente, sin un framework de
entrenamiento. El perfil predeterminado usa 4 hilos, lotes de 8 y hasta 512 tokens.
Granite utiliza el vector CLS normalizado, como especifica su
[modelo oficial](https://huggingface.co/ibm-granite/granite-embedding-97m-multilingual-r2).

Qdrant se ejecuta embebido y persiste en `storage/qdrant`. SQLite FTS5 aporta la
búsqueda léxica. El backend sirve también la interfaz compilada: sólo se mantiene
un proceso del proyecto, sin servicios adicionales de infraestructura.

## Instalación local en Windows

Requisitos: Python 3.12 de 64 bits, Node.js 22.12 o posterior, npm y Ollama con
sesión iniciada. Los modelos INT8 seleccionados requieren una CPU con AVX2.

Desde la raíz del repositorio, en PowerShell:

```powershell
ollama run deepseek-v4.1-flash:cloud
# Salir de la conversación de consola con /bye.
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\start_giana.ps1
```

Abrí [Gianna local](http://127.0.0.1:5000). La instalación crea `.venv` y `.env`,
instala las versiones verificadas de Python y npm, prepara los dos modelos,
compila la interfaz y genera el índice de los 555 fragmentos de la guía.
El script de inicio reutiliza un índice compatible y lo reconstruye si cambia
el corpus o la configuración de embeddings. No ejecutes el instalador ni el
indexador mientras esté abierto el backend.

Ollama debe permanecer abierto. La inferencia de DeepSeek se realiza en la nube;
necesita conexión a Internet y una sesión de Ollama autorizada para ese modelo.
La API local usa `http://127.0.0.1:11434` y no necesita copiar credenciales,
según el [esquema de autenticación de Ollama](https://docs.ollama.com/api/authentication).
Para acceso directo a Ollama Cloud, configurá `OLLAMA_BASE_URL=https://ollama.com`
y `OLLAMA_API_KEY` en `.env`. La búsqueda DDGS funciona sin esa clave; el proveedor
web alternativo de Ollama sí requiere una API key.

## Operación

```powershell
powershell -ExecutionPolicy Bypass -File scripts\status_giana.ps1
powershell -ExecutionPolicy Bypass -File scripts\stop_giana.ps1
```

`start_giana.ps1` recompila la interfaz; `-NoBuild` reutiliza la compilación
existente. Los logs quedan en `logs/backend.log` y `logs/backend.err.log`.
El servidor escucha únicamente en `127.0.0.1:5000` y usa Waitress.
`/ready` verifica los modelos calentados y la compatibilidad del índice;
`/api/diagnostics` informa el proveedor CPU y la configuración de inferencia.
Activá `GIANA_DIAGNOSTICS=true` para registrar eventos del chat en `logs/`.

Para desarrollo, iniciá el backend y ejecutá `npm run dev` desde `frontend`.
Vite publica la interfaz en `http://localhost:5173` y reenvía `/api` al backend.

## Corpus y validación

La fuente está en `data/source/Guia_Turistica_Lavalleja_Consolidada_v4(2).md`.
Los datos derivados versionados incluyen SQLite, 510 bloques, 555 fragmentos,
133 entradas de catálogo, 34 FAQ y 243 fuentes. Para regenerarlos:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_giana.ps1
.\.venv\Scripts\python.exe scripts\ingest.py
.\.venv\Scripts\python.exe scripts\index_qdrant.py --force
```

Con el backend detenido, ejecutá las pruebas locales y el benchmark:

```powershell
.\.venv\Scripts\python.exe scripts\verify_cpu.py
.\.venv\Scripts\python.exe scripts\run_tests.py
```

Con el backend iniciado, la prueba completa usa también DeepSeek Cloud:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_chat.py
```

Las pruebas de navegador usan Chrome y Playwright; se instalan por separado:

```powershell
Push-Location tests\e2e
npm ci
node chat_smoke.mjs
node stale_text.mjs
node check_auto_web_progress.mjs
Pop-Location
```

El navegador verifica respuestas reales, fuentes, escritorio/móvil, nuevas
conversaciones y progreso de búsqueda. Los resultados locales quedan en `reports/`.

Los modelos, el índice, las credenciales y los entornos instalados son locales y
están excluidos de Git. La arquitectura y los límites del índice se explican en
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
