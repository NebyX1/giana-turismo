"""A local index is reusable only for the same corpus and Granite artifact."""
import json
import time

from qdrant_client import models

from backend.app.model_policy import ROOT, COLLECTION, VECTOR_SIZE, BATCH_SIZE, index_signature

INDEX_MANIFEST = ROOT / 'storage' / 'index_manifest.json'
CHUNKS = ROOT / 'data/generated/chunks.jsonl'


def index_is_current(client):
    if not INDEX_MANIFEST.exists() or not client.collection_exists(COLLECTION):
        return False
    try:
        recorded = json.loads(INDEX_MANIFEST.read_text(encoding='utf-8'))
        current = index_signature()
        info = client.get_collection(COLLECTION)
        return (recorded['signature'] == current and info.points_count == recorded['points']
                and info.config.params.vectors.size == VECTOR_SIZE)
    except (ValueError, KeyError, OSError, AttributeError):
        return False


def ensure_index(client, manager, force=False):
    if not force and index_is_current(client):
        return {'collection': COLLECTION, 'reused': True}
    chunks = [json.loads(line) for line in CHUNKS.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not chunks:
        raise RuntimeError('La guía no tiene fragmentos. Ejecutá scripts/ingest.py.')
    INDEX_MANIFEST.unlink(missing_ok=True)
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE))
    started = time.perf_counter()
    fields = ('chunk_id', 'block_id', 'entity_id', 'title', 'heading_path', 'start_line', 'end_line', 'source_refs', 'text')
    for offset in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[offset:offset + BATCH_SIZE]
        vectors = manager.encode([row['text'] for row in batch])
        points = [models.PointStruct(id=offset + i, vector=vector.tolist(), payload={key: row.get(key) for key in fields})
                  for i, (row, vector) in enumerate(zip(batch, vectors))]
        client.upsert(COLLECTION, points=points, wait=True)
        if offset % (BATCH_SIZE * 10) == 0:
            print(f'Indexando Granite CPU: {offset + len(batch)}/{len(chunks)}', flush=True)
    result = {'collection': COLLECTION, 'signature': index_signature(), 'points': len(chunks),
              'seconds': round(time.perf_counter() - started, 2), 'reused': False}
    INDEX_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    temporary = INDEX_MANIFEST.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    temporary.replace(INDEX_MANIFEST)
    print(json.dumps(result), flush=True)
    return result
