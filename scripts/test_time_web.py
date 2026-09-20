"""Clock/research contracts; mocked network is NOT proof of real web quality."""
import sys
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.temporal import clock_snapshot, event_window
from backend.app.intent_router import classify_intent, CURRENT_TIME, CURRENT_INFO, TOURISM_RAG
from backend.app.web_research import search_plan, territorial
from backend.app import main as app

NOW = clock_snapshot(datetime(2026, 9, 19, 22, 4, 5, tzinfo=timezone.utc))
OLD = {'title': 'Semana de Lavalleja', 'url': 'https://example.uy/agenda', 'content': 'Festival en Minas del 8 al 19 de octubre de 2025.'}
NEW = {'title': 'Agenda Minas 2026', 'url': 'https://example.uy/teatro', 'content': 'Publicado el 11 de septiembre de 2026.\n\nTeatro Lavalleja\n\nSábado 19 de setiembre\n\nEncuentro coral Entre Sierras a las 20:30 horas.'}

def model_reply(answer, sufficient=True):
    return json.dumps({'answer': answer, 'sufficient': sufficient, 'evidence_ids': [1] if sufficient else [], 'missing': '', 'events':[{'name':'Encuentro','date':'2026-09-19','time':'20:30','source_id':1}] if sufficient else []}), None

class TimeWebTests(unittest.TestCase):
    def setUp(self):
        config_patch=patch.dict(app.CONFIG,{'web_research_mode':'native'})
        config_patch.start();self.addCleanup(config_patch.stop)
        clock_patch=patch.object(app,'clock_snapshot',return_value=NOW)
        clock_patch.start();self.addCleanup(clock_patch.stop)
        self.client = app.app.test_client()
        app.SESSION_HISTORY.clear()

    def ask(self, text):
        return self.client.post('/api/ask-text', json={'question': text, 'session_id': 'test-time-web'}).get_json()

    def test_timezone_and_rollovers(self):
        self.assertEqual(NOW['time'], '19:04:05')
        self.assertEqual(NOW['weekday'], 'sábado')
        midnight = clock_snapshot(datetime(2027, 1, 1, 2, 59, tzinfo=timezone.utc))
        self.assertEqual(midnight['date'], '2026-12-31')
        self.assertEqual(event_window('mañana', midnight), {'start': '2027-01-01', 'end': '2027-01-01'})
        self.assertEqual(event_window('esta semana', NOW), {'start': '2026-09-19', 'end': '2026-09-20'})
        self.assertEqual(event_window('la próxima semana', NOW), {'start': '2026-09-21', 'end': '2026-09-27'})

    def test_clock_no_llm_and_fresh_each_request(self):
        later = clock_snapshot(datetime(2026, 9, 20, 3, 1, tzinfo=timezone.utc))
        with patch.object(app, 'clock_snapshot', side_effect=[NOW, later]), patch.object(app, 'llm_answer', side_effect=AssertionError('clock used LLM')), patch.object(app, 'retrieve', side_effect=AssertionError('clock used RAG')):
            first = self.ask('Hola Giana, ¿podés decirme el día de hoy cuál es?')
            second = self.ask('¿Qué fecha es hoy?')
        self.assertEqual(first['route'], 'CLOCK')
        self.assertIn('sábado 19 de septiembre de 2026', first['answer'])
        self.assertIn('19:04:05', first['answer'])
        self.assertIn('domingo 20 de septiembre', second['answer'])

    def test_router(self):
        for query in ['¿Qué hora es?', '¿Qué día de la semana es hoy?', '¿Sabés qué fecha es?', '¿En qué día estamos?']:
            self.assertEqual(classify_intent(query), CURRENT_TIME, query)
        for query in ['¿Qué eventos culturales hay esta semana?', '¿Algún concierto este fin de semana?', '¿Está abierto ahora?', 'Eventos para mañana en Minas']:
            self.assertEqual(classify_intent(query), CURRENT_INFO, query)
        self.assertEqual(classify_intent('¿A qué hora abre el parque?'), TOURISM_RAG)

    def test_old_sources_are_reasoned_not_template(self):
        answer = 'La fuente anuncia una edición de 2025, no una actividad para esta semana.'
        with patch.object(app, 'clock_snapshot', return_value=NOW), patch.object(app, 'web_search', return_value=({'results': [OLD]}, None)) as search, patch.object(app, 'web_fetch', return_value=({'content': OLD['content']}, None)), patch.object(app, 'llm_answer', return_value=model_reply(answer, False)) as llm:
            first = self.ask('¿Qué eventos culturales hay esta semana?')
            second = self.ask('¿No podés buscar en la web algún evento cultural en Minas?')
        for response in [first, second]:
            self.assertTrue(response['web_invoked'])
            self.assertTrue(response['llm_invoked'])
            self.assertFalse(response['rag_invoked'])
            self.assertEqual(response['requested_window'], {'start': '2026-09-19', 'end': '2026-09-20'})
            self.assertEqual(response['answer'], answer)
        self.assertGreaterEqual(search.call_count, 6)
        self.assertEqual(llm.call_count, 2)
        self.assertEqual(llm.call_args.args[1][0]['text'], OLD['content'])
        self.assertEqual(len(llm.call_args.kwargs['context']), 1)

    def test_split_date_and_mixed_old_sources_reach_model(self):
        answer = 'Encuentro coral Entre Sierras: hoy a las 20:30 en el Teatro Lavalleja.'
        with patch.object(app, 'clock_snapshot', return_value=NOW), patch.object(app, 'web_search', return_value=({'results': [NEW, OLD]}, None)), patch.object(app, 'web_fetch', side_effect=lambda url: ({'content': NEW['content'] if url == NEW['url'] else OLD['content']}, None)), patch.object(app, 'llm_answer', return_value=model_reply(answer)) as llm:
            response = self.ask('¿Qué eventos hay esta semana?')
        self.assertEqual(response['answer'], answer)
        self.assertEqual(len(response['evidence']), 2)
        self.assertIn(NEW['content'], [x['text'] for x in llm.call_args.args[1]])
        self.assertEqual(llm.call_args.kwargs['time_context'], NOW)
        self.assertEqual(llm.call_args.kwargs['context'], [])
        self.assertEqual(response['sources_read'], 2)

    def test_fetch_failure_preserves_identified_excerpt(self):
        with patch.object(app, 'web_search', return_value=({'results': [NEW]}, None)), patch.object(app, 'web_fetch', return_value=(None, 'WEB_FETCH_ERROR')), patch.object(app, 'llm_answer', return_value=model_reply('El extracto anuncia un encuentro; no pude leer la página completa.')):
            response = self.ask('Buscá en la web eventos en Minas')
        self.assertEqual(response['sources_read'], 0)
        self.assertEqual(response['evidence'][0]['content_origin'], 'search_excerpt')
        self.assertEqual(response['evidence'][0]['text'], NEW['content'])

    def test_web_failure_is_not_fake_success(self):
        with patch.object(app, 'web_search', return_value=(None, 'WEB_AUTH_ERROR')), patch.object(app, 'llm_answer', side_effect=AssertionError('all searches failed')):
            response = self.ask('Buscá en la web eventos en Minas')
        self.assertEqual(response['state'], 'SYSTEM_ERROR')
        self.assertFalse(response['llm_invoked'])
        self.assertEqual(response['evidence'], [])

    def test_empty_successful_search_still_reasons(self):
        with patch.object(app, 'web_search', return_value=({'results': []}, None)), patch.object(app, 'llm_answer', return_value=model_reply('No encontré resultados para esa agenda.', False)) as llm:
            response = self.ask('Buscá en la web eventos en Minas')
        self.assertEqual(response['state'], 'NO_CONFIRMED_RESULT')
        self.assertTrue(response['llm_invoked'])
        llm.assert_called_once()

    def test_partial_failure_does_not_hide_success(self):
        def search(query):
            return (None, 'WEB_SEARCH_ERROR') if 'site:' in query else ({'results': [NEW]}, None)
        with patch.object(app, 'web_search', side_effect=search), patch.object(app, 'web_fetch', return_value=({'content': NEW['content']}, None)), patch.object(app, 'llm_answer', return_value=model_reply('Encuentro coral en el teatro [1].')):
            response = self.ask('Buscá en la web eventos en Minas')
        self.assertTrue(response['llm_invoked'])
        self.assertEqual(response['sources_read'], 1)
        self.assertEqual(sum(bool(x['error']) for x in response['search_attempts']), 1)

    def test_search_planning_and_territory(self):
        q = 'Te di una orden bien clara, buscá en la web eventos culturales en Minas'
        queries = search_plan(q, event_window(q, NOW), NOW)
        self.assertEqual(len(queries), 3)
        for query in queries:
            self.assertIn('2026', query)
            self.assertIn('septiembre octubre', query)
            self.assertNotIn('orden', query)
        self.assertFalse(territorial({'url': 'https://example.uy', 'content': 'Agenda de Montevideo, Uruguay'}))

if __name__ == '__main__':
    unittest.main()
