# Recuperación de arquitectura y aceptación — 19/09/2026

> **Nota de estado actual (20/09/2026).** Este documento conserva decisiones y
> resultados históricos de la recuperación del 19/09. La arquitectura operativa
> vigente está descrita en [ARCHITECTURE.md](ARCHITECTURE.md). Desde entonces,
> el código incorpora `whisper_turbo` como STT predeterminado mediante
> faster-whisper/CTranslate2 en CUDA, conserva Moonshine como rollback y añade el
> adaptador Kokoro CUDA. Los builders actuales de `voice/pipeline.py` siguen
> usando Piper HTTP para TTS; Kokoro no debe describirse como TTS activo hasta que
> esos builders lo seleccionen.

La versión aprobada por el gate anterior NO acreditaba una entrega funcional:
`Hola Giana, ¿estás ahí?` se enviaba a recuperación turística, el formato inválido
del modelo producía un 503 y voz lo presentaba como fallo de la guía. El conjunto
anterior no incluía ese saludo compuesto. Sus resultados históricos no se borran.

## Alternativas medidas

Se compararon reglas, selección JSON y selección nativa de herramientas con el
mismo conjunto de 30 entradas, incluidas correcciones y contexto. Se conservaron
las respuestas, errores y latencias, no sólo el resultado agregado.

| Configuración | Aciertos / 30 | Observación |
| --- | --- | --- |
| Reglas originales | 18 | Comparación inicial `comparison-1789860484` |
| Reglas con saludos componibles | 26 | Todavía insuficientes para contexto |
| Gemma4, herramientas con consulta contextual | 30 | Alternativa rápida |
| DeepSeek v4.1 Flash, herramientas con consulta contextual | 30 | Candidato elegido |
| GLM 5.3, herramientas con consulta contextual | 20 | Configuración ensayada no aceptada |
| Gemma4, JSON | 29 | Comparación ampliada |
| DeepSeek v4.1 Flash, JSON | 30 | Sin ventajas observadas sobre herramientas |
| GLM 5.3, JSON | 0 | Fallos de formato en la configuración ensayada |

Resultados ampliados: `logs/test/architecture-repair/comparison-1789860923/RESULTS.json`.
No son un ranking general de los modelos. `think=false` y el límite de generación
del selector son parte de la configuración evaluada. GLM no queda declarado
incapaz: queda descartada ESTA combinación para la aplicación.

Comparación de respuestas sobre las mismas fuentes: diez escenarios por modelo.
DeepSeek y Gemma pasaron 10/10; GLM no cumplió el contrato de salida en 10/10.
Resultados: `answers-1789860942/RESULTS.json`. Una ejecución anterior falló por un
error del cliente experimental (chat sin mensaje user); se conserva, pero NO se
utiliza como comparación de capacidad de los modelos.

## Decisión implementada

1. Saludos puros componibles: vía local que consume TODA la frase. No depende
   de red, buscador, índice ni modelo. Un saludo seguido de una consulta no usa
   esa vía. Las variantes ambiguas pasan a interpretación semántica.
2. Selector semántico DeepSeek con herramientas permitidas: conversación,
   conocimiento local, web, reloj, identidad y fuera de alcance. Consulta autónoma
   para resolver referencias. Sólo acepta una herramienta y argumentos validados.
3. Ejecución controlada: RAG existente, investigación web existente o reloj real.
   No se permite ejecutar código ni herramientas arbitrarias. El modelo no puede
   anular una prohibición expresa de búsqueda web.
   En RAG, la consulta original y la reformulación semántica se recuperan por
   separado y se fusionan sin eliminar la evidencia original. La reformulación
   puede resolver referencias, pero no reemplazar hechos o topónimos del usuario.
4. Respuesta basada en evidencia. Si la guía no contiene el dato central, web en
   el mismo turno; si el JSON es inválido, un reintento acotado con Gemma. Una
   transmisión incompleta no se aprueba como respuesta completa.
5. Agenda: fechas, horas e índices de fuente estructurados. Comprobación local
   del período y del horario de inicio, además de interpretación de fuentes.
   Si ambas generaciones insisten en incluir candidatos vencidos, se conservan
   sólo candidatos temporalmente válidos y se redacta desde esos datos, nunca
   desde la prosa inválida. Sin candidatos válidos se activa la recuperación web
   existente; no se afirma que no existan actividades.

La configuración no secreta está en `backend/app/runtime_config.json` y tiene
prioridad sobre el antiguo `OLLAMA_MODEL` de `.env`. `/ready` publica los modelos y
el modo realmente cargados. El build ID incluye ese JSON. Claves y URL del servicio
continúan en `.env`. Cambiar configuración requiere reiniciar y volver a probar.

En la decisión histórica de este documento no se reemplazaron VAD ni WebRTC y se
conservó Piper como TTS del pipeline. El estado posterior de STT y el adaptador
Kokoro se documenta en `docs/ARCHITECTURE.md`. El mensaje de error de voz deja de
culpar a la guía por cualquier fallo del backend.

La prueba real posterior descubrió un defecto en la barrera del turno: al retomar
habla después de una pausa, la transcripción de la primera parte seguía marcada
como lista. SmartTurn cerraba con ese texto viejo mientras Whisper procesaba la
segunda parte. Ahora se invalida esa marca al reanudar y se vuelve a comprobar al
cerrar la espera. La regresión demora 800 ms el segundo transcript y exige una
única consulta completa; voz real reproduce también la frase original.

Texto y voz comparten `conversation_id`, independiente del ID de transporte.
La reconexión conserva contexto en el backend y Nueva conversación desconecta la
voz y crea otra identidad. Las respuestas de texto pendientes ya no pueden
insertar mensajes, errores o consentimiento en una conversación recién creada.
El historial del backend sigue siendo memoria de proceso: no se promete recuperar
contexto semántico después de reiniciar el servidor.

## Referencias de implementación

Se adoptó el patrón de selección por modelo y ejecución controlada, no una copia
indiscriminada ni una afirmación de que otro proyecto garantiza este resultado:

- [Ollama: herramientas y continuación con resultados](https://docs.ollama.com/capabilities/tool-calling).
- [Pipecat: ejemplo oficial de function calling](https://github.com/pipecat-ai/pipecat/blob/main/examples/getting-started/07-function-calling.py).
- [DeepSeek v4.1 Flash en Ollama](https://ollama.com/library/deepseek-v4.1-flash:cloud).
- [GLM 5.3 en Ollama](https://ollama.com/library/glm-5.3:cloud).

No es un bucle de agente abierto: hay límites de herramientas, intentos y tiempo.

## Cambios en las pruebas y límites

- 49 escenarios HTTP, dos repeticiones: 98 consultas.
- Seis diálogos separados, 27 turnos, con referencias, negaciones, cambios de
  lugar/dieta, saludos mezclados y recuperación del tema después de conversar.
- Navegador escrito: 15 turnos, historial, recarga y nueva conversación.
- Voz prolongada: 14 turnos con pausa y reconexión; segunda conversación de cinco
  turnos comienza con la frase fallida e interrumpe una respuesta larga mientras
  está sonando. Se comprueba detención, reemplazo y continuidad posterior.
- Voz/contexto: cuatro turnos después de una consulta escrita, con referencias
  después de reconectar y aislamiento al comenzar una nueva conversación.
- UI aislada: respuestas tardías exitosas, fallidas y de consentimiento después
  de Nueva conversación; estas tres pruebas simulan HTTP, no el modelo real.
- Quince métodos nuevos de resiliencia, incluidos 108 saludos compuestos y 432
  combinaciones con consulta añadida, proveedores caídos, formatos inválidos,
  citas inválidas, herramientas desconocidas, cuerpos HTTP incorrectos,
  transmisión truncada y cruce del horario de eventos. Son contratos, no 540
  conversaciones humanas. Se mantienen las suites anteriores y el barrido de fechas.

El cliente web distingue errores transitorios de cuota agotada. Reintenta como
máximo una vez 408/429/5xx o un error de conexión, con espera corta; no reintenta
autenticación, límites con Retry-After largo ni el mensaje explícito de cuota de
sesión. Una cuota agotada produce `WEB_QUOTA_EXCEEDED`, nunca «no hay eventos».
Las pruebas completas requieren cuota disponible; ninguna respuesta simulada o
resultado histórico se acepta como sustituto de una búsqueda real.

Las grabaciones de entrada Microsoft Helena ahora se generan con PowerShell 7:
PowerShell 5 interpretaba el UTF-8 de las frases con otra codificación y dañaba los
acentos de la propia prueba. El generador falla explícitamente si se ejecuta con 5.

Entre Sierras dejó de ser una prueba de evento FUTURO a las 20:30 del 19/09/2026.
Antes de esa hora debe encontrarse; después no debe ofrecerse como próximo. La
agenda de octubre mantiene un positivo obligatorio. El test ya no prohíbe
mencionar una exposición vieja al explicar por qué se descartó: prohíbe
recomendarla como vigente. Esta distinción no elimina el fallo real de horario,
que motivó la validación estructurada. Corridas fallidas quedan conservadas.

Ninguna suite finita certifica todas las conversaciones, fuentes web futuras,
micrófonos, acentos o entornos. La prueba de voz usa audio controlado y transporte
real; la escucha humana y pruebas de campo son una dimensión adicional.
