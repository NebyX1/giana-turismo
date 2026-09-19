import json
import os
import time
from pathlib import Path

from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/generated"
MODEL_ID = os.getenv("EMBEDDING_MODEL", "ibm-granite/granite-embedding-97m-multilingual-r2")
COLLECTION = os.getenv("QDRANT_COLLECTION", "giana_granite_v2")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").replace("qdrant:6333", "localhost:6333")


def main():
    chunks = [json.loads(x) for x in (OUT / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    model = SentenceTransformer(MODEL_ID, device="cuda")
    assert str(model.device).startswith("cuda"), model.device
    client = QdrantClient(url=QDRANT_URL)
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
    started = time.perf_counter()
    for offset in range(0, len(chunks), 32):
        batch = chunks[offset:offset + 32]
        vectors = model.encode([x["text"] for x in batch], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
        points = [models.PointStruct(id=i + offset, vector=v.tolist(), payload={k: x[k] for k in ["chunk_id", "block_id", "entity_id", "title", "heading_path", "start_line", "end_line", "source_refs", "text"]}) for i, (x, v) in enumerate(zip(batch, vectors))]
        client.upsert(COLLECTION, points=points, wait=True)
    info = client.get_collection(COLLECTION)
    result = {"collection": COLLECTION, "model": MODEL_ID, "device": str(model.device), "vectors": len(chunks), "vector_size": 384, "seconds": time.perf_counter() - started, "status": str(info.status)}
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/index.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
