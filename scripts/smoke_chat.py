"""Test a running chat, including real retrieval and Ollama Cloud generation."""
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from backend.app.model_policy import ROOT, EMBED_MODEL, RERANK_MODEL


def main():
    base = f'http://127.0.0.1:{os.getenv("PORT", "5000")}'
    readiness = requests.get(base + '/ready', timeout=10)
    readiness.raise_for_status()
    diagnostics = requests.get(base + '/api/diagnostics', timeout=10).json()['models']
    assert diagnostics['embedding_model'] == EMBED_MODEL
    assert diagnostics['reranker_model'] == RERANK_MODEL
    assert diagnostics['providers'] == ['CPUExecutionProvider']
    assert diagnostics['loaded'] and diagnostics['warmed']
    session_id = f'smoke-{uuid.uuid4().hex}'
    results = []
    for query, expected_route in (
        ('Hola Gianna', 'CONVERSATION'),
        ('¿Qué día y hora es?', 'CLOCK'),
        ('Contame qué es el Cerro Arequita en Lavalleja. Usá solamente la guía local, sin buscar en internet.', 'HYBRID_RERANK'),
    ):
        started = time.perf_counter()
        response = requests.post(base + '/api/ask-text', json={
            'question': query, 'session_id': session_id,
            'generation_id': uuid.uuid4().hex,
        }, timeout=90)
        response.raise_for_status()
        body = response.json()
        assert body['route'] == expected_route, body
        assert body.get('answer'), body
        if expected_route == 'HYBRID_RERANK':
            assert body['rag_invoked'] and body['llm_invoked'] and body['evidence'], body
            assert not body['web_invoked'] and 'arequita' in body['answer'].lower(), body
        results.append({'query': query, 'route': body['route'], 'state': body['state'],
                        'answer': body['answer'], 'sources': len(body.get('evidence', [])),
                        'seconds': round(time.perf_counter() - started, 2)})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    report = {'status': 'PASS', 'models': diagnostics, 'cases': results}
    (ROOT / 'reports').mkdir(exist_ok=True)
    (ROOT / 'reports/chat_smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('CHAT_SMOKE_PASS')


if __name__ == '__main__':
    main()
