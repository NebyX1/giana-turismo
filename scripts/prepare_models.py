"""Download only the two pinned AVX2 INT8 models, with SHA256 verification."""
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.model_policy import MODELS, MODEL_ROOT


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    for name, model in MODELS.items():
        folder = MODEL_ROOT / name
        for relative, expected in model['files'].items():
            target = folder / relative
            if target.exists() and sha256(target) == expected:
                print(f'Verificado: {name}/{relative}', flush=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            url = f'https://huggingface.co/{model["id"]}/resolve/{model["revision"]}/{relative}'
            temporary = target.with_suffix(target.suffix + '.partial')
            for attempt in range(3):
                try:
                    print(f'Descargando: {name}/{relative}', flush=True)
                    with urlopen(url, timeout=60) as response, temporary.open('wb') as handle:
                        while chunk := response.read(1024 * 1024):
                            handle.write(chunk)
                    if sha256(temporary) != expected:
                        raise RuntimeError(f'SHA256 incorrecto: {name}/{relative}')
                    temporary.replace(target)
                    break
                except Exception:
                    temporary.unlink(missing_ok=True)
                    if attempt == 2:
                        raise
                    time.sleep(2)
        (folder / 'manifest.json').write_text(json.dumps(model, indent=2) + '\n', encoding='utf-8')
    print('Granite y mMARCO CPU preparados.', flush=True)


if __name__ == '__main__':
    main()
