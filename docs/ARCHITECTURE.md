# Arquitectura del chat

```text
Navegador
  -> Waitress + Flask :5000 (interfaz compilada y API)
       -> router de intención y respuestas locales de conversación/persona/reloj
       -> guía SQLite FTS5 + Granite ONNX INT8 CPU + Qdrant embebido
       -> fusión RRF por bloque y mMARCO ONNX INT8 CPU
       -> DeepSeek en Ollama Cloud, a través de Ollama local :11434
       -> búsqueda y lectura web cuando corresponde
```

## Recuperación

El corpus turístico original y sus datos estructurados se conservan. La consulta
se resuelve con el historial reciente, se busca en FTS5 y en el índice vectorial,
y los resultados se fusionan por bloque para restaurar evidencia completa.
El reranker evalúa los candidatos antes de seleccionar las fuentes para la
respuesta. Se preservan las coincidencias exactas del catálogo y las restricciones
territoriales de Lavalleja.

Granite usa pooling CLS y normalización L2, sin prefijos de consulta/documento.
Los dos modelos utilizan únicamente el proveedor `CPUExecutionProvider`, pesos
UINT8 preparados para AVX2, lotes limitados, 512 tokens y cuatro hilos de inferencia.
Se desactiva la espera activa de los hilos para reducir consumo en reposo.
Las sesiones se cargan una vez y las llamadas se serializan con un bloqueo.

`model_policy.py` fija los únicos dos IDs admitidos, revisiones y SHA256 oficiales.
`prepare_models.py` valida la integridad de los cuatro archivos descargados.
El backend y el indexador comparten exactamente el mismo tokenizador,
normalización, límite de tokens y artefacto de Granite.

La colección `giana_granite_cpu_v1` pertenece exclusivamente a este perfil.
`storage/index_manifest.json` registra el hash del corpus y la firma de inferencia.
Un índice sin firma compatible o con recuento/dimensiones incorrectos se
reconstruye al arrancar. Una reconstrucción interrumpida no pasa `/ready`.
Sólo un proceso puede abrir el almacenamiento Qdrant local; el indexador se
ejecuta con el backend detenido.

## Respuestas y web

Los saludos simples, la identidad y el reloj se resuelven localmente. El router,
la evaluación de evidencia y las respuestas turísticas usan exclusivamente
`deepseek-v4.1-flash:cloud`, configurado en `runtime_config.json`.
La selección de herramientas, los límites de alcance, la evaluación de suficiencia,
la búsqueda web y las fuentes permanecen en sus módulos originales.

El transporte predeterminado utiliza la sesión iniciada de la aplicación Ollama;
no descarga pesos de un modelo generativo. El acceso directo a `ollama.com`
requiere `OLLAMA_API_KEY`. DDGS aporta búsqueda web sin credenciales y la lectura
web conserva los límites y las validaciones de URLs existentes. La evidencia web
es temporal y nunca se inserta en la guía ni en la colección vectorial.

## Interfaz y operación

La interfaz mantiene el diseño, el avatar, las sugerencias, el historial de sesión,
las fuentes, el aviso de búsqueda web y el botón de nueva conversación. React y
Zustand son sus únicas dependencias de ejecución. Una nueva conversación descarta
las respuestas pendientes; las solicitudes tienen un plazo de 90 segundos.

En operación sólo se ejecuta el backend, que sirve los recursos compilados de
Vite. El servidor se enlaza a la interfaz de loopback. Ollama permanece como
servicio independiente del usuario. El modo de desarrollo añade Vite en `5173`.
