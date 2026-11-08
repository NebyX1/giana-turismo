"""Prevent incompatible model selection and reuse of stale vector indexes."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qdrant_client import QdrantClient, models
from backend.app import model_policy, vector_index


class CpuPolicyTests(unittest.TestCase):
    def test_model_override_is_rejected(self):
        for variable in ('EMBEDDING_MODEL', 'RERANKER_MODEL', 'QDRANT_COLLECTION'):
            with self.subTest(variable=variable), patch.dict(os.environ, {variable: 'unsupported'}):
                with self.assertRaises(ValueError):
                    model_policy.validate_model_policy()

    def test_stale_incomplete_and_different_corpus_indexes_are_rejected(self):
        client = QdrantClient(':memory:')
        client.create_collection(model_policy.COLLECTION, vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
        client.upsert(model_policy.COLLECTION, [models.PointStruct(id=0, vector=[1.0] + [0.0] * 383)])
        try:
            with tempfile.TemporaryDirectory() as temporary:
                manifest = Path(temporary) / 'index_manifest.json'
                signature = model_policy.index_signature()
                with patch.object(vector_index, 'INDEX_MANIFEST', manifest):
                    self.assertFalse(vector_index.index_is_current(client))
                    record = {'signature': signature, 'points': 1}
                    manifest.write_text(json.dumps(record), encoding='utf-8')
                    self.assertTrue(vector_index.index_is_current(client))
                    for key, changed in (('points', 2), ('signature', {**signature, 'corpus_sha256': 'different'}),
                                         ('signature', {**signature, 'max_tokens': 32}),
                                         ('signature', {**signature, 'pooling': 'mean'})):
                        manifest.write_text(json.dumps({**record, key: changed}), encoding='utf-8')
                        self.assertFalse(vector_index.index_is_current(client))
        finally:
            client.close()


if __name__ == '__main__':
    unittest.main()
