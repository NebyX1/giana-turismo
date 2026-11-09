#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo '=== containers ==='
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
echo '=== processes ==='
ps -eo pid,ppid,stat,pcpu,pmem,rss,etime,args | rg 'backend/app/main.py|voice/bot.py|piper.http_server|giana-frontend|docker logs' || true
echo '=== ports ==='
ss -ltnp | rg ':(5000|5001|5173|6333|7860|7880)\b' || true
echo '=== health ==='
for url in http://127.0.0.1:6333/collections http://127.0.0.1:5000/health http://127.0.0.1:5000/ready http://127.0.0.1:5000/api/diagnostics http://127.0.0.1:5173/; do
  code="$(curl -sS -o /tmp/giana_status_body -w '%{http_code}' "$url" || true)"
  echo "$url HTTP $code"
  [ "$url" = http://127.0.0.1:5000/api/diagnostics ] && sed 's/"counters".*/"counters": "redacted-for-status"}/' /tmp/giana_status_body || true
done
echo '=== gpu ==='
nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader || true
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader || true
