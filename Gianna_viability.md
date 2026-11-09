# Gianna — Análisis de viabilidad y plan de producción

Fecha: 2026-09-18. Hardware objetivo: RTX 3050 8 GB + Ryzen 5 5500 (el equipo de desarrollo actual es una RTX 5060 Ti; todo lo propuesto cabe también en 8 GB).

## 1. Veredicto

**El proyecto es viable y no debe descartarse.** La base es correcta: corpus consolidado con referencias, ingesta determinista con hash, retrieval híbrido (FTS5 + Granite + RRF + reranker) con evidencia trazable, pipeline de voz Pipecat con VAD/STT/TTS locales y un frontend funcional. Los fallos observados (irse de Lavalleja, no buscar en la web, confundirse) **no son estructurales**: están concentrados en la capa de decisión (router de intención por palabras clave, prompt sin ancla geográfica, búsqueda web sin restricción territorial). Son corregibles en horas, no en semanas. Reescribir desde cero costaría más y volvería a los mismos problemas si no se corrige esa capa.

## 2. Estructura actual

| Capa | Tecnología | Estado |
|---|---|---|
| Corpus | `data/source/Guia_Turistica_Lavalleja_Consolidada_v4(2).md` (4088 líneas, 243 fuentes) | Bueno. Único origen de verdad. |
| Ingesta | `scripts/ingest.py` determinista → SQLite FTS5 + JSONL (510 bloques, 555 chunks, 133 fichas, 34 FAQ) | Bueno. `aliases.json` está vacío: desaprovechado. |
| Dense index | Qdrant (Docker) + Granite 97m multilingual 384d en CUDA | Bueno. ~200 MB VRAM. |
| Reranker | mMARCO MiniLM L12 en CUDA, condicional | Bueno. ~470 MB VRAM. |
| Backend | Flask dev server, `backend/app/main.py` (un solo archivo, ~540 líneas) | Funciona; monolítico; sin WSGI de producción. |
| LLM | Ollama Cloud `gemma4:31b-cloud` con fallback `glm-5.3-flash:cloud` | Funciona; dependencia externa; sin ancla geográfica en el prompt. |
| Web | Ollama Web Search/Fetch | Estaba desconectada de `/api/ask-text` (corregido hoy); sin filtro Lavalleja/Uruguay. |
| Voz | Pipecat 1.10: Silero VAD → Moonshine ES (CPU) → SmartTurn v3 (CPU) → RAG → Piper `es_AR-daniela-high` HTTP | Funciona tras las correcciones de turno. Moonshine confunde topónimos. |
| Frontend | React + Vite + TypeScript + Zustand + Pipecat client-js + SmallWebRTC | Funciona. Sin limpieza de sesión al desmontar. |
| Arranque | `scripts/start_giana.ps1` | Lanza procesos sin esperar readiness real; sin equivalente Linux de producción. |

## 3. Problemas encontrados (evidencia real, no supuestos)

### 3.1 Críticos (rompen la confianza del usuario)

1. **Se va de Lavalleja.** Pregunta "busca en la web información sobre el nuevo hotel plaza" devolvió un hotel de Valencia. Causa: la consulta a Ollama Web Search se enviaba tal cual, sin "Lavalleja Uruguay", y el prompt del LLM decía "usá solo la evidencia" sin decir "solo Lavalleja". El LLM resumió honestamente la evidencia equivocada.
2. **No buscaba en la web aunque se lo pidiera.** `classify_intent` devolvía `WEB_FOLLOWUP` pero `ask_text` no tenía rama para ese intent: caía al RAG local y el LLM prometía "busco ahora mismo" sin buscar. Corregido hoy con `web_followup_response`, pero es el síntoma del problema de fondo: **el router decide, el ejecutor ignora**.
3. **"Buscalo" pierde el tema.** El seguimiento "dale, buscalo en la web" buscaba literalmente esas palabras. Corregido hoy en `standalone_query` (usa el turno anterior), pero el mecanismo general de resolución de referencias es un `startswith` de 8 palabras.
4. **Router por palabras clave frágil.** `"web" in q` dispara búsqueda web con cualquier frase que contenga "web"; `"hoy"`/`"ahora"` disparan `CURRENT_INFO` aunque el usuario diga "hoy quiero conocer Minas"; `TOURISM_RAG` es el default para cualquier cosa, incluida una pregunta sobre Valencia o Marte. No hay concepto de **fuera de dominio**.
5. **Topónimos mal transcritos.** Moonshine transcribió "Cerro Arequita" → "ser varequita", "Minas" → "ciudadaninas", "Giana" → "Jana/Shanna". El RAG recupera lo correcto (Arequita), pero el LLM responde "no tengo información sobre ser varequita". No hay normalización de entidades entre STT y RAG, y `aliases.json` está vacío.

### 3.2 Importantes (calidad/operación)

6. Flask dev server (`app.run`) en producción: single-thread por defecto, sin supervisión. Con `GPU_LOCK` global una consulta lenta bloquea a todas.
7. Estado global compartido en el proceso de voz (`LAST_SMART_TURN_DECISION`, `CURRENT_TURN_DEBUG`, `CURRENT_TTS_TRACE`): con dos navegadores conectados se contaminan las trazas y potencialmente las decisiones. Hoy se eliminó el veto por decisión global, pero los diccionarios siguen.
8. `TEXT_TTS_DIVERGENCE` se dispara en cada frase: compara cada oración contra la respuesta completa. Ruido que esconde errores reales.
9. El frontend adjunta al reproductor **todas** las pistas de audio, incluida la local (`participant: true` en trazas): riesgo de eco/retroalimentación.
10. `SESSION_HISTORY`, `CONSENTS`, `ACTIVE_GENERATIONS` viven en memoria del proceso: se pierden en cada reinicio y no escalan a más de un worker.
11. Archivos duplicados `*(1).*` en `frontend/src`, `scripts`: ruido que confunde builds y revisiones.
12. `start_giana.ps1` no espera readiness real (backend puede tardar 60–90 s cargando CUDA), abre el frontend antes de que voz esté lista y no tiene par para Linux.
13. `HF_HUB_OFFLINE` no está fijado: un arranque sin internet o con rate limit de Hugging Face puede fallar aunque los modelos estén en caché.
14. Dependencia del LLM en la nube: sin `OLLAMA_API_KEY` o sin internet, Giana no responde nada útil salvo persona/conversación.

### 3.3 Menores

15. Watchdogs del frontend con mensajes engañosos ("No pude entender lo que dijiste" cuando el transcript sí llegó).
16. Backend `/ready` exige Qdrant; no hay `/ready` en voz ni Piper (Piper sólo tiene `/synthesize`).
17. Prompt del LLM no fija idioma/estilo de forma sistemática ni prohíbe recomendar fuera del departamento.

## 4. Cómo lo haría yo (y por qué)

Referencia: asistentes turísticos municipales exitosos (p. ej. proyectos con Rasa/Haystack + LLM acotado) comparten tres reglas: **dominio cerrado explícito**, **grounding verificable** y **degradación honesta**. Este proyecto ya tiene el segundo. Le faltan el primero y el tercero.

### 4.1 Dominio cerrado (lo más importante)

- **Contrato de alcance en el prompt**: "Sos la asistente turística del departamento de Lavalleja, Uruguay. Si la pregunta o la evidencia se refiere a otro lugar, decilo y redirigí a Lavalleja. Nunca recomiendes lugares fuera del departamento."
- **Búsqueda web siempre anclada**: toda consulta a Web Search se reescribe como `"{consulta} Lavalleja Uruguay"` y se filtran resultados sin señales territoriales (Lavalleja, Minas, Villa Serrana, Uruguay, `.uy`).
- **Router con estado `OUT_OF_SCOPE`**: preguntas sobre otros lugares se contestan con una redirección amable, sin RAG ni web.

### 4.2 Router de intención

Reemplazar el `if "web" in q` por un clasificador en dos niveles:
1. Reglas de alta precisión (saludos, meta, pedido explícito de web con verbo + objeto).
2. Para lo demás, una decisión ligera basada en si el retrieval devolvió evidencia con score suficiente: si el RAG tiene evidencia → responder; si no → ofrecer web (una vez) o declarar que no está en la guía. **La evidencia decide, no la palabra clave.**

### 4.3 Normalización de entidades STT → RAG

- Poblar `aliases.json` desde `catalog.jsonl` (133 fichas) con variantes fonéticas (Arequita/Arequitá/varequita, Minas/minas, Villa Serrana, Penitente, Salus, Aguas Blancas, etc.).
- Antes del retrieval, corregir el transcript por similitud (RapidFuzz, ratio ≥ 85) contra el índice de nombres. Barato, determinista, resuelve el 80 % de los "ser varequita".

### 4.4 Operación

- Backend con **Waitress** (Windows) / **Gunicorn** (Linux), 2 hilos, `GPU_LOCK` intacto.
- Persistir `SESSION_HISTORY` y `CONSENTS` en SQLite (ya existe la dependencia).
- Endpoints `/ready` en voz (`7860/ready` ya lo da el runner de Pipecat como `/`) y comprobación de Piper con un `/synthesize` corto.
- Arranque ordenado con espera **real** de cada servicio (sección 6).
- Eliminar duplicados `*(1).*`.
- `HF_HUB_OFFLINE=1` tras primera descarga.

### 4.5 Presupuesto de recursos para RTX 3050 8 GB / Ryzen 5 5500

| Componente | Dónde | Memoria estimada |
|---|---|---|
| Granite 97m fp16 | GPU | ~200 MB |
| mMARCO MiniLM fp16 | GPU | ~470 MB |
| Silero VAD | CPU | <50 MB RAM |
| Moonshine small-streaming ES | CPU | ~250 MB RAM |
| SmartTurn v3.2 ONNX | CPU | ~100 MB RAM |
| Piper daniela-high | CPU | ~150 MB RAM |
| Qdrant (555 vectores) | Docker | ~100 MB RAM |
| LLM | Nube (Ollama Cloud) | 0 local |

Total GPU < 1 GB. Sobra margen. Si se quisiera **LLM local** para no depender de la nube: `qwen2.5:7b-instruct-q4_K_M` (~4.7 GB VRAM) o `gemma2:9b-q4` (~5.5 GB) vía Ollama local caben en 8 GB junto con los embeddings, con latencia aceptable para 1–4 frases. Recomendación: mantener nube como primario por calidad y añadir Ollama local como fallback offline.

### 4.6 Alternativa completa (solo si en el futuro se quiere rehacer)

No la recomiendo ahora, pero si se rehiciera desde cero con la experiencia adquirida:

- **Backend**: FastAPI + Uvicorn (async nativo, mismo proceso que voz posible), Pydantic para contratos.
- **Retrieval**: igual (FTS5 + Granite + Qdrant + reranker); añadir grafo de entidades ligero (SQLite) para preguntas "cerca de", "en la misma zona".
- **Router**: clasificador pequeño fine-tuned (SetFit sobre MiniLM, 200 ejemplos) + reglas.
- **LLM**: Ollama local `qwen2.5:7b` como primario, nube como escalado.
- **Voz**: Pipecat (correcto), STT `faster-whisper small` en GPU (~1 GB, mejor con topónimos que Moonshine) ya que la GPU está libre.
- **Frontend**: igual.
- **Orquestación**: `docker compose` con healthchecks y `depends_on: condition: service_healthy` para todo salvo el proceso con GPU.

## 5. Plan de corrección aplicado (paso 2)

1. Prompt del LLM con ancla territorial y regla de fuera de dominio.
2. Búsqueda web anclada a "Lavalleja Uruguay" + filtro de resultados sin señal territorial.
3. Router: `OUT_OF_SCOPE`, detección de web más estricta (verbo + objeto), `hoy/ahora` sólo si acompañan horario/apertura/disponibilidad.
4. Normalización de topónimos del transcript con aliases generados del catálogo.
5. Eliminación de `TEXT_TTS_DIVERGENCE` por frase (comparar acumulado).
6. Frontend: sólo pistas remotas al reproductor.
7. Pruebas: router, alcance, web y voz sintetizada.

## 6. Puesta en producción (paso 3)

`scripts/start_production.ps1` y `scripts/start_production.sh` levantan en este orden y **no avanzan hasta que el anterior responde de verdad**:

1. Qdrant → `GET /readyz` = 200 **y** colección `giana_granite_v2` existe (si no, indexa).
2. Piper → `POST /synthesize` con texto corto devuelve audio.
3. Backend → `GET /ready` = 200 (modelos cargados y calentados, Qdrant visible).
4. Voz → `GET http://localhost:7860/` = 200 **y** `POST /start` devuelve `sessionId`.
5. Frontend → sólo entonces `npm run dev`/`vite preview`, y espera `GET :5173` = 200.

Cualquier fallo aborta con mensaje claro y detiene lo que levantó.

## 7. Lo que sigue siendo un riesgo aunque todo lo anterior esté hecho

- Moonshine seguirá equivocándose en nombres raros; la normalización mitiga, no elimina. Si molesta, `faster-whisper small` en GPU es el siguiente paso.
- El LLM en la nube puede caer o cambiar de modelo; el fallback local es la única protección real.
- SmartTurn v3 marca INCOMPLETE con frecuencia en rioplatense; hoy se acepta el cierre por silencio (1.5 s). Si el usuario habla con pausas largas, se le cortará. Ajustable con `stop_secs`.
