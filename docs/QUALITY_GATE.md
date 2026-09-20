# Calidad de Giana: contratos, contenido y conversación

## Actualización posterior al fallo del saludo

El PASS anterior no constituye aprobación de entrega: omitió el saludo compuesto
reportado por el usuario. Ver [decisiones y cobertura ampliada](ARCHITECTURE_DECISIONS.md).
La suite actual añade selección semántica, resiliencia, 49 escenarios HTTP
(98 ejecuciones), seis diálogos de 27 turnos, navegador escrito de 15 turnos,
voz de 14 turnos, cinco turnos con interrupción durante la reproducción real y
cuatro turnos de continuidad texto/voz/reconexión. Añade tres contratos UI de
respuesta tardía y la regresión de transcripción tardía al reanudar habla.
Los apartados de cobertura originales abajo
describen la base que se conserva, no el total ampliado.

Ejecutar el generador con **PowerShell 7 / pwsh**, no Windows PowerShell 5.

## Ejecutar

Con los servicios levantados:

```powershell
./scripts/create_deep_quality_fixtures.ps1
.venv/Scripts/python.exe scripts/quality_gate.py --repeat 2
```

La salida está en `logs/test/deep-quality-repair/gate-*/RESULTS.json`; cada etapa
tiene su log. Cualquier etapa fallida bloquea la aprobación. `--skip-voice` es
diagnóstico parcial y nunca produce PASS global.

El gate comprueba `/ready.build_id` contra el backend en disco. Guarda huellas del
código de producción y del catálogo de casos; si cambian durante la ejecución, no
aprueba. No basta con que los procesos estén levantados.

## Cobertura

1. Contratos: recuperación del bloque padre completo; fusión de canales; reranking
   antes del corte; categorías/localidades; hacer asado vs restaurante; evidencia
   presente pero insuficiente; web automática y prohibición explícita; recuperación
   dentro del turno; JSON inválido; fallos del modelo; generaciones superadas;
   aislamiento de sesiones; variaciones de STT y continuidad temporal.
2. Reloj: medianoche de Uruguay, cambio de año, mes explícito, bisiesto y barrido de
   400 fechas. Son comprobaciones del reloj, no 400 conversaciones reales.
3. HTTP real: `tests/quality_cases.json`, 38 preguntas en sesiones nuevas, orden
   mezclado reproducible y dos repeticiones. Se comprueban nombres, direcciones,
   teléfonos, negaciones, ruta, evidencia y uso de web; no sólo HTTP 200. Cubre
   gastronomía, preferencias alimentarias, camping, mascotas, estacionamiento,
   alojamiento, paseos, eventos, reloj y ámbito territorial.
4. Navegador escrito: secuencia de las capturas, correcciones, seguimiento de
   teléfono, búsqueda con transcripción imperfecta, cambio de tema, web por dato
   faltante, recarga y nueva conversación. Texto visible igual a respuesta HTTP.
5. Voz: diez turnos por Chrome/WebRTC/STT/backend/Piper sin simular respuestas.
   Entrada controlada, salida real, segmentos completos, energía RTP recibida,
   unicidad, pausa en frase inconclusa y reconexión/historial. Los tests de colas
   prueban interrupción/continuación y recuperación tras timeout/503 con backend
   simulado para aislar la máquina de estados.

Los audios Microsoft Helena sólo sustituyen el micrófono en el navegador de
pruebas. No cambian el dispositivo del usuario. La audición humana de pronunciación
y pruebas en micrófonos/ambientes adicionales siguen siendo otra dimensión.

## Oráculos y límites

- Nombres y contactos esperados proceden del catálogo existente; no se incorporan
  respuestas fijas en producción. Asado debe recuperar parrillas de la ciudad,
  no sustituirlas por camping o paseos rurales.
- La agenda positiva está fechada al 19/09/2026. Al vencer hay que revisar fuentes
  y actualizar los casos, no aceptar una negativa como sustituto del positivo.
  El paso del horario de un evento también cambia su pertinencia. Conservar todas
  las corridas, incluidas las fallidas.
- `evidence_sufficient` es una evaluación validada del modelo, no prueba formal de
  verdad. Se comprueba además contenido contra hechos de referencia. Los fallos de
  modelo/buscador deben ser explícitos y no contaminar la siguiente respuesta.
- El JSON se solicita en el prompt y se valida localmente. No se depende de `format`
  en Ollama Cloud, actualmente no disponible según su
  [documentación](https://docs.ollama.com/capabilities/structured-outputs).
- Ninguna suite finita abarca todas las conversaciones. Este gate bloquea las
  regresiones comprobadas y amplía cobertura por dimensiones; no certifica cero
  errores futuros ni sustituye pruebas de campo.

## Ante un nuevo fallo

Guardar pregunta, historial, audio/transcripción, evidencia, ruta y reloj. Agregar
primero un caso que falle; corregir la causa; ejecutar caso, variantes, secuencia y
gate completo. No quitar una aserción para aprobar: si el oráculo estaba mal,
documentar por qué y conservar el resultado anterior.
