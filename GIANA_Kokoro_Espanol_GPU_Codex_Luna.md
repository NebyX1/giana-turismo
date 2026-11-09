# GIANA: KOKORO FEMENINO EN ESPAÑOL, GPU Y AUDIO SIN RECORTES

## Encargo

Migrá únicamente el TTS principal de Giana desde Piper a Kokoro local, con la voz femenina española `ef_dora` y aceleración CUDA. Además, verificá y corregí los recortes en el recorrido texto → síntesis → reproducción que puedan persistir independientemente del modelo.

No reconstruyas Giana. La aplicación ya funciona. Conservá los arreglos de conversación, STT, RAG, WebRTC y frontend. Trabajá sobre el checkout LOCAL real, que puede tener cambios aún no publicados en GitHub.

Repositorio: https://github.com/NebyX1/giana-turismo

La versión publicada revisada aún contiene Moonshine y `TracedPiperTTSService`. NO restaures ese STT si el checkout local ya tiene Whisper large-v3-turbo funcionando. El STT instalado y funcional no se modifica en esta misión.

### Configuración objetivo

- TTS: `hexgrad/Kokoro-82M`, modelo multilingüe v1.0.
- Voz: `ef_dora`, femenina en español.
- Runtime principal: paquete oficial `kokoro`, PyTorch CUDA.
- Idioma de KPipeline: `lang_code="e"`.
- Velocidad inicial: `1.0`.
- Salida nativa: mono, 24.000 Hz.
- Integración: adaptador pequeño basado en `TTSService` de la versión de Pipecat instalada.
- Un modelo residente por proceso de voz, no uno por frase o conexión.
- Piper conservado como rollback explícito, sin cargarlo innecesariamente durante la operación con Kokoro.

No usar `pf_dora` (portugués), una voz inglesa por defecto ni una voz masculina. No prometer acento uruguayo: la voz solicitada es la femenina española disponible en el catálogo.

La integración nativa `KokoroTTSService` de Pipecat utiliza `kokoro-onnx`; NO asumir que admite el parámetro PyTorch `device="cuda"`. Esta misión elige la implementación oficial `kokoro` con PyTorch y un adaptador mínimo para no modificar los proveedores ONNX usados por otras partes del sistema.

Fuentes de implementación:
https://github.com/hexgrad/kokoro
https://huggingface.co/hexgrad/Kokoro-82M
https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
https://docs.pipecat.ai/api-reference/server/services/tts/kokoro

Consultá las firmas reales instaladas, no inventes parámetros.

## M1. Preservar la base y capturar dónde se recorta

Leé `Gianna_viability.md` y los archivos actuales de voz, TTS, arranque, configuración y pruebas. Guardá revisión Git, cambios locales, versiones y configuración sin secretos. No hacer reset ni checkout forzado.

No ejecutar Docker prune, no borrar volúmenes o modelos, no reindexar ni actualizar todas las dependencias. No cambiar Gemma, Whisper/Moonshine activo, Silero, SmartTurn, Granite, mMARCO, Qdrant, consentimiento web o diseño del frontend.

Crear una sesión real en:
`logs/test/<timestamp>-kokoro-migration/`

Usar rutas absolutas derivadas del repo. Verificar escritura y lectura física. Guardar stdout y stderr del proceso afectado, eventos y resultados; no fabricar archivos estáticos de “sin errores”.

Antes del cambio, ejecutar una respuesta fija de varias frases con Piper y guardar, cuando esté disponible:
1. Texto canónico.
2. Texto entregado a cada llamada TTS.
3. Audio completo generado por el proveedor.
4. Audio en la entrada del transporte.
5. Eventos de reproducción/cancelación del navegador.

Separar causa confirmada de hipótesis. Un WAV generado correctamente y un audio cortado en WebRTC no demuestran un fallo del modelo.

En el código publicado hay dos puntos que DEBÉS revisar en la copia local:
- `TracedPiperTTSService.run_tts` emite `turn_finished` al acabar cada llamada, aunque pueda representar sólo una oración.
- `_active_assistant_generation_id` se limpia al terminar de emitir texto, antes de demostrar que terminó la reproducción.

No afirmes que sean la causa sin reproducirlo. Verificá si esos eventos hacen que se cierre, cancele o resetee prematuramente una respuesta.

## M2. Preparar Kokoro CUDA sin romper dependencias

Usá la .venv funcional. Añadí y fijá únicamente `kokoro`, sus dependencias necesarias y utilidades de audio que falten. Ejecutá `pip check` antes y después.

Conservá la instalación CUDA de PyTorch que ya funciona. No reinstalar drivers, toolkit o CTranslate2 por reflejo. Si existe conflicto real de dependencias, detené la migración y documentalo; no destruyas la base funcional intentando resolverlo a ciegas.

Instalá/verificá eSpeak NG y la fonemización española requeridos por Kokoro. En Windows, usar fuentes oficiales y rutas válidas para el mismo proceso de Python. No descargar DLL de sitios desconocidos. La síntesis neuronal va en GPU; fonemización y preparación pueden permanecer en CPU.

Descargá una sola vez modelo, configuración y voz `ef_dora`. Registrá revisión y hashes. Prepará todos los recursos antes de activar modo offline. Comprobá que la siguiente carga puede usar archivos locales sin volver a descargar.

Configuración de proyecto sugerida:

```dotenv
TTS_PROVIDER=kokoro
KOKORO_MODEL=hexgrad/Kokoro-82M
KOKORO_VOICE=ef_dora
KOKORO_LANG_CODE=e
KOKORO_DEVICE=cuda
KOKORO_SPEED=1.0
KOKORO_DTYPE=float32
```

Son variables del proyecto, no parámetros mágicos de Pipecat. Implementá su lectura y paso real al proceso de voz. Conservá rutas con espacios y secretos en el entorno.

Inicialización conceptual:

```python
KPipeline(
    lang_code="e",
    repo_id="hexgrad/Kokoro-82M",
    device="cuda",
)
```

Adaptala a las firmas instaladas y a la carga local verificada.

Empezá con FP32 y `.eval()`/`torch.inference_mode()` para establecer calidad y estabilidad. No aplicar `.half()` a todo el modelo/vocoder a ciegas. Optimizá precisión sólo si hace falta y después de comparar audios, latencia y estabilidad.

Validar CUDA con síntesis REAL, device de parámetros, PID propietario y métricas. `nvidia-smi` o `torch.cuda.is_available()` aislados no bastan. No usar fallback CPU silencioso.

Antes de integrar al chat generar tres WAV completos a 24 kHz:
- Bienvenida de Giana.
- Párrafo turístico de varias frases.
- Lista de nombres: Minas, Lavalleja, Cerro Arequita, Villa Serrana, Salto del Penitente, Solís de Mataojo.

Guardar textos y audios para escucha. No afirmar que la voz suena mejor sin evaluación; eso lo confirma el usuario.

## M3. Integrar TTS preservando TODOS los fragmentos

Crear/reutilizar una fábrica de TTS y un adaptador local pequeño, por ejemplo `voice/tts/kokoro_service.py`. Evitar un servidor extra, contenedor GPU o framework nuevo. No editar `site-packages`.

Mantener los contratos de `TTSService`, lifecycle, frames, métricas y contexto de la versión instalada. No copiar indiscriminadamente overrides de Piper ni duplicar start/stop frames que la base ya maneja.

### Modelo y concurrencia

Compartir sólo runtime/modelo residente. Cada sesión conserva su propio estado de reproducción, contexto y cancelación.

Una síntesis activa; cola acotada con backpressure. Un executor de un worker es suficiente inicialmente. No cargar el modelo por reconexión. Preparar y calentar fuera del camino crítico de la primera respuesta.

KPipeline produce un generador: consumir TODOS sus resultados. No quedarse con `next(generator)`, el primer bloque o el último bloque. La llamada y la iteración efectiva de síntesis deben ejecutarse fuera del event loop de Pipecat.

Entregar los bloques mediante una cola thread-safe/asíncrona acotada. No tocar una `asyncio.Queue` desde otro hilo sin el puente apropiado. No acumular audio de respuestas enteras si puede emitirse por bloques ordenados.

Al cancelar una tarea async, una inferencia CUDA en marcha puede seguir ejecutándose. Mantener control de ese trabajo hasta que termine y descartar su salida obsoleta. No iniciar más inferencias en paralelo porque se canceló sólo el await.

### Segmentación sin truncar

Debe existir una sola fuente de texto canónico y una única política coherente de segmentación. Reutilizá la agregación de Pipecat y agregá únicamente la partición adicional exigida por el modelo.

Verificá el límite real de fonemas/tokens del modelo instalado. Las rutas de Kokoro consultadas contienen límites de aproximadamente 510 y pueden truncar exceso. Esto NO puede pasar en Giana.

Segmentar por frases/cláusulas y comprobar el tamaño después de fonemizar. Si una frase excede el límite, dividirla en límites de palabras y repetir la verificación, conservando todo el contenido y el orden. No cortar cadenas de fonemas a 510 ni ignorar avisos de truncamiento.

No contar letras como si fueran tokens fonéticos. Usar un presupuesto conservador inferior al máximo real. No partir abreviaturas, números o teléfonos indiscriminadamente. No sintetizar palabra por palabra.

No alargar una respuesta inventando contenido para mejorar la voz. Si hay varias frases cortas ya disponibles, pueden agruparse sin una espera artificial larga.

Al recibir fin de respuesta del LLM, vaciar también el fragmento pendiente aunque no termine en punto. Ese fin cierra la ENTRADA de texto; no significa que el audio ya terminó de reproducirse.

### Identidad y finalización de audio

Cada trabajo conserva:
`session_id`, `turn_id`, `generation_id`, `context_id` y `segment_index`.

No atribuir bloques usando un diccionario global mutable que otra respuesta pueda sobrescribir.

Distinguir:
- Segmento sintetizado.
- Audio encolado/enviado.
- Cola de respuesta drenada.
- Reproducción observada.
- Respuesta interrumpida.

No emitir “turno completo” al finalizar el primer segmento. No cancelar/limpiar los siguientes segmentos por un evento de fin parcial. No desactivar la cancelación de salida sólo porque terminó el LLM.

No esperar un nuevo `playing`/`ended` del HTMLAudioElement para cada frase: el track WebRTC permanece vivo y puede reproducir silencio. Usar eventos de transporte y mediciones pertinentes; no confundir un reproductor activo con palabras audibles.

### Formato y sample rate

Kokoro genera mono a 24.000 Hz. Mantener 16.000 Hz en la captura STT si ésa es la configuración actual.

Para la salida, mantener el transporte actual y remuestrear correctamente una sola vez cuando sea necesario. Registrar tasas reales de origen y destino. Nunca etiquetar muestras de 24 kHz como 16 kHz cambiando sólo metadatos.

Convertir float a PCM int16 con rango correcto, clipping numérico seguro y validación de valores finitos. No enviar una cabecera WAV como si fuese PCM raw. Respetar sample rate, canales, bytes por muestra y `context_id` en los frames.

No recortar ataques/finales de palabras con eliminación agresiva de silencios. Vaciar el remuestreador según su API sin perder su cola. No insertar pausas grandes para disimular huecos.

Conservar el elemento de audio persistente del navegador. No llamar `track.stop()` ni limpiar `srcObject` al finalizar una frase. Asegurar que sólo el track remoto llegue al parlante.

## M4. Texto, errores y barge-in

Todo contenido enviado a TTS debe quedar registrado en el chat, incluidos bienvenida, avisos y errores hablados.

Derivar chat y TTS del mismo texto canónico. La normalización para pronunciación puede expandir “Gral.”, números o símbolos, pero no omitir ideas ni alterar hechos.

Guardar por respuesta:
- `assistant_text`.
- `spoken_text` normalizado y transformaciones.
- Segmentos ordenados con intervalos del texto fuente.
- Bloques de audio, muestras y duración.
- Estado de cancelación y reproducción, sin afirmar que se oyó lo no comprobado.

Comparar cobertura del texto fuente completo y orden al terminar la respuesta. No comparar cada oración aislada contra el párrafo entero. El test debe detectar un bloque intermedio perdido, no sólo si llegó la última palabra.

Si se interrumpe, conservar el historial y marcar la respuesta interrumpida; distinguir lo generado de lo reproducido. No continuar con audio viejo después de un nuevo turno.

Conservar barge-in. No “resolver” recortes deshabilitando el micrófono. Si se sospecha eco, comparar auriculares/parlantes y registrar VAD y cancelación. El audio del bot no debe provocar preguntas falsas.

Un fallo TTS debe producir un error TTS y mantener el texto visible. No mostrar “no pude acceder al micrófono” porque falló Kokoro, playback o la cola. Preservar excepción original y contexto en los logs.

Agregar diagnóstico útil, sin otro dashboard:
proveedor, voz, device, segmento actual/total, cola, última cancelación y componente del error.

## M5. Pruebas que detecten cortes reales

Reutilizá el banco existente. No construir otra plataforma QA ni introducir lógica de prueba en producción.

Casos obligatorios:
1. Bienvenida tras el primer clic de micrófono.
2. Frase corta: “Sí, claro. Estoy para ayudarte.”
3. Párrafo turístico de tres o más frases.
4. Texto con “Av.”, “Gral.”, cifras y puntuación.
5. Topónimos locales y acentos.
6. Último fragmento sin punto final.
7. Texto que exceda claramente el límite de una inferencia.
8. Interrupción durante síntesis/reproducción y respuesta siguiente normal.
9. Diez turnos seguidos y tres reconexiones sin duplicar el modelo.
10. Error TTS controlado correctamente registrado, seguido de recuperación.

En el caso largo incluir al final:
“La última palabra de esta prueba es Lavalleja.”

Verificar cobertura de TODOS los segmentos, no sólo esa frase final. Guardar texto, índices, audio local y evidencia de audio recibido en navegador cuando el harness lo permita.

Si una muestra directa Kokoro está completa y WebRTC la corta, reparar la integración; no culpar al modelo. Si el WAV directo ya omite palabras, documentar el problema de síntesis.

Una retranscripción con STT puede servir de alarma, no de prueba absoluta de que todo fue pronunciado. `play()` resuelto tampoco demuestra ausencia de palabras perdidas. Separar tests técnicos de escucha humana.

Medir con toda Giana funcionando, incluyendo el STT GPU realmente instalado, Granite y mMARCO:
- VRAM antes/después y pico global.
- Cargas del modelo por PID.
- Tiempo de cola y primera salida Kokoro.
- Tiempo total de síntesis y duración de audio.
- RTF = segundos de síntesis / segundos de audio.
- Fin de voz del usuario → primera salida remota observable.
- Bloqueos del event loop y vuelta al reposo.

No usar sólo estadísticas del allocator PyTorch para describir el consumo total: el STT puede usar CTranslate2 en otro runtime/proceso.

No prometer un total fijo de VRAM por el tamaño de los pesos. Objetivo inicial en 8 GB: conservar al menos aproximadamente 1 GiB de margen en las pruebas. Si no alcanza, detenerse y reportar alternativas; no mover otros modelos a CPU sin avisar.

## M6. Arranque, rollback y entrega

Modificar scripts existentes para seleccionar TTS por configuración.

Con `TTS_PROVIDER=kokoro`:
- No exigir voz Piper ni un `/synthesize` de Piper como requisito de arranque.
- Cargar y calentar Kokoro antes de declarar TTS ready.
- Verificar que la instancia residente es la que atenderá las conexiones.
- No hacer síntesis en cada health check.
- No descargar modelos al pulsar micrófono.
- No dejar Piper corriendo como residuo cuando no se usa.

Con `TTS_PROVIDER=piper` debe seguir funcionando el rollback explícito.

No desinstalar Piper hasta que el usuario acepte la nueva voz. No alternar proveedores silenciosamente a mitad de una respuesta.

Reiniciar sólo servicios afectados y dejar Giana levantada. No activar LiveKit ni recrear Docker/Qdrant.

Crear:
`reports/GIANA_KOKORO_GPU_MIGRATION.md`
`reports/GIANA_KOKORO_GPU_MIGRATION.json`

Incluir: revisión local, cambios, modelo/revisión, voz, device, dtype, versiones, causa confirmada de recortes o investigación pendiente, segmentación, resampling, cobertura texto/audio, errores, latencias, VRAM, pruebas y rollback.

Si la migración falla, restaurar el proveedor funcional y conservar los cambios para revisión. No dejar una aplicación muda.

Respuesta final breve:

KOKORO GPU: PASS / PARTIAL / BLOCKED
Modelo/voz:
Device/dtype:
Cobertura completa de texto:
Audio local:
Audio por WebRTC:
Barge-in:
VRAM total medida:
STT preservado:
Rollback:
Reportes:
Frontend: http://localhost:5173/?debug=1
Pendiente: escucha humana y preferencias de voz.

Implementá y ejecutá estas pruebas. No respondas sólo con un plan ni declares calidad humana verificada sin la escucha del usuario.
