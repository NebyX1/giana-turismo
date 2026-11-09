#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v python3 >/dev/null || { echo "Falta python3" >&2; exit 1; }
command -v node >/dev/null || { echo "Falta Node.js 22" >&2; exit 1; }
command -v npm >/dev/null || { echo "Falta npm" >&2; exit 1; }
command -v docker >/dev/null || { echo "Falta Docker" >&2; exit 1; }

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/pip install -r voice/requirements.txt
(cd frontend && npm ci)
mkdir -p data storage run logs

if [ ! -f .env ]; then
  echo "Falta .env: copiá .env.example y completá OLLAMA_API_KEY." >&2
fi
if [ ! -s 'data/source/Guia_Turistica_Lavalleja_Consolidada_v4(2).md' ]; then
  echo "Falta el corpus turístico en data/source/; no se descarga automáticamente."
fi
if ! compgen -G 'voice/piper/*.onnx' >/dev/null; then
  echo "Falta la voz Piper es_AR-daniela-high (.onnx); no se descarga automáticamente."
fi

echo "Bootstrap terminado. Revisá los faltantes anteriores antes de iniciar."
