"""Build or verify the embedded Granite CPU index. Stop the backend first."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qdrant_client import QdrantClient
from backend.app.model_policy import QDRANT_PATH
from backend.app.cpu_models import ModelManager
from backend.app.vector_index import ensure_index

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='Reconstruir aunque el índice esté vigente')
    args = parser.parse_args()
    client = QdrantClient(path=str(QDRANT_PATH))
    try:
        ensure_index(client, ModelManager(), force=args.force)
    finally:
        client.close()
