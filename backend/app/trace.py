"""Optional, bounded diagnostic events for the text chat."""
import json
import os
from datetime import datetime, timezone
from threading import Lock

from backend.app.model_policy import ROOT

TRACE_PATH = ROOT / 'logs' / 'chat_trace.jsonl'
_lock = Lock()


def trace_event(component, event, *, detail='', **fields):
    if os.getenv('GIANA_DIAGNOSTICS', 'false').lower() != 'true':
        return
    payload = {'ts': datetime.now(timezone.utc).isoformat(), 'component': component,
               'event': event, 'detail': str(detail)[:500], **fields}
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        if TRACE_PATH.exists() and TRACE_PATH.stat().st_size > 2_000_000:
            TRACE_PATH.replace(TRACE_PATH.with_suffix('.previous.jsonl'))
        with TRACE_PATH.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + '\n')
