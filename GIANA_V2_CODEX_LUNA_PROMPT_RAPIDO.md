# GIANA V2 — PROMPT MAESTRO RÁPIDO PARA CODEX + LUNA

## 0. OBJETIVO

Construí **Giana V2 desde cero** como asistente turístico conversacional de Lavalleja, con voz, RAG local de alta recuperación, búsqueda web con consentimiento e interrupciones reales.

Este encargo está deliberadamente diseñado para que un modelo de programación rápido y no necesariamente brillante pueda ejecutarlo sin improvisar arquitectura. **No rediseñes el stack, no investigues alternativas y no conviertas el proyecto en un laboratorio de frameworks.** Tu trabajo es implementar esta especificación, probarla y dejar una aplicación ejecutable.

Prioridad absoluta:

1. Que Giana **encuentre la información cuando está en su base**.
2. Que distinga “no encontré evidencia” de “el sistema falló”.
3. Que pueda hablar y ser interrumpida naturalmente.
4. Que pueda pedir permiso para buscar en la web si la base local no alcanza.
5. Que consuma pocos recursos y funcione tanto en una RTX 3050 8 GB como en una RTX 5060 Ti 16 GB.
6. Que exista una primera versión funcional **rápido**, antes de pulir arquitectura secundaria.

No entregues sólo planes. Trabajá sobre archivos, ejecutá comandos seguros y probá lo que implementes.

---

# 1. STACK CONGELADO

No sustituyas ninguna pieza salvo incompatibilidad técnica demostrada.

## Voz

- Orquestación: **Pipecat**
- Transporte de desarrollo: **Pipecat SmallWebRTC**
- Transporte de producción: **LiveKit self-hosted mediante `LiveKitTransport` de Pipecat**
- VAD / detección de inicio de voz: **Silero VAD**
- STT: **Moonshine español**, local, **CPU**
- TTS: **Piper**, voz **`es_AR-daniela-high`**, local, **CPU**
- Para producción, preferir **Piper por HTTP (`PiperHttpTTSService`)** para mantener el proceso Piper separado del código de Giana.
- Interrupciones: mecanismo nativo de Pipecat, habilitado.

## RAG

- Vector DB: **Qdrant**
- Base estructurada y búsqueda lexical: **SQLite + FTS5**
- Dense embedding GPU:
  - modelo exacto: `ibm-granite/granite-embedding-97m-multilingual-r2`
  - 97M parámetros
  - **384 dimensiones**
  - CUDA
  - SentenceTransformers
- Reranker GPU:
  - modelo exacto: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`
  - ~0.1B parámetros
  - CrossEncoder
  - CUDA
  - máximo práctico del par query+passage: 512 tokens
- Fusión de resultados: **RRF (Reciprocal Rank Fusion)**
- No LangChain.
- No LlamaIndex.
- No otro framework RAG.
- No un agente que “decida mágicamente” cómo buscar.

## LLM y web

- LLM: **Ollama Cloud — DeepSeek V4.1 Flash**
- API key: variable de entorno `OLLAMA_API_KEY`
- Modelo configurable por `OLLAMA_MODEL`
- Base URL configurable por `OLLAMA_BASE_URL`
- Búsqueda web: **Ollama Web Search API**
- Lectura de páginas: **Ollama Web Fetch API**
- Usar la **misma `OLLAMA_API_KEY`**
- No instalar SearXNG.
- No integrar otro buscador en esta primera versión.

## Backend y frontend

- Backend de negocio/RAG: **Flask**
- Frontend: **React + Vite + TypeScript + Fluent UI**
- Docker Compose para infraestructura y ejecución reproducible.
- Una conversación concurrente es suficiente para la primera entrega.
- Qdrant en Docker.
- LiveKit entra sólo después de que la versión SmallWebRTC funcione.

---

# 2. ARQUITECTURA FINAL

La aplicación debe terminar conceptualmente así:

```text
                        ┌─────────────────────┐
                        │ React / Vite        │
                        │ Fluent UI           │
                        └──────────┬──────────┘
                                   │
                         WebRTC / LiveKit
                                   │
                        ┌──────────▼──────────┐
                        │ Pipecat             │
                        │ estados + barge-in  │
                        └───┬─────────────┬───┘
                            │             │
                      Moonshine ES      Piper
                         CPU             CPU
                            │             ▲
                            ▼             │
                         texto          frases
                            │             │
                    ┌───────▼─────────────┐
                    │ Flask / Giana Core  │
                    └───────┬─────────────┘
                            │
             ┌──────────────┼────────────────────┐
             │              │                    │
             ▼              ▼                    ▼
        SQLite FTS5      Qdrant dense        catálogo exacto
        lexical          Granite 97M         entidades/servicios
                             GPU
             └──────────────┬────────────────────┘
                            │
                           RRF
                            │
                    candidatos pequeños
                            │
                      mMARCO MiniLM
                         GPU
                            │
                         top 4-6
                            │
                   expansión de contexto
                            │
                     Evidence Gate
                ┌───────────┼───────────┐
                ▼           ▼           ▼
           answerable    partial     no evidence
                │           │           │
                └──────┬────┘           ▼
                       │        pedir permiso web
                       ▼                │
               DeepSeek Cloud          ▼
                               Ollama web_search/fetch
                                       │
                                       ▼
                                  DeepSeek Cloud
```

---

# 3. REGLAS DE VELOCIDAD DE DESARROLLO

Ayer el desarrollo se fue durante horas en estructuración. **Esta vez no.**

Obedecé estas reglas:

1. **Vertical slice primero.** Antes de voz, UI bonita o LiveKit, debe existir:
   `pregunta de texto -> retrieval -> evidencia -> respuesta`.
2. No escribas decenas de documentos de arquitectura.
3. Sólo crear:
   - `README.md`
   - `PROGRESS.md`
   - `docs/ARCHITECTURE.md`
   - `docs/RAG_CONTRACT.md`
   - `docs/TEST_REPORT.md`
4. Ningún documento de diseño debe superar lo razonable para explicar decisiones concretas. No generes burocracia.
5. No crees ADRs salvo que haya una incompatibilidad real que obligue a apartarse de este contrato.
6. No hagas investigación web general sobre “mejores frameworks”. El stack ya está elegido.
7. Consultá documentación oficial únicamente si un import/API concreto no coincide con la versión instalada.
8. **No uses un LLM para convertir todo el Markdown en JSON.** La ingestión inicial debe ser determinista y rápida.
9. No intentes normalizar semánticamente cada oración del documento antes de tener RAG funcionando.
10. No hagas benchmarks enormes durante desarrollo. Primero smoke tests pequeños; suite completa sólo al cerrar una fase.
11. No reconstruyas imágenes Docker si no cambió una dependencia.
12. Montá cachés persistentes de Hugging Face/modelos.
13. Si el SHA256 del corpus no cambió, no reingieras ni re-embebas.
14. No cargues Granite ni mMARCO una vez por request.
15. Los dos modelos GPU deben vivir calientes en **un solo proceso backend**.
16. En desarrollo y producción inicial usar **un solo worker backend que posea CUDA** para no duplicar modelos.
17. No ejecutes embedding y reranker GPU en paralelo. Serializá inferencia CUDA con un lock/semaphore de concurrencia 1.
18. Si una implementación falla tres veces por la misma causa, no sigas parchando a ciegas. Elegí la ruta oficial más simple, documentá el bloqueo y seguí.
19. Ejecutá tests dirigidos después de cambios pequeños. Suite completa al final de cada misión.
20. Tras cada misión informá sólo:
    - PASS / FAIL / BLOCKED
    - archivos principales cambiados
    - tests ejecutados
    - problema pendiente
    - próxima misión

---

# 4. HARDWARE OBJETIVO

Máquina de desarrollo:

- Windows 11
- Ryzen 5 5500
- NVIDIA RTX 3050 8 GB
- Docker Desktop
- 16 GB RAM aproximadamente

Máquina de laboratorio:

- Ubuntu 24.x
- Ryzen 3 tercera generación
- NVIDIA RTX 5060 Ti 16 GB

El objetivo no es usar toda la GPU.

## Reglas GPU

Granite y mMARCO son las únicas piezas que deben usar CUDA.

Moonshine, Piper, Silero, Qdrant, SQLite, Pipecat y LiveKit deben permanecer en CPU.

Objetivo inicial del proceso GPU:

```text
Granite 97M + mMARCO MiniLM
presupuesto deseado total < 2 GB VRAM
```

Esto es un objetivo a medir, no un número que debas falsificar.

Registrar:

- VRAM con modelos recién cargados.
- Pico de VRAM durante una consulta.
- tiempo de embedding de una query.
- tiempo de reranking.
- tiempo total de retrieval, sin contar LLM cloud.

No quiero una GPU al 97 % durante varios segundos para una pregunta ordinaria.

Un pico de utilización alto durante pocos milisegundos es normal.

---

# 5. ARCHIVO FUENTE

El usuario entregará:

```text
data/source/Guia_Turistica_Lavalleja_Consolidada_v4(2).md
```

Para la versión actualmente conocida:

```text
SHA256:
9e156bf315db9340edefe9fb12aa93eab0a67e48d447f922ba584de339ddfc41
```

No falles si posteriormente se usa una versión distinta. En ese caso registrá el nuevo hash y reingestá.

La guía está estructurada con Markdown y contiene:

- capítulos turísticos narrativos
- fichas de atractivos
- directorio de gastronomía y alojamiento
- tablas
- contactos
- restricciones
- preguntas frecuentes
- fuentes
- registros cerrados/históricos
- inventario del geoparque

Sanity checks conocidos para esta versión:

- 133 fichas del directorio
- 34 FAQ
- 243 referencias
- 49 filas del inventario oficial del geoparque

Estos conteos sirven como control de ingestión, no como definición de todas las entidades existentes.

---

# 6. INGESTIÓN RÁPIDA Y SIN PÉRDIDA

Ésta es una de las diferencias centrales respecto del intento anterior.

## NO HACER

No mandar 4.000 líneas completas a DeepSeek para que “entienda y genere un JSON perfecto”.

No esperar horas a una extracción semántica total.

No resumir el corpus.

No reemplazar el Markdown por JSON.

## HACER

Crear vistas deterministas del mismo contenido.

Generar:

```text
data/generated/
  manifest.json
  blocks.jsonl
  chunks.jsonl
  catalog.jsonl
  faq.jsonl
  sources.jsonl
  aliases.json
  giana.sqlite3
```

## 6.1 `manifest.json`

Guardar:

- ruta del archivo
- SHA256
- fecha de ingestión
- versión del parser
- número de bloques
- número de chunks
- número de fichas de catálogo
- número de FAQ
- número de fuentes

## 6.2 `blocks.jsonl`

Cada bloque conserva texto **sin resumir**.

Campos mínimos:

```json
{
  "block_id": "stable-id",
  "heading_path": ["...", "..."],
  "heading_level": 3,
  "title": "...",
  "text": "...",
  "start_line": 100,
  "end_line": 118,
  "source_refs": [72, 73],
  "section_type": "narrative"
}
```

Los IDs deben ser deterministas a partir de contenido/ruta.

## 6.3 `chunks.jsonl`

Crear chunks semánticamente sensatos a partir de bloques.

Objetivo:

- ~250 a 550 tokens por chunk.
- overlap pequeño, ~50-80 tokens cuando haga falta.
- nunca separar un `Contacto:` de la ficha a la que pertenece.
- nunca separar una condición crítica de la frase que la define.
- conservar:
  - heading path
  - entidad asociada si existe
  - line range
  - source refs
  - tipo de bloque
  - texto exacto

No indexar sólo resúmenes.

## 6.4 `catalog.jsonl`

Parsear de forma determinista el directorio de establecimientos.

Una ficha empieza normalmente en un `#### Nombre` dentro del directorio.

Extraer cuando exista:

```json
{
  "entity_id": "...",
  "name": "...",
  "categories": [],
  "zone": "...",
  "location_text": "...",
  "contacts": [],
  "description": "...",
  "status": "active|temporary_closed|historical|unknown",
  "source_refs": [],
  "start_line": 0,
  "end_line": 0
}
```

No inventar campos faltantes.

`unknown` significa desconocido, no “no”.

No fusionar dos establecimientos sólo porque comparten teléfono.

Ejemplo importante:

- `Posada itaY`
- `Estación Penitente`

comparten un número en la guía pero son entidades distintas.

## 6.5 `faq.jsonl`

Extraer las preguntas y respuestas de la sección de preguntas de viaje.

Usarlas como:

- conocimiento
- tests
- ejemplos

Pero no hardcodear sus respuestas en runtime.

## 6.6 `sources.jsonl`

Parsear la bibliografía `[N]`.

Conservar:

```json
{
  "source_number": 72,
  "name": "...",
  "title": "...",
  "url": "...",
  "review_date": "..."
}
```

## 6.7 `aliases.json`

Generar aliases obvios solamente cuando estén documentados en el texto.

Ejemplos:

- Averías / 19 de Junio / Diecinueve de Junio.
- José Batlle y Ordóñez / referencias regionales pertinentes.

No crear aliases imaginarios mediante fuzzy matching agresivo.

---

# 7. SQLITE

Crear tablas mínimas:

```text
entities
entity_categories
entity_contacts
entity_aliases
source_blocks
sources
```

Crear FTS5 sobre:

- nombre
- aliases
- heading_path
- texto
- categorías
- localidad/zona

FTS5 es nuestra búsqueda lexical/BM25.

No hace falta desplegar Elasticsearch.

---

# 8. QDRANT

Crear una colección nueva.

Nombre recomendado:

```text
giana_granite_v2
```

Configuración:

- vector size: **384**
- distance: cosine

Payload por chunk:

```json
{
  "chunk_id": "...",
  "block_id": "...",
  "entity_id": "...",
  "title": "...",
  "heading_path": [],
  "start_line": 0,
  "end_line": 0,
  "source_refs": [],
  "text": "..."
}
```

No reutilizar una colección Qwen de 1024 dimensiones.

Indexación:

```text
texto -> Granite 97M GPU -> 384d -> Qdrant
```

Mantener caché por:

```text
sha256(chunk text + model id)
```

para evitar recalcular embeddings idénticos.

---

# 9. SERVICIO GPU

Granite y mMARCO deben cargarse una sola vez al iniciar el backend.

Usar:

```python
SentenceTransformer(
    "ibm-granite/granite-embedding-97m-multilingual-r2",
    device="cuda"
)
```

y:

```python
CrossEncoder(
    "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
    device="cuda"
)
```

Usar FP16 cuando sea estable en la RTX 3050.

Verificar con código que:

- `torch.cuda.is_available() == True`
- el modelo realmente está en CUDA
- no existe fallback silencioso a CPU

No abras múltiples procesos con copias de modelos.

No uses Flask debug reloader si duplica el proceso GPU.

---

# 10. PIPELINE RAG

El RAG debe ser explícito y determinista.

## 10.1 Ruta 0: consulta estructurada

Antes de llamar al embedding, detectar consultas obvias:

- teléfono de X
- contacto de X
- dirección de X
- listame todos los hoteles en Y
- heladerías de Minas
- camping con electricidad
- lugares catalogados en una zona
- estado cerrado/activo cuando está estructurado

Resolver desde SQLite cuando sea suficiente.

Si la respuesta exacta ya está allí:

```text
NO reranker
NO dense retrieval obligatorio
```

Aun así devolver evidencia y líneas.

## 10.2 Ruta 1: retrieval híbrido

Para preguntas generales:

```text
consulta
   │
   ├── SQLite FTS5 lexical top 20
   ├── Granite dense top 20
   └── entity/alias hits
             │
             ▼
            RRF
             │
         deduplicación
             │
        8-16 candidatos
```

Usar RRF. No sumar scores cosine y BM25 directamente.

## 10.3 Reranking

mMARCO **no debe rerankear 50 documentos**.

Regla inicial:

- máximo: 16 candidatos
- batch GPU pequeño: 4 u 8, medir
- truncar cada candidate passage a una longitud que mantenga query+passage <= 512 tokens
- preferir 300-430 tokens de passage
- top final: 4-6

Sólo rerankear si:

- hay varios candidatos plausibles,
- la query es semántica,
- o la evidencia todavía no es clara.

No usar reranker para un teléfono encontrado por identidad exacta.

## 10.4 Expansión posterior

Después del reranker, y sólo entonces:

- recuperar chunk padre
- recuperar vecino anterior/siguiente si corresponde
- unir condiciones/restricciones del mismo bloque

No hagas reranking sobre páginas completas.

## 10.5 Evidence Gate

Implementar en código, no dejarlo librado a una frase del LLM.

Estados:

```text
ANSWERABLE
PARTIAL
AMBIGUOUS
CURRENT_DATA_REQUIRED
NO_EVIDENCE
SYSTEM_ERROR
```

Nunca convertir:

```text
Qdrant caído
GPU error
SQLite error
timeout
```

en:

> “No tengo información.”

Eso es `SYSTEM_ERROR`.

---

# 11. SEGUNDA OPORTUNIDAD ANTES DE DECIR “NO SÉ”

`NO_EVIDENCE` sólo puede ocurrir después de:

1. entity/alias exact lookup
2. SQLite FTS5
3. Granite dense
4. RRF
5. reranker si corresponde
6. exact substring fallback en bloques
7. una segunda búsqueda con reformulación cuando tenga sentido

La reformulación puede usar DeepSeek, pero sólo en esta segunda pasada.

Pedir como máximo **3 consultas alternativas**.

Ejemplo:

```text
"dónde puedo comer algo sin carne cerca del lago"
```

puede generar:

```text
comida vegetariana Villa Serrana
restaurante vegetariano Villa Serrana
platos vegetarianos Villa Serrana
```

No lanzar diez búsquedas.

Si la segunda pasada encuentra evidencia, responder normalmente.

---

# 12. REGLAS CRÍTICAS DE CONOCIMIENTO

Estas diferencias no se pueden perder:

- Una opción vegana no convierte todo el restaurante en vegano.
- “Sin gluten” puede ser:
  - opciones puntuales
  - propuesta declarada como 100 % sin gluten
  y deben permanecer diferenciadas.
- `unknown` no significa “no ofrece”.
- Camping cerrado no significa cabañas cerradas.
- Fecha histórica no significa evento vigente.
- Precio fechado no significa tarifa actual.
- Teléfono compartido no implica misma empresa.
- “Cerca” documentado puede ser una relación útil aunque no existan coordenadas.
- Geositio no implica acceso público.
- Un alojamiento próximo a un atractivo no concede acceso al atractivo.
- Nico Pérez pertenece a Florida aunque sea contiguo a Batlle y Ordóñez.
- Agua en un lugar no demuestra baño habilitado.
- Horario administrativo no es automáticamente horario de museo.
- Una referencia web en la bibliografía no significa que runtime conozca el contenido completo de esa web.

---

# 13. LLM

DeepSeek redacta, conversa y puede ayudar con reformulación.

No decide por sí solo qué evidencia existe.

Input al LLM:

```text
system prompt breve
+ pregunta
+ contexto conversacional relevante
+ evidence package
```

El `evidence package` debe contener por resultado:

- entidad/título
- texto
- líneas
- fuentes
- tipo de evidencia

El prompt del LLM debe exigir:

1. responder sólo usando evidencia local o web suministrada;
2. no inventar horarios, contactos, distancias, disponibilidad ni precios;
3. mantener incertidumbres;
4. si `PARTIAL`, responder la parte conocida;
5. si falta un dato actual, decir qué falta;
6. usar español rioplatense natural;
7. respuestas de voz relativamente breves;
8. poder ampliar si el usuario lo solicita.

No enviar los 4.000 renglones de la guía a cada turno.

---

# 14. BÚSQUEDA WEB Y HUMAN IN THE LOOP

Usar la API oficial de Ollama:

```text
POST https://ollama.com/api/web_search
POST https://ollama.com/api/web_fetch
Authorization: Bearer $OLLAMA_API_KEY
```

O su equivalente en la biblioteca oficial instalada.

## Cuándo ofrecer web

- `NO_EVIDENCE`
- `CURRENT_DATA_REQUIRED`
- información dinámica:
  - abierto ahora
  - disponibilidad
  - precio actual
  - evento de hoy
  - horario actual
  - estado actual de un servicio

## Human in the loop

Si el usuario no pidió ya explícitamente buscar:

> “No tengo ese dato actualizado en mi base. ¿Querés que lo busque en la web?”

Guardar un objeto de consentimiento ligado a:

```text
session_id
request_id
query
expires_at
```

Un “sí” posterior habilita solamente esa búsqueda.

Cambio de tema invalida el permiso pendiente.

No permitir que el LLM invente `consent=true`.

## Frases de progreso

Sólo decirlas si hay una tarea real en curso.

Ejemplos:

- “Ok, estoy buscando.”
- “Dame un momento que reviso la información.”
- “Estoy verificando ese dato.”

No decirlas si la operación terminó instantáneamente.

Si la operación supera aproximadamente 1-1.5 s, se puede emitir una frase corta.

El usuario puede interrumpir incluso durante una búsqueda.

---

# 15. VOZ

## Moonshine

Usar la integración actual de Pipecat.

Configurar español explícitamente.

Verificar y loguear qué variante española fue cargada.

Debe correr en CPU.

No permitir fallback accidental a inglés.

Audio esperado:

- PCM mono
- 16 kHz cuando lo requiera el servicio

Moonshine puede trabajar segmentado después del VAD. Eso está bien.

La interrupción no depende de esperar la transcripción completa.

## Silero VAD

Debe detectar:

```text
USER_STARTED_SPEAKING
```

y permitir barge-in mientras Giana habla.

## Piper

Voz exacta:

```text
es_AR-daniela-high
```

CPU.

Para producción usar preferentemente:

```text
Piper HTTP server
+
PiperHttpTTSService
```

Mantener modelo caliente.

No cargar el modelo por oración.

Segmentar la salida del LLM por frases naturales para empezar a hablar sin esperar toda la respuesta.

---

# 16. INTERRUPCIONES

Requisito obligatorio.

Cuando el usuario empieza a hablar mientras Giana habla:

1. Pipecat dispara interrupción.
2. parar/invalidar generación LLM pendiente.
3. descartar texto no reproducido.
4. detener TTS.
5. vaciar audio pendiente del transporte.
6. marcar herramientas cancelables.
7. invalidar resultados tardíos mediante `generation_id`.
8. escuchar el nuevo turno inmediatamente.

Cada turno debe llevar:

```text
session_id
generation_id
```

Un resultado perteneciente a un `generation_id` viejo no puede:

- volver a hablar,
- agregar una respuesta como si fuera actual,
- iniciar búsqueda,
- modificar el turno nuevo.

No silenciar el micrófono del usuario mientras Giana habla.

---

# 17. ESTADOS DE LA CONVERSACIÓN

Usar estados explícitos simples:

```text
IDLE
LISTENING
TRANSCRIBING
RETRIEVING
THINKING
ASKING_WEB_PERMISSION
WEB_SEARCHING
SPEAKING
INTERRUPTED
ERROR
```

Frontend recibe eventos de estado.

No dejar que el LLM invente estados.

---

# 18. FRONTEND

Primero mínimo y funcional.

Debe mostrar:

- botón conectar/desconectar
- estado de micrófono
- estado actual de Giana
- transcript del usuario
- respuesta textual
- fuentes/evidencias expandibles
- aviso cuando se está buscando web
- botón textual opcional para autorizar/rechazar búsqueda web además de voz

No construyas un dashboard gigantesco.

Fluent UI.

Responsive básico.

---

# 19. ESTRUCTURA DEL REPOSITORIO

Crear algo equivalente a:

```text
giana/
  backend/
    app/
      api/
      rag/
        ingest.py
        parser.py
        catalog.py
        retrieval.py
        reranker.py
        evidence.py
        web_search.py
        llm.py
      models/
      config.py
      main.py
    tests/
    requirements.txt

  voice/
    agent.py
    pipeline.py
    piper/
    tests/
    requirements.txt

  frontend/
    src/
    package.json

  data/
    source/
    generated/

  scripts/
    ingest.py
    smoke_rag.py
    benchmark_rag.py
    verify_gpu.py
    start-dev.ps1
    start-dev.sh

  docker/
  docker-compose.yml
  .env.example
  README.md
  PROGRESS.md
  docs/
    ARCHITECTURE.md
    RAG_CONTRACT.md
    TEST_REPORT.md
```

Podés ajustar nombres sin cambiar las responsabilidades.

---

# 20. VARIABLES DE ENTORNO

`.env.example`:

```dotenv
OLLAMA_API_KEY=
OLLAMA_MODEL=deepseek-v4.1-flash
OLLAMA_BASE_URL=https://ollama.com

QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=giana_granite_v2

EMBEDDING_MODEL=ibm-granite/granite-embedding-97m-multilingual-r2
RERANKER_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
CUDA_DEVICE=0

RERANK_MAX_CANDIDATES=16
RERANK_TOP_K=6
DENSE_TOP_K=20
LEXICAL_TOP_K=20

PIPER_VOICE=es_AR-daniela-high
PIPER_URL=http://piper:5000

LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=

WEB_SEARCH_ENABLED=true
WEB_CONSENT_TTL_SECONDS=120
```

No imprimir secretos.

No copiar `.env` al frontend.

---

# 21. MISIONES — VERSIÓN RÁPIDA

Sólo **6 misiones**.

No inventes otras quince.

---

## M0 — BOOTSTRAP Y SMOKE DE HARDWARE

Objetivo: probar componentes, no diseñar.

Hacer:

1. crear estructura mínima;
2. verificar Docker;
3. verificar CUDA;
4. descargar/cargar Granite;
5. descargar/cargar mMARCO;
6. comprobar que ambos usan CUDA;
7. medir VRAM idle/modelos cargados;
8. probar una oración con Granite;
9. probar tres pares query/documento con mMARCO;
10. comprobar `OLLAMA_API_KEY` sin imprimirla;
11. smoke call a DeepSeek;
12. levantar Qdrant.

PASS cuando:

- Qdrant responde;
- Granite devuelve vector de 384 dimensiones;
- mMARCO devuelve scores;
- ambos están realmente en CUDA;
- DeepSeek responde;
- se registra consumo real.

No montar voz todavía.

---

## M1 — INGESTIÓN + RAG TEXTO FUNCIONAL

Objetivo: lograr el primer vertical slice.

Hacer:

1. parser Markdown determinista;
2. generar JSONL + SQLite;
3. sanity checks;
4. chunks;
5. embeddings Granite;
6. Qdrant;
7. FTS5;
8. hybrid retrieval;
9. RRF;
10. mMARCO condicional;
11. evidence package;
12. endpoint `/api/ask-text`.

La respuesta puede usar DeepSeek.

Antes de terminar M1 debe funcionar:

```text
curl pregunta
   ↓
respuesta
+ evidencia
+ líneas/fuentes
```

### Smoke tests obligatorios de M1

Preguntar al sistema real, no al archivo manualmente:

1. ¿Dónde puedo comer algo vegano en Minas?
2. ¿Dónde puedo tomar un helado con opciones sin gluten en Minas?
3. ¿El camping del Penitente tiene electricidad en las parcelas?
4. ¿Laguna de los Cuervos tiene camping habilitado?
5. ¿Puedo ir con mascota a Salus?
6. ¿Puedo llevar perro al Penitente?
7. ¿Dónde tomar té sin gluten en Villa Serrana?
8. ¿Hay comida vegana cerca de Mariscala?
9. Si me alojo en Granja Penitente, ¿qué lugar para comer tengo al lado?
10. ¿Hotel Minas tiene estacionamiento propio garantizado?
11. ¿Cerro Místico acepta niños pequeños?
12. ¿Nico Pérez está en Lavalleja?
13. ¿Arequita es solamente subir un cerro?
14. ¿Puedo visitar libremente Cueva Amarilla?
15. ¿Puedo ir al Parque de Minas a almorzar sin hospedarme?
16. ¿Dónde cargo un auto eléctrico si me quedo en Villa Serrana?
17. ¿Dónde puedo dormir en José Pedro Varela?
18. ¿Cuál es el teléfono de la Catedral de Minas?
19. ¿Qué puedo hacer en Minas un día de lluvia?
20. ¿Los parrilleros del Penitente son gratis y también la entrada al parque?

Condición:

- cero respuestas “no tengo información” cuando el corpus contiene la respuesta;
- no inventar lo que no está.

No pasar a voz si esto falla.

---

## M2 — RAG ROBUSTO + WEB

Objetivo: defensa contra falsas ausencias.

Implementar:

- structured fast path;
- exact entity/alias;
- FTS5;
- dense;
- RRF;
- rerank;
- neighbor/parent expansion;
- segunda oportunidad;
- reformulación máxima 3 queries;
- evidence gate;
- Ollama web search;
- consentimiento;
- web fetch;
- status/progress events;
- cancelación por `generation_id`.

Crear tests de:

- dato local existente;
- dato parcial;
- dato actual requerido;
- dato verdaderamente ausente;
- Qdrant caído;
- Ollama caído;
- permiso web aceptado;
- permiso rechazado;
- permiso expirado;
- cambio de tema.

Un fallo técnico nunca debe producir `NO_EVIDENCE`.

---

## M3 — VOZ LOCAL CON SMALLWEBRTC

Objetivo: hablar con Giana antes de montar LiveKit.

Integrar:

- Pipecat
- Silero VAD
- Moonshine ES CPU
- backend RAG/LLM
- Piper Daniela CPU
- SmallWebRTC

Probar:

```text
hablar
↓
Moonshine
↓
RAG
↓
DeepSeek
↓
Piper
↓
audio
```

Medir:

- tiempo fin de voz -> transcript
- retrieval
- primer texto LLM
- primer audio
- tiempo total percibido

No optimizar obsesivamente antes de que funcione.

---

## M4 — INTERRUPCIONES + FRONTEND

Objetivo: conversación usable.

Implementar React mínimo.

Probar barge-in:

```text
Giana habla
↓
usuario habla
↓
audio de Giana se corta
↓
nuevo turno se procesa
↓
respuesta vieja jamás vuelve
```

Testear interrupción durante:

- TTS
- generación LLM
- retrieval
- web search

El frontend debe enseñar estados reales.

---

## M5 — LIVEKIT + ACEPTACIÓN FINAL

Sólo ahora integrar LiveKit self-hosted.

Sustituir transporte SmallWebRTC por `LiveKitTransport` sin reescribir el núcleo.

Ejecutar suite completa.

Si existen fixtures del kit anterior:

- 80 casos críticos
- 133 identity checks

reutilizarlos.

Si no existen, generar una suite final equivalente a partir del corpus, pero NO con respuestas hardcodeadas en la aplicación.

Entregar:

- startup limpio
- Docker Compose
- PowerShell para Windows
- shell para Ubuntu
- reporte de consumo
- reporte de RAG
- reporte de voz/interrupción
- instrucciones de migración 3050 -> 5060 Ti

---

# 22. PERFORMANCE DEL RAG

No perseguir micro-optimizaciones antes de medir.

Runtime esperado por pregunta:

```text
structured lookup        CPU
FTS5                     CPU
Granite query embedding  GPU
Qdrant                   CPU/network local
mMARCO opcional          GPU
DeepSeek                 cloud
```

Granite sólo genera **un embedding de query** durante runtime.

Los chunks ya están embebidos.

No re-embebas el corpus por pregunta.

mMARCO sólo ve candidatos finales.

## GPU lock

Implementar un lock:

```python
asyncio.Semaphore(1)
```

o equivalente alrededor de inferencias CUDA.

Si Flask es sync, usar lock/thread-safe equivalente.

No lanzar Granite y MiniLM en paralelo.

---

# 23. CACHÉS

Cachear:

- embeddings de chunks por hash
- resolución de aliases
- consultas estructuradas frecuentes
- retrieval result por query normalizada con TTL corto
- web result con TTL razonable, marcado como web y fecha

No cachear como verdad eterna:

- “abierto ahora”
- disponibilidad
- precios actuales

---

# 24. CITAS Y EVIDENCIA

Cada respuesta local debe poder devolver en JSON:

```json
{
  "answer": "...",
  "state": "ANSWERABLE",
  "evidence": [
    {
      "title": "...",
      "start_line": 2306,
      "end_line": 2316,
      "source_refs": [232],
      "text": "..."
    }
  ]
}
```

Frontend puede ocultar/expandir evidencia.

La voz no necesita leer las citas en voz alta.

---

# 25. WEB NO CONTAMINA EL RAG AUTOMÁTICAMENTE

Resultados web:

```text
ephemeral
source=web
timestamp
url
```

No insertar automáticamente en Qdrant como conocimiento permanente.

Si en el futuro se quiere incorporar algo, eso es otra función de curación.

---

# 26. ERRORES

API debe distinguir:

```text
RAG_NO_EVIDENCE
RAG_PARTIAL
RAG_INDEX_UNAVAILABLE
GPU_MODEL_ERROR
LLM_UNAVAILABLE
WEB_AUTH_ERROR
WEB_SEARCH_ERROR
STT_ERROR
TTS_ERROR
```

Nunca usar un único:

```text
"no encontré información"
```

para todo.

---

# 27. TESTS DE GPU

Crear:

```text
python scripts/verify_gpu.py
```

Debe imprimir SIN secretos:

- GPU
- CUDA disponible
- modelo embedding
- device embedding
- modelo reranker
- device reranker
- vector dim
- VRAM antes
- VRAM después
- VRAM pico de una consulta
- latencia embedding
- latencia reranking

Guardar reporte JSON en:

```text
reports/gpu.json
```

No falsificar datos para la 5060 Ti si sólo se probó la 3050.

---

# 28. CRITERIOS DE ACEPTACIÓN

No uses “perfecto” como sinónimo de terminado.

Giana V2 se acepta cuando:

### Ingestión

- fuente preservada
- parser reproducible
- catálogo esperado presente
- FAQ presentes
- fuentes presentes
- ningún bloque narrativo importante eliminado

### RAG

- los 20 smoke tests pasan
- cero falsas abstenciones críticas en la suite final
- consultas exactas no dependen innecesariamente de reranker
- fallback lexical puede rescatar nombres propios
- dense puede rescatar paráfrasis
- reranker mejora orden sin destrozar recall
- SYSTEM_ERROR nunca se presenta como falta de conocimiento

### GPU

- Granite y mMARCO realmente en CUDA
- no Qwen
- no copias múltiples
- consumo medido
- proceso estable en RTX 3050 8 GB

### LLM

- DeepSeek Cloud responde
- no filtra API key
- no inventa fuera de evidencia

### Web

- requiere consentimiento cuando corresponde
- puede cancelarse
- resultado queda identificado como web

### Voz

- Moonshine español CPU
- Piper Daniela CPU
- barge-in funcional
- audio viejo no regresa después de interrupción

### Transporte

- SmallWebRTC funcional
- LiveKit funcional al final

---

# 29. COSAS QUE ESTÁN PROHIBIDAS

No hacer ninguna de estas cosas:

- volver a Qwen3-Embedding-0.6B
- volver a Qwen3-Reranker-0.6B
- Whisper
- STT/TTS cloud
- Kokoro
- LangChain
- LlamaIndex
- Chroma en lugar de Qdrant
- Elasticsearch
- SearXNG
- Kubernetes
- Redis si no existe una necesidad demostrada
- MariaDB si no existe una necesidad demostrada
- microservicios por cada clase
- varios workers CUDA
- embeddings por request del corpus completo
- rerank de docenas de páginas
- extracción total del Markdown mediante LLM
- “no tengo información” después de un único top-k
- búsqueda web automática sin permiso cuando no fue solicitada
- hardcodear las respuestas de los tests
- modificar tests para hacer pasar código roto

---

# 30. PRIMER MENSAJE QUE QUIERO DE VOS

No respondas con veinte párrafos de planificación.

Respondé brevemente:

```text
M0 iniciado.
Voy a verificar workspace, Docker, CUDA, Granite, mMARCO, Qdrant y Ollama.
Después construiré el vertical slice RAG de M1 antes de tocar voz o LiveKit.
```

Y empezá a ejecutar.

---

# 31. COMPORTAMIENTO DURANTE EL DESARROLLO

Trabajá de forma autónoma.

No me pidas confirmación entre M0-M5 para decisiones ya especificadas.

Preguntá solamente si:

- falta físicamente el archivo fuente;
- falta `OLLAMA_API_KEY`;
- una licencia impide legalmente continuar y necesita decisión humana;
- un puerto está ocupado por un servicio que no podés tocar;
- hay riesgo de borrar datos existentes;
- la especificación contiene una contradicción imposible.

Si una pieza opcional falla, continuá con lo independiente.

Al terminar cada misión actualizá `PROGRESS.md`.

No me digas que algo funciona si no ejecutaste su test real.

EMPEZÁ AHORA.
