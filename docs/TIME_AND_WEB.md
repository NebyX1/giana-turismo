# Reloj y búsqueda web de Giana

- La fuente del tiempo es el reloj del servidor convertido con ZoneInfo a
  `America/Montevideo`. La dependencia `tzdata` es necesaria en Windows.
- `/api/time` devuelve fecha, hora, día de semana, zona, offset y límites de la
  semana, con `Cache-Control: no-store`.
- Las preguntas directas de fecha/hora se responden sin LLM ni RAG. Cada petición
  toma una lectura nueva. Los demás prompts también reciben ese reloj.
- Los eventos actuales y las solicitudes explícitas de web usan búsqueda real.
  “Esta semana” se convierte en fechas concretas y no se pierde en el seguimiento.
  Para recomendar planes quedan excluidos los días de esa semana ya pasados.
- Para eventos, `web_research.py` ejecuta tres búsquedas en paralelo, ancladas a
  localidad, días, meses y año; deduplica enlaces, diversifica dominios y lee hasta
  ocho páginas por ronda. Las fechas ordenan, no eliminan párrafos.
- El modelo recibe el contexto completo de las páginas (hasta 16000 caracteres
  por fuente), el reloj, el período y el historial. Debe relacionar año/edición y
  fecha aunque estén en párrafos separados; distinguir publicación, inscripción y
  función; explicar datos faltantes y no trasladar “esta semana” de una noticia vieja
  a la semana actual. Las fuentes son datos no confiables, no instrucciones.
- Se eliminó el filtro regex que impedía invocar el modelo y devolvía una respuesta
  fija. Una búsqueda completada, incluso vacía, pasa por análisis. `ANSWERABLE`
  requiere evaluación positiva de suficiencia. Si falta evidencia central se hace
  una segunda ronda acotada en el mismo turno, manteniendo lugar/período. Si sigue
  faltando, `NO_CONFIRMED_RESULT` explica el límite sin afirmar que no existan eventos.
  Si todas las búsquedas fallan, `SYSTEM_ERROR` informa el problema técnico.
- Una consulta al RAG con fragmentos pero sin respuesta suficiente también activa
  web automáticamente, salvo prohibición explícita del usuario. Se conserva
  `rag_invoked=true` y se registra `fallback_reason`.
- La API expone `llm_invoked`, `search_queries`, `search_attempts`, `sources_read`
  y fuentes completas. Si falla la lectura se conserva el extracto identificándolo
  como `search_excerpt`, sin contar la página como leída. Un fallo parcial no tapa
  las otras consultas exitosas. Las fuentes siguen disponibles como enlaces.
- La API de búsqueda/fetch utilizada es la ya configurada con Ollama; no se
  cambió de proveedor ni se expusieron credenciales. Referencia:
  [documentación oficial](https://docs.ollama.com/capabilities/web-search).

## Pruebas

El control completo vigente está documentado en [QUALITY_GATE.md](QUALITY_GATE.md).

```powershell
.venv\Scripts\python.exe scripts/test_time_web.py
.venv\Scripts\python.exe scripts/test_intent_router.py
.venv\Scripts\python.exe scripts/test_conversation_regressions.py
.venv\Scripts\python.exe scripts/test_web_reasoning_live.py
node tests/e2e/time_web_text.mjs
$env:GIANA_E2E_MODE = 'web-research'
node tests/e2e/conversation_audio.mjs
Remove-Item Env:GIANA_E2E_MODE
```

Las pruebas unitarias congelan el reloj y simulan la red para comprobar medianoche,
fin de año, fuentes completas, deduplicación, errores parciales/totales y seguimiento.
No prueban calidad del modelo. `test_web_reasoning_live.py` usa el modelo REAL con
evidencia sintética controlada para evaluar fechas separadas, noticias viejas,
fechas no anunciadas, períodos relativos y solapamiento de intervalos.

Las pruebas de navegador no simulan backend, reloj ni buscador. Los casos positivos
están fechados al 19/09/2026: exigen Semana de Lavalleja del 7 al 11 de octubre y,
para esta semana, Entre Sierras a las 20:30. Una negativa genérica NO pasa. Después
verifican cambio de tema, reloj e historial. Al ejecutar en otra fecha hay que
revalidar las fuentes y actualizar los casos; no relajar los asserts a “HTTP 200”.

Los WAV de `tests/e2e/fixtures/web-research` son entradas habladas por Microsoft Helena
para separar la voz de entrada de Piper, que sigue siendo la voz de salida de
producción. Pueden regenerarse con PowerShell 7 ejecutando
`./scripts/create_web_research_fixtures.ps1`; no cambian el micrófono del usuario.
El harness comprueba el texto completo enviado a TTS, cada segmento sintetizado,
reproducción completa por transporte, energía del audio recibido, historial y
respuesta posterior. La evaluación auditiva humana de pronunciación sigue separada.
