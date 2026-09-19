#!/usr/bin/env bash
# Puesta en producción ordenada de Giana (Linux).
# Cada servicio se levanta y se verifica FUNCIONALMENTE antes de pasar al siguiente.
# Orden: Qdrant -> Piper -> Backend -> Voz -> Frontend. La interfaz sólo abre al final.
#
# Uso: scripts/start_production.sh [--dev]
#   --dev  Frontend con Vite dev server en lugar de build + preview.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
LOGS="$ROOT/logs"
mkdir -p "$LOGS"
DEV=0
[[ "${1:-}" == "--dev" ]] && DEV=1
BACKEND_TIMEOUT="${BACKEND_TIMEOUT:-300}"
VOICE_TIMEOUT="${VOICE_TIMEOUT:-120}"
STARTED_PIDS=()

step() { printf '\033[36m[GIANA] %s\033[0m\n' "$*"; }
ok()   { printf '\033[32m[GIANA]   OK  %s\033[0m\n' "$*"; }

stop_started() {
  for pid in "${STARTED_PIDS[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
}

fail() {
  printf '\033[31m[GIANA] ERROR: %s\033[0m\n' "$*" >&2
  printf '\033[31m[GIANA] Deteniendo los servicios que este script levantó.\033[0m\n' >&2
  stop_started
  exit 1
}

# wait_until <timeout_sec> <descripción> <comando...>
wait_until() {
  local timeout="$1" what="$2"; shift 2
  local deadline=$(( $(date +%s) + timeout ))
  while (( $(date +%s) < deadline )); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  fail "$what no respondió correctamente en ${timeout}s."
}

port_listening() { ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"; }

# start_bg <nombre> <comando...>   (hereda las variables exportadas antes de llamar)
start_bg() {
  local name="$1"; shift
  nohup "$@" >"$LOGS/$name.log" 2>"$LOGS/$name.err" &
  STARTED_PIDS+=("$!")
}

# ---------- Requisitos ----------
step 'Verificando requisitos'
[[ -x "$PY" ]] || fail 'Falta .venv/bin/python. Instalá el entorno primero.'
command -v docker >/dev/null || fail 'Docker no está instalado.'
command -v npm    >/dev/null || fail 'npm no está instalado.'
command -v curl   >/dev/null || fail 'curl no está instalado.'
command -v ss     >/dev/null || fail 'ss (iproute2) no está instalado.'
[[ -f "$ROOT/.env" ]] || fail 'Falta .env en la raíz (OLLAMA_API_KEY es obligatoria).'
grep -qE '^OLLAMA_API_KEY=.+' "$ROOT/.env" || fail 'OLLAMA_API_KEY no está definida en .env.'
PIPER_MODEL="$(ls "$ROOT"/models/piper/*.onnx 2>/dev/null | head -n1 || true)"
[[ -n "$PIPER_MODEL" ]] || fail 'No hay modelo Piper (*.onnx) en models/piper.'
[[ -f "$ROOT/data/generated/giana.sqlite3" ]] || fail 'Falta data/generated/giana.sqlite3. Ejecutá scripts/ingest.py.'
ok 'requisitos'

# ---------- 1. Qdrant ----------
step '1/5 Qdrant'
docker compose up -d qdrant >/dev/null
wait_until 90 'Qdrant' curl -fsS 'http://127.0.0.1:6333/readyz'
points="$(curl -fsS 'http://127.0.0.1:6333/collections/giana_granite_v2' 2>/dev/null | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["result"]["points_count"])' 2>/dev/null || echo 0)"
if [[ "${points:-0}" -lt 1 ]]; then
  step 'Colección ausente o vacía: indexando'
  HF_HUB_OFFLINE=1 "$PY" scripts/index_qdrant.py || fail 'La indexación en Qdrant falló.'
  points="$(curl -fsS 'http://127.0.0.1:6333/collections/giana_granite_v2' | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["result"]["points_count"])')"
fi
ok "Qdrant listo ($points vectores)"

# ---------- 2. Piper ----------
step '2/5 Piper TTS'
if ! port_listening 5001; then
  start_bg piper "$PY" -m piper.http_server --host 127.0.0.1 --port 5001 --model "$PIPER_MODEL"
fi
piper_probe() {
  local bytes
  bytes="$(curl -fsS -X POST 'http://127.0.0.1:5001/synthesize' -H 'Content-Type: application/json' -d '{"text":"Hola"}' --max-time 15 | wc -c)"
  (( bytes > 1000 ))
}
wait_until 90 'Piper (síntesis de prueba)' piper_probe
ok 'Piper sintetiza audio'

# ---------- 3. Backend ----------
step '3/5 Backend RAG (carga modelos CUDA; puede tardar)'
if ! port_listening 5000; then
  GIANA_DIAGNOSTICS=true PYTHONUTF8=1 HF_HUB_OFFLINE=1 start_bg backend "$PY" -m backend.app.main
fi
wait_until "$BACKEND_TIMEOUT" 'Backend /ready' curl -fsS 'http://127.0.0.1:5000/ready'
answer="$(curl -fsS -X POST 'http://127.0.0.1:5000/api/ask-text' -H 'Content-Type: application/json' \
  -d '{"question":"hola","session_id":"startup-probe","source":"probe"}' --max-time 30 \
  | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("answer") or "")')"
[[ -n "$answer" ]] || fail 'El backend respondió /ready pero no contesta preguntas.'
ok 'Backend responde consultas'

# ---------- 4. Voz ----------
step '4/5 Servidor de voz (Pipecat)'
if ! port_listening 7860; then
  GIANA_DIAGNOSTICS=true GIANA_TRACE_SOURCE=human PYTHONUTF8=1 \
  PIPER_URL='http://127.0.0.1:5001/synthesize' BACKEND_URL='http://127.0.0.1:5000' \
  start_bg voice "$PY" -m voice.bot -t webrtc
fi
voice_probe() {
  curl -fsS -X POST 'http://127.0.0.1:7860/start' -H 'Content-Type: application/json' \
    -d '{"transport":"webrtc","enableDefaultIceServers":true}' --max-time 10 | grep -q '"sessionId"'
}
wait_until "$VOICE_TIMEOUT" 'Voz /start' voice_probe
ok 'Voz acepta sesiones WebRTC'

# ---------- 5. Frontend (sólo cuando TODO lo anterior está listo) ----------
step '5/5 Interfaz web'
if ! port_listening 5173; then
  pushd frontend >/dev/null
  if (( DEV )); then
    start_bg frontend npm run dev -- --host 0.0.0.0 --port 5173
  else
    npm run build >/dev/null || { popd >/dev/null; fail 'La compilación del frontend falló.'; }
    start_bg frontend npm run preview -- --host 0.0.0.0 --port 5173 --strictPort
  fi
  popd >/dev/null
fi
wait_until 120 'Frontend' curl -fsS 'http://127.0.0.1:5173/'
ok 'Interfaz publicada'

echo
printf '\033[32m[GIANA] Todos los servicios están arriba y verificados.\033[0m\n'
echo '  Interfaz : http://localhost:5173'
echo '  Debug    : http://localhost:5173/?debug=1'
echo '  Backend  : http://localhost:5000/ready'
echo '  Voz      : http://localhost:7860'
echo '  Qdrant   : http://localhost:6333'
echo "  Logs     : $LOGS"
