"""The two supported retrieval models and their immutable CPU artifacts."""
from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
MODEL_FILE = 'onnx/model_quint8_avx2.onnx'
VECTOR_SIZE = 384
MODELS = {
    'granite': {
        'id': 'ibm-granite/granite-embedding-97m-multilingual-r2',
        'revision': '835ad14087e140460703cf0fae09f97d469d65c2',
        'files': {
            MODEL_FILE: 'a6022dd8220ea6f6595562a1328ee216f4a94faa55362f2f4747c80f1e78772e',
            'tokenizer.json': '4f2842d568e2724370aec203652a42ac783c7937f8347a1a2cc7506d71f1582f',
        },
    },
    'mmarco': {
        'id': 'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1',
        'revision': '1427fd652930e4ba29e8149678df786c240d8825',
        'files': {
            MODEL_FILE: '6c2513767fb63d008a4377bef7a7a3555433d9436342bb53e35a3a72ffc52d4b',
            'tokenizer.json': '62c24cdc13d4c9952d63718d6c9fa4c287974249e16b7ade6d5a85e7bbb75626',
        },
    },
}
EMBED_MODEL = MODELS['granite']['id']
RERANK_MODEL = MODELS['mmarco']['id']
COLLECTION = 'giana_granite_cpu_v1'


def validate_model_policy():
    for variable, expected in (('EMBEDDING_MODEL', EMBED_MODEL), ('RERANKER_MODEL', RERANK_MODEL)):
        if os.getenv(variable, expected) != expected:
            raise ValueError(f'{variable} must be {expected}; alternative retrieval models are unsupported.')
    if os.getenv('QDRANT_COLLECTION', COLLECTION) != COLLECTION:
        raise ValueError(f'QDRANT_COLLECTION must be {COLLECTION}; rebuild the CPU index.')


validate_model_policy()
CPU_THREADS = max(1, min(int(os.getenv('CPU_THREADS', '4')), os.cpu_count() or 1))
MAX_TOKENS = max(32, min(int(os.getenv('MODEL_MAX_TOKENS', '512')), 512))
BATCH_SIZE = max(1, min(int(os.getenv('MODEL_BATCH_SIZE', '8')), 32))
MODEL_ROOT = ROOT / 'models'
QDRANT_PATH = ROOT / 'storage' / 'qdrant'


def index_signature():
    import hashlib
    chunks = ROOT / 'data/generated/chunks.jsonl'
    return {
        'embedding_model': EMBED_MODEL,
        'revision': MODELS['granite']['revision'],
        'artifact_sha256': MODELS['granite']['files'][MODEL_FILE],
        'tokenizer_sha256': MODELS['granite']['files']['tokenizer.json'],
        'pooling': 'cls', 'normalize': True, 'max_tokens': MAX_TOKENS,
        'vector_size': VECTOR_SIZE,
        'corpus_sha256': hashlib.sha256(chunks.read_bytes()).hexdigest(),
    }


if __name__ == '__main__':
    import json
    print(json.dumps({'port': int(os.getenv('PORT', '5000')), 'threads': CPU_THREADS,
                      'embedding_model': EMBED_MODEL, 'reranker_model': RERANK_MODEL}))
