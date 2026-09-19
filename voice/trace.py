"""Small JSONL trace shared by the voice process and debug endpoint."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parents[1]
TRACE_PATH = ROOT / "logs" / "voice_trace.jsonl"
_lock = Lock()


def trace_event(component: str, event: str, *, session_id: str = "", turn_id: str = "", generation_id: str = "", status: str = "ok", detail: str = "", elapsed_ms: float | None = None, source: str | None = None, **fields):
    qa_session_id = fields.pop("qa_session_id", None) or os.getenv("QA_SESSION_ID", "")
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_ms": elapsed_ms,
        "session_id": session_id,
        "turn_id": turn_id,
        "generation_id": generation_id,
        "component": component,
        "event": event,
        "status": status,
        "detail": detail[:500],
        "source": source or os.getenv("GIANA_TRACE_SOURCE", "probe"),
        "qa_session_id": qa_session_id,
        **fields,
    }
    if not osafe_diagnostics():
        return
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with TRACE_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        qa_file = ROOT / "logs" / "test" / "CURRENT_QA_SESSION.txt"
        if qa_file.exists():
            try:
                qa_dir = Path(qa_file.read_text(encoding="utf-8").strip())
                qa_dir.mkdir(parents=True, exist_ok=True)
                with (qa_dir / "trace.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                if payload["status"] == "error" or payload["event"] in {"frontend_error_displayed", "TEXT_TTS_DIVERGENCE", "backend_request_failed", "backend_request_timeout"}:
                    with (qa_dir / "errors.jsonl").open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            except OSError:
                pass
        if payload["source"] == "human":
            session_file = ROOT / "logs" / "test" / "CURRENT_HUMAN_TURN_SESSION.txt"
            if session_file.exists():
                try:
                    session_dir = Path(session_file.read_text(encoding="utf-8").strip())
                    session_dir.mkdir(parents=True, exist_ok=True)
                    with (session_dir / "turn_taking.jsonl").open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    with (session_dir / "human_turns.jsonl").open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                except OSError:
                    pass
    compact = f"{component} {event} status={status} turn={payload['turn_id']} gen={payload['generation_id']}"
    if detail:
        compact += f" detail={detail[:160]}"
    print(f"[VOICE_TRACE] {compact}", flush=True)


def osafe_diagnostics() -> bool:
    import os
    return os.getenv("GIANA_DIAGNOSTICS", "false").lower() == "true"
