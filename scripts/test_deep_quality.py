"""Deterministic failure injection and corpus contracts; no real model/network."""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app import main as app
from backend.app.answer_quality import assessed_answer
from backend.app.retrieval_quality import catalog_candidates, parent_evidence, retrieval_terms
from backend.app.intent_router import classify_intent, CONVERSATION, CURRENT_INFO, WEB_FOLLOWUP, OUT_OF_SCOPE, TOURISM_RAG
from backend.app.temporal import clock_snapshot, event_window
from backend.app.web_research import research_web

NOW = clock_snapshot(datetime(2026, 9, 19, 22, tzinfo=timezone.utc))
LOCAL = {'chunk_id': 'x', 'title': 'Fuente local', 'text': 'Paisajes de Minas.', 'source_refs': [], 'start_line': 1, 'end_line': 2}
WEB = {'title': 'Teatro Lavalleja', 'url': 'https://example.uy/minas', 'content': 'Encuentro en Minas el 19 de septiembre de 2026 a las 20:30.'}
def reply(sufficient, text='Dato confirmado [1].'):
    return json.dumps({'answer': text, 'sufficient': sufficient, 'evidence_ids': [1] if sufficient else [], 'missing': '' if sufficient else 'falta el dato central','events':[{'name':'Encuentro','date':'2026-09-19','time':'20:30','source_id':1}] if sufficient else []}), None


class DeepQuality(unittest.TestCase):
    def setUp(self):
        config_patch=patch.dict(app.CONFIG,{'web_research_mode':'native'})
        config_patch.start();self.addCleanup(config_patch.stop)
        app.SESSION_HISTORY.clear()
        app.ACTIVE_GENERATIONS.clear()
        self.client = app.app.test_client()

    def ask(self, question, sid='deep-unit'):
        return self.client.post('/api/ask-text', json={'question': question, 'session_id': sid, 'generation_id': question}).get_json()

    def test_asado_paraphrases_catalog_not_camping(self):
        for noun in ['asado', 'asados', 'parrilla', 'parrillada', 'carne a la parrilla']:
            for prefix in ['Dónde comer ', 'Hola Giana, necesito que me digas si hay algún lugar donde comer ', 'No, no, te pedí que me recomendaras ']:
                with self.subTest(noun=noun, prefix=prefix):
                    hits = catalog_candidates(app.DB, prefix + noun + ' en la ciudad de Minas')
                    names = {x['title'] for x in hits}
                    self.assertIn('Parrillada Don Jorgito', names)
                    self.assertIn('Parrillada el Pololo', names)
                    self.assertTrue(all(x['zone'] == 'Minas' for x in hits))

    def test_cooking_own_is_not_restaurant(self):
        for verb in ['hacer', 'preparar', 'cocinar']:
            self.assertEqual(catalog_candidates(app.DB, f'Dónde {verb} un asado en Minas'), [])

    def test_parent_fragment_restores_missing_paragraph(self):
        import sqlite3
        with sqlite3.connect(app.DB) as db:
            rows = db.execute("SELECT chunk_id,block_id,text FROM chunks WHERE title='Minas para comer y recorrer a pie'").fetchall()
        self.assertGreater(len(rows), 1)
        found = parent_evidence(app.DB, [{'chunk_id': r[0], 'block_id': r[1], 'text': r[2], 'rrf': .01} for r in rows])
        self.assertEqual(len(found), 1)
        self.assertIn('Don Jorgito', found[0]['text'])
        self.assertIn('El Pololo', found[0]['text'])
        self.assertAlmostEqual(found[0]['rrf'], len(rows) * .01)

    def test_all_candidates_reranked_before_cut(self):
        rows = [{**LOCAL, 'chunk_id': str(i), 'title': str(i)} for i in range(20)]
        with patch.object(app, 'catalog_candidates', return_value=[]), patch.object(app, 'lexical', return_value=rows), patch.object(app, 'dense', return_value=[]), patch.object(app, 'parent_evidence', side_effect=lambda _, x:x), patch.object(app.MODELS, 'rerank', side_effect=lambda x:list(range(len(x)))) as rank:
            result, _ = app.retrieve_with_route('consulta de prueba')
        self.assertEqual(len(rank.call_args.args[0]), 20)
        self.assertEqual(result[0]['title'], '19')

    def test_routes_with_stt_damage_and_topic_switch(self):
        cases = [('Salud', CONVERSATION), ('¡Salud!', CONVERSATION),
                 ('Cá en la web, información sobre eventos culturales', WEB_FOLLOWUP),
                 ('Información sobre eventos culturales', CURRENT_INFO),
                 ('Qué puedo visitar en el Cerro Artigas', TOURISM_RAG),
                 ('Buscá en la web dónde comer en Madrid', OUT_OF_SCOPE),
                 ('Dónde comer asado en Minas', TOURISM_RAG)]
        for q, intent in cases:
            with self.subTest(q=q): self.assertEqual(classify_intent(q), intent)

    def test_followup_keeps_place_window_through_salud(self):
        app.remember_turn('deep-unit', 'Eventos esta semana en Minas', 'Respuesta')
        app.SESSION_HISTORY['deep-unit'][-1]['web_window'] = {'start':'2026-09-19', 'end':'2026-09-20'}
        app.remember_turn('deep-unit', 'Salud', 'Salud')
        for q in ['Buscá en la web información sobre eventos culturales', 'Cá en la web, información sobre eventos culturales', 'Eventos culturales, por favor']:
            with self.subTest(q=q):
                result = app.standalone_query('deep-unit', q)
                self.assertIn('minas', result.lower())
                self.assertEqual(event_window(result, NOW), {'start':'2026-09-19','end':'2026-09-20'})
        self.assertNotIn('2026-09-20', app.standalone_query('deep-unit', 'Eventos en octubre'))
        self.assertEqual(app.standalone_query('deep-unit', 'Qué podés contarme del Cerro Arequita'), 'Qué podés contarme del Cerro Arequita')

    def test_short_agenda_followups_never_fall_back_to_static_rag(self):
        for followup, window in [('¿Y mañana?', {'start':'2026-09-20','end':'2026-09-20'}), ('¿Y en Mariscala?', {'start':'2026-09-19','end':'2026-09-20'}), ('¿Y octubre?', {'start':'2026-10-01','end':'2026-10-31'})]:
            with self.subTest(followup=followup):
                app.SESSION_HISTORY.clear()
                app.remember_turn('deep-unit', 'Eventos culturales esta semana en Minas', 'Entre Sierras')
                app.SESSION_HISTORY['deep-unit'][-1]['web_window']={'start':'2026-09-19','end':'2026-09-20'}
                with patch.object(app, 'clock_snapshot', return_value=NOW), patch.object(app, 'retrieve', side_effect=AssertionError('agenda followup incorrectly used RAG')), patch.object(app,'web_search',return_value=({'results':[WEB]},None)), patch.object(app,'web_fetch',return_value=({'content':WEB['content']},None)), patch.object(app,'llm_answer',return_value=reply(False,'No confirmé eventos para ese período.')):
                    r=self.ask(followup)
                self.assertEqual(r['route'],'WEB_SEARCH')
                self.assertEqual(r['requested_window'],window)
                if 'Mariscala' in followup:
                    self.assertTrue(all('mariscala' in x.lower() for x in r['search_queries']))

    def test_clock_400_days_including_leap_year(self):
        for offset in range(400):
            dt = datetime(2027, 12, 1, 2, 59, tzinfo=timezone.utc) + timedelta(days=offset)
            with self.subTest(dt=dt):
                s = clock_snapshot(dt)
                self.assertEqual(s['date'], (dt-timedelta(hours=3)).date().isoformat())
                self.assertEqual((date.fromisoformat(s['week_end'])-date.fromisoformat(s['week_start'])).days, 6)
                self.assertEqual(date.fromisoformat(s['week_start']).weekday(), 0)
        self.assertEqual(event_window('eventos en febrero 2028', NOW), {'start':'2028-02-01','end':'2028-02-29'})
        self.assertEqual(event_window('eventos en octubre', NOW), {'start':'2026-10-01','end':'2026-10-31'})

    def test_contract_invalid_never_approves(self):
        for raw in ['no sé', '{}', '{"sufficient":"false"}', '{"answer":"ok","sufficient":true,"evidence_ids":[]}', '{"answer":"ok","sufficient":true,"evidence_ids":[999]}']:
            with self.subTest(raw=raw):
                value,error = assessed_answer(lambda *a,**k:(raw,None), 'q', [LOCAL])
                self.assertIsNone(value)
                self.assertEqual(error, 'LLM_EVIDENCE_CONTRACT_INVALID')

    def test_insufficient_local_evidence_automatically_searches(self):
        with patch.object(app, 'retrieve', return_value=([LOCAL],'HYBRID_RERANK')), patch.object(app, 'llm_answer', side_effect=[reply(False), reply(True,'Resultado web [2].')]), patch.object(app, 'web_search', return_value=({'results':[WEB]},None)) as search, patch.object(app, 'web_fetch', return_value=({'content':WEB['content']},None)):
            r = self.ask('Cuál es el precio del plato del día en Minas')
        self.assertTrue(r['rag_invoked'])
        self.assertTrue(r['web_invoked'])
        self.assertTrue(r['evidence_sufficient'])
        search.assert_called_once()

    def test_no_web_request_honored(self):
        with patch.object(app,'retrieve',return_value=([LOCAL],'HYBRID_RERANK')), patch.object(app,'llm_answer',return_value=reply(False)), patch.object(app,'web_search',side_effect=AssertionError('web forbidden')):
            r = self.ask('No busques en la web: dónde comer algo desconocido en Minas')
        self.assertFalse(r['web_invoked'])
        self.assertEqual(r['state'],'NO_EVIDENCE')

    def test_web_recovery_same_turn_not_user_retry(self):
        old = {**WEB, 'url':'https://example.uy/viejo', 'content':'Noticia antigua de Minas en 2025.'}
        def search(q):
            # Only the recovery's exact day query returns the missing current item.
            return {'results':[WEB if '19 septiembre 2026' in q and 'al' not in q.split('agenda')[1] else old]},None
        with patch.object(app,'clock_snapshot',return_value=NOW), patch.object(app,'web_search',side_effect=search), patch.object(app,'web_fetch',side_effect=lambda u:({'content':WEB['content'] if u==WEB['url'] else old['content']},None)), patch.object(app,'llm_answer',side_effect=[reply(False),reply(True,'Encuentro hoy a las 20:30 [2].')]):
            r=self.ask('Eventos esta semana en Minas')
        self.assertEqual(r['state'],'ANSWERABLE')
        self.assertGreater(len(r['search_queries']),3)
        self.assertEqual(r['requested_window'],{'start':'2026-09-19','end':'2026-09-20'})

    def test_model_failure_then_next_turn_recovers(self):
        with patch.object(app,'retrieve',return_value=([LOCAL],'HYBRID_RERANK')), patch.object(app,'llm_answer',return_value=(None,'LLM_UNAVAILABLE')):
            failed=self.ask('Donde comer en Minas')
        self.assertEqual(failed['state'],'SYSTEM_ERROR')
        self.assertEqual(self.ask('Qué hora es')['route'],'CLOCK')

    def test_superseded_answer_cannot_poison_history(self):
        def generate(*a,**k):
            app.ACTIVE_GENERATIONS['deep-unit']='new-generation'
            return reply(True)
        with patch.object(app,'retrieve',return_value=([LOCAL],'HYBRID_RERANK')), patch.object(app,'llm_answer',side_effect=generate):
            r=self.ask('Donde comer en Minas')
        self.assertEqual(r['state'],'INTERRUPTED')
        self.assertFalse(app.SESSION_HISTORY.get('deep-unit'))

    def test_session_isolation(self):
        app.remember_turn('a','Eventos esta semana en Minas','a')
        self.assertEqual(app.standalone_query('b','Buscalo en la web'),'Buscalo en la web')


if __name__=='__main__': unittest.main()
