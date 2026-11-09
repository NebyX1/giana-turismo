#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
exec .venv/bin/python -m flask --app backend.app.main run --host 0.0.0.0 --port 5000
