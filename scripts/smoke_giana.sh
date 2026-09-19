#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
curl -fsS http://127.0.0.1:6333/collections >/dev/null
curl -fsS http://127.0.0.1:5000/health >/dev/null
curl -fsS http://127.0.0.1:5000/ready >/dev/null
curl -fsS http://127.0.0.1:5173/ >/dev/null
echo 'health=ok'

PYTHONPATH="$ROOT" "$ROOT/.venv/bin/python" - <<'PY'
import json, requests, uuid
questions = [
    "¿Cuál es el teléfono de la Catedral de Minas?",
    "¿Dónde puedo comer algo vegano en Minas?",
    "¿Qué puedo hacer en Minas un día de lluvia?",
    "¿Dónde puedo tomar té sin gluten en Villa Serrana?",
    "¿Laguna de los Cuervos tiene camping habilitado?",
]
for question in questions:
    try:
        r=requests.post('http://127.0.0.1:5000/api/ask-text',json={'question':question,'session_id':'smoke','generation_id':str(uuid.uuid4())},timeout=35)
        data=r.json()
        debug=data.get('debug',{}).get('timings',{})
        print(json.dumps({'question':question,'http':r.status_code,'state':data.get('state'),'route':data.get('route'),'evidence':len(data.get('evidence',[])),'total_ms':debug.get('total_ms'),'error_code':data.get('error_code')},ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'question':question,'error':type(exc).__name__},ensure_ascii=False))
PY
echo 'diagnostics:'
curl -fsS http://127.0.0.1:5000/api/diagnostics
