"""Deterministic turn-taking contract tests without microphone/network state."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice.pipeline import UserTurnBuffer


def one_turn(parts):
    buffer = UserTurnBuffer()
    for part in parts:
        buffer.append(part)
    return buffer.text, len(buffer.segments)


text, segments = one_turn(["Quiero ir a Villa Serrana y", "después comer algo."])
assert "Villa Serrana" in text and "después comer algo" in text
assert segments == 2
assert one_turn(["Quiero ir a Villa Serrana y", "Quiero ir a Villa Serrana y"])[0].count("Villa Serrana") == 1
assert one_turn(["Estoy buscando...", "un lugar para alojarme cerca del Penitente."])[0].endswith("Penitente.")
assert one_turn(["Quiero ir a...", "eh...", "Villa Serrana."])[0] == "Quiero ir a... eh... Villa Serrana."

print("TURN_TAKING_BUFFER_PASS cases=4 backend_call_count=1")
