"""LIVE model with fixed evidence: separately tests reasoning, not the search service.

Synthetic source names intentionally do not occur in the real agenda. All outputs
are retained for inspection. Run alongside the real-network browser acceptance.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.main import llm_answer
from backend.app.temporal import clock_snapshot, event_window, plain
from backend.app.web_research import research_instruction

snapshot = clock_snapshot(datetime(2026, 9, 19, 22, 10, tzinfo=timezone.utc))
cases = [
    ('split_year', '¿Qué eventos culturales hay esta semana en Minas?',
     'Agenda de Minas. Publicado 11 de septiembre de 2026.\n\nSábado 19 de setiembre\n\nEncuentro coral de prueba Lucero en Teatro Lavalleja a las 20:30 horas.',
     ['lucero', '20:30'], []),
    ('old_edition', '¿Qué eventos culturales hay esta semana en Minas?',
     'Archivo de Minas: Festival de prueba Horizonte, celebrado el 19 de septiembre de 2025.',
     ['2025'], ['hoy a', 'podes asistir', 'te recomiendo asistir']),
    ('publication_not_schedule', '¿Qué eventos culturales hay esta semana en Minas?',
     'Noticia publicada el 19 de septiembre de 2026. Teatro Lavalleja anuncia el espectáculo de prueba Bruma. Todavía no se definieron la fecha ni el horario.',
     ['bruma', 'fecha'], ['hoy a', 'se realizara hoy', '19 de septiembre a']),
    ('relative_publication_week', '¿Sigue abierta hoy la exposición de Minas?',
     'Publicado viernes 11 de septiembre de 2026. En Minas la muestra de prueba Niebla está abierta toda esta semana. No se indica una fecha de cierre ni una prórroga.',
     ['11 de septiembre', r'no (puedo|tengo|cuento)'], ['si, sigue abierta', 'podes visitarla hoy']),
    ('overlap_and_deadline', '¿Qué eventos hay el 19/09/2026 en Minas?',
     'Minas, agenda 2026. La feria de prueba Azahares se celebrará del 19 al 22 de septiembre en Plaza Libertad. Plazo de inscripción de puestos: 4 de septiembre. Entrada libre.',
     ['azahares', '19', '22'], []),
]
out = Path('logs/test/web-research-repair') / f'model-{int(time.time())}.json'
results = []
for name, query, text, required, forbidden in cases:
    evidence = [{'title': 'Fuente sintética de prueba', 'url': 'https://example.invalid/agenda',
                 'source_refs': [], 'content_origin': 'page', 'text': text}]
    research = {'queries': [query], 'sources_read': 1}
    answer, error = llm_answer(research_instruction(query, event_window(query, snapshot), research), evidence, time_context=snapshot)
    normalized = plain(answer or '')
    failures = ([error] if error else []) + [f'missing: {x}' for x in required if not re.search(x, normalized)] + [f'forbidden: {x}' for x in forbidden if x in normalized]
    results.append({'case': name, 'source': text, 'answer': answer, 'failures': failures, 'status': 'FAIL' if failures else 'PASS'})
    print(json.dumps(results[-1], ensure_ascii=True))
out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'ARTIFACTS {out}')
sys.exit(int(any(x['failures'] for x in results)))
