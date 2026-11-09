#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p run logs
: > logs/backend.log; : > logs/voice.log; : > logs/piper.log; : > logs/frontend.log
[ -f .env ] || { echo 'Falta .env' >&2; exit 1; }
[ -s 'data/source/Guia_Turistica_Lavalleja_Consolidada_v4(2).md' ] || { echo 'Falta corpus fuente' >&2; exit 1; }
[ -x .venv/bin/python ] || { echo 'Falta .venv/bin/python' >&2; exit 1; }
.venv/bin/python - <<'PY'
import torch
if not torch.cuda.is_available(): raise SystemExit('CUDA no disponible')
print('cuda=ok')
PY

COMPOSE_PROJECT_NAME=giana-v2 docker compose up -d qdrant >/dev/null
for _ in $(seq 1 30); do curl -fsS http://127.0.0.1:6333/collections >/dev/null && break; sleep 1; done
curl -fsS http://127.0.0.1:6333/collections >/dev/null || { echo 'Qdrant no responde' >&2; exit 1; }
SOURCE_SHA="$(sha256sum 'data/source/Guia_Turistica_Lavalleja_Consolidada_v4(2).md' | awk '{print $1}')"
MANIFEST_SHA="$(.venv/bin/python -c 'import json; print(json.load(open("data/generated/manifest.json"))["sha256"])')"
[ "$SOURCE_SHA" = "$MANIFEST_SHA" ] || .venv/bin/python scripts/ingest.py > logs/ingest.log
COLLECTION_OK="$(.venv/bin/python - <<'PY'
import requests
try:
 d=requests.get('http://127.0.0.1:6333/collections/giana_granite_v2',timeout=5).json()['result']['config']['params']['vectors']
 ok=isinstance(d,dict) and d.get('size')==384 and d.get('distance')=='Cosine'
 print('true' if ok else 'false')
except Exception: print('false')
PY
)"
if [ "$COLLECTION_OK" != true ]; then
  curl -fsS -X DELETE http://127.0.0.1:6333/collections/giana_granite_v2 >/dev/null 2>&1 || true
  .venv/bin/python scripts/index_qdrant.py > logs/index_qdrant.log
fi

nohup bash -c "cd '$ROOT/voice' && echo \"pid=\$\$ timestamp=\$(date -Is) service=piper voice=es_AR-daniela-high\" && exec '$ROOT/.venv/bin/python' -m piper.http_server --host 0.0.0.0 --port 5001 -m ./piper/es_AR-daniela-high.onnx" >> logs/piper.log 2>&1 & echo $! > run/piper.pid
for _ in $(seq 1 30); do curl -fsS http://127.0.0.1:5001/ >/dev/null 2>&1 && break; sleep 1; done
GIANA_DIAGNOSTICS=true PYTHONPATH="$ROOT" nohup bash -c "echo \"pid=\$\$ timestamp=\$(date -Is) service=backend\"; exec '$ROOT/.venv/bin/python' '$ROOT/backend/app/main.py'" >> logs/backend.log 2>&1 & echo $! > run/backend.pid
for _ in $(seq 1 120); do curl -fsS http://127.0.0.1:5000/ready >/dev/null 2>&1 && break; sleep 1; done
curl -fsS http://127.0.0.1:5000/ready >/dev/null || { echo 'backend no llegó a ready' >&2; exit 1; }

PYTHONPATH="$ROOT" "$ROOT/.venv/bin/python" - <<'PY' >> logs/backend.log
import os,requests,time
from dotenv import load_dotenv
load_dotenv('.env'); key=os.getenv('OLLAMA_API_KEY',''); base=os.getenv('OLLAMA_BASE_URL','https://ollama.com').rstrip('/'); model=os.getenv('OLLAMA_MODEL','deepseek-v4.1-flash')
if not key: raise SystemExit('OLLAMA_API_KEY ausente')
t=time.perf_counter()
r=requests.post(base+'/api/generate',headers={'Authorization':f'Bearer {key}'},json={'model':model,'prompt':'Respondé exactamente OK','stream':False},timeout=(5,20))
r.raise_for_status(); print('ollama_status=%s total_ms=%.2f response=%s'%(r.status_code,(time.perf_counter()-t)*1000,str(r.json().get('response',''))[:20]))
PY

GIANA_DIAGNOSTICS=true PYTHONPATH="$ROOT" PIPER_URL=http://127.0.0.1:5001/synthesize nohup bash -c "echo \"pid=\$\$ timestamp=\$(date -Is) service=voice transport=smallwebrtc\"; exec '$ROOT/.venv/bin/python' '$ROOT/voice/bot.py' -t webrtc" >> logs/voice.log 2>&1 & echo $! > run/voice.pid
for _ in $(seq 1 60); do ss -ltn | rg -q ':7860 ' && break; sleep 1; done
ss -ltn | rg -q ':7860 ' || { echo 'SmallWebRTC no llegó a escuchar' >&2; exit 1; }
FRONTEND_ID="$(docker run -d --name giana-frontend --add-host=host.docker.internal:host-gateway -p 5173:5173 -v "$ROOT":/app -w /app/frontend node:22 npm run dev -- --host 0.0.0.0)"
echo "$FRONTEND_ID" > run/frontend.pid
docker logs -f "$FRONTEND_ID" >> logs/frontend.log 2>&1 & echo $! > run/frontend-log.pid
for _ in $(seq 1 30); do curl -fsS http://127.0.0.1:5173/ >/dev/null && break; sleep 1; done
curl -fsS http://127.0.0.1:5173/ >/dev/null || { echo 'frontend no llegó a responder' >&2; exit 1; }
echo 'GIANA clean start OK'
