"""Identify the backend code loaded at process start, without secrets/config."""
import hashlib
from pathlib import Path

def backend_build_id():
    digest = hashlib.sha256()
    for file in sorted([*Path(__file__).parent.glob('*.py'), *Path(__file__).parent.glob('*.json')]):
        digest.update(file.name.encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()[:20]
