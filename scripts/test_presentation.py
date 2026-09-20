"""User-facing answer cleanup contracts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.presentation import strip_citation_markers


CASES = {
    "Encontré dos opciones [1][2].": "Encontré dos opciones.",
    "La fuente dice [1, 2] y otra confirma [3;4].": "La fuente dice y otra confirma.",
    "El evento es del 7 al 11 de octubre.": "El evento es del 7 al 11 de octubre.",
}

for raw, expected in CASES.items():
    actual = strip_citation_markers(raw)
    assert actual == expected, (raw, actual, expected)

print(f"PRESENTATION_PASS cases={len(CASES)}")
