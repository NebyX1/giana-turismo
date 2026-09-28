"""Short-lived, per-request progress for the chat UI."""

import threading
import time

_lock = threading.Lock()
_turns = {}
_ttl_seconds = 180


def _prune(now):
    for key, (_, updated) in list(_turns.items()):
        if now - updated > _ttl_seconds:
            del _turns[key]


def set_progress(session_id: str, generation_id: str, state: str) -> None:
    now = time.monotonic()
    with _lock:
        _prune(now)
        _turns[(session_id, generation_id)] = (state, now)


def get_progress(session_id: str, generation_id: str) -> str:
    now = time.monotonic()
    with _lock:
        _prune(now)
        return _turns.get((session_id, generation_id), ('IDLE', now))[0]
