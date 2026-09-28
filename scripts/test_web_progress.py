"""Verify that an automatic RAG-to-web fallback is visible while it runs."""

import threading
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app import main as backend


class WebProgressTest(unittest.TestCase):
    def setUp(self):
        backend.SESSION_HISTORY.clear()
        backend.ACTIVE_GENERATIONS.clear()

    def test_automatic_web_fallback_reports_live_progress(self):
        session_id = 'automatic-web-progress-test'
        generation_id = 'automatic-web-progress-generation'
        entered_web = threading.Event()
        finish_web = threading.Event()
        result = {}
        local_evidence = [{'title': 'Gastronomía en Minas', 'text': 'Minas Lavalleja', 'source_refs': []}]
        web_evidence = [{'title': 'Restaurante en Minas, Lavalleja', 'url': 'https://example.com/minas',
                         'text': 'Restaurante en Minas, Lavalleja', 'source_refs': ['https://example.com/minas']}]

        def research(*args, **kwargs):
            entered_web.set()
            if not finish_web.wait(5):
                raise TimeoutError('web fixture was not released')
            return {'queries': ['restaurante Minas Lavalleja'],
                    'attempts': [{'query': 'restaurante Minas Lavalleja', 'error': None, 'result_count': 1}],
                    'sources_read': 1, 'evidence': web_evidence, 'provider': 'fixture'}

        assessments = [
            ({'answer': 'Dato local no confirmado.', 'sufficient': False, 'evidence_ids': [], 'missing': 'restaurante'}, None),
            ({'answer': 'Encontré un restaurante en Minas.', 'sufficient': True, 'evidence_ids': [1], 'missing': ''}, None),
        ]

        def ask():
            with backend.app.test_client() as client:
                result['response'] = client.post('/api/ask-text', json={
                    'question': '¿Hay un restaurante de comida etíope en Minas?',
                    'session_id': session_id, 'generation_id': generation_id,
                })

        with patch.object(backend, 'ROUTER_MODE', 'rules'), \
             patch.object(backend, 'retrieve', return_value=(local_evidence, 'HYBRID_RERANK')), \
             patch.object(backend, 'assessed_answer', side_effect=assessments), \
             patch.object(backend, 'agentic_web_research', side_effect=research), \
             patch.dict(backend.CONFIG, {'web_research_mode': 'agent_tools'}):
            worker = threading.Thread(target=ask, daemon=True)
            worker.start()
            try:
                self.assertTrue(entered_web.wait(5), 'automatic fallback did not start')
                with backend.app.test_client() as client:
                    progress = client.get('/api/turn-progress', query_string={
                        'session_id': session_id, 'generation_id': generation_id,
                    })
                self.assertEqual(progress.json['state'], 'WEB_SEARCHING')
            finally:
                finish_web.set()
                worker.join(6)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result['response'].status_code, 200)
            self.assertTrue(result['response'].json['web_invoked'])
            self.assertTrue(result['response'].json['rag_invoked'])
            with backend.app.test_client() as client:
                progress = client.get('/api/turn-progress', query_string={
                    'session_id': session_id, 'generation_id': generation_id,
                })
                other = client.get('/api/turn-progress', query_string={
                    'session_id': 'other-session', 'generation_id': generation_id,
                })
            self.assertEqual(progress.json['state'], 'DONE')
            self.assertEqual(other.json['state'], 'IDLE')


if __name__ == '__main__':
    unittest.main()
