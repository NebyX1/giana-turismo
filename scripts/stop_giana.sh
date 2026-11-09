#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_PROJECT_NAME=giana-v2 docker compose down --remove-orphans >/dev/null 2>&1 || true
for container in giana-qdrant giana-livekit giana-frontend pipecat-chatbot-qdrant-1 pipecat-chatbot-voice-agent-1 pipecat-chatbot-frontend-1 pipecat-chatbot-backend-api-1 pipecat-chatbot-turn-1 giana-turismo-3-qdrant-1; do
  docker inspect "$container" >/dev/null 2>&1 && docker rm -f "$container" >/dev/null 2>&1 || true
done

declare -a targets=()
for proc in /proc/[0-9]*; do
  pid="${proc##*/}"
  [ "$pid" = "$$" ] && continue
  cwd="$(readlink "$proc/cwd" 2>/dev/null || true)"
  case "$cwd" in
    "$ROOT"|"$ROOT"/*)
      cmd="$(tr '\0' ' ' < "$proc/cmdline" 2>/dev/null || true)"
      case "$cmd" in
        *backend/app/main.py*|*voice/bot.py*|*piper.http_server*|*vite*|*npm*|*ingest.py*|*index_qdrant.py*) targets+=("$pid") ;;
      esac
      ;;
  esac
done
for pid in "${targets[@]:-}"; do kill -TERM "$pid" 2>/dev/null || true; done
sleep 2
for pid in "${targets[@]:-}"; do kill -KILL "$pid" 2>/dev/null || true; done

if ! rg -q '^OLLAMA_BASE_URL=.*(localhost:11434|127\.0\.0\.1:11434)' "$ROOT/.env" 2>/dev/null; then
  for pid in $(pgrep -x ollama 2>/dev/null || true); do
    cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
    case "$cmd" in *ollama\ serve*) kill -TERM "$pid" 2>/dev/null || true ;; esac
  done
fi
