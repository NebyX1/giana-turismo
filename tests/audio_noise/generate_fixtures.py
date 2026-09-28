"""Generate a small frozen synthetic Spanish voice corpus using local Piper."""
from pathlib import Path
import json
import urllib.request

CASES = {
    'hola': 'Hola.', 'si': 'Sí.', 'no': 'No.', 'minas': 'Minas.',
    'arequita': 'Arequita.', 'gracias': 'Gracias.',
    'donde_queda': '¿Dónde queda?',
    'visitar_minas': '¿Qué puedo visitar en Minas?',
    'cerro_arequita': '¿Dónde queda el Cerro Arequita?',
    'villa_serrana': 'Quiero conocer Villa Serrana.',
}
DEST = Path(__file__).resolve().parent / 'fixtures'


def main():
    DEST.mkdir(exist_ok=True)
    for name, text in CASES.items():
        request = urllib.request.Request('http://127.0.0.1:5001/synthesize', json.dumps({'text': text}).encode(), {'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        if not data.startswith(b'RIFF') or len(data) > 500_000:
            raise RuntimeError(f'Unexpected Piper WAV for {name}: {len(data)} bytes')
        (DEST / f'{name}.wav').write_bytes(data)
        print(name, len(data))


if __name__ == '__main__': main()
