"""INT8 inference on CPU, without a training framework or model exporters."""
import hashlib
import threading
import time

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from backend.app.model_policy import (
    BATCH_SIZE, CPU_THREADS, EMBED_MODEL, MAX_TOKENS, MODEL_FILE,
    MODEL_ROOT, MODELS, RERANK_MODEL, VECTOR_SIZE,
)


class CpuModel:
    def __init__(self, name):
        folder = MODEL_ROOT / name
        for relative, expected_hash in MODELS[name]['files'].items():
            if not (folder / relative).is_file():
                raise RuntimeError('Faltan los modelos CPU. Ejecutá scripts/prepare_models.py.')
            digest = hashlib.sha256()
            with (folder / relative).open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != expected_hash:
                raise RuntimeError('Modelo CPU incompatible. Ejecutá scripts/prepare_models.py.')
        options = ort.SessionOptions()
        options.intra_op_num_threads = CPU_THREADS
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.add_session_config_entry('session.intra_op.allow_spinning', '0')
        options.add_session_config_entry('session.inter_op.allow_spinning', '0')
        self.session = ort.InferenceSession(str(folder / MODEL_FILE), options, providers=['CPUExecutionProvider'])
        self.tokenizer = Tokenizer.from_file(str(folder / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS)
        padding = self.tokenizer.padding
        if padding:
            self.tokenizer.enable_padding(pad_id=padding['pad_id'], pad_token=padding['pad_token'])
        else:
            pad_token = '<pad>' if self.tokenizer.token_to_id('<pad>') is not None else '[PAD]'
            self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id(pad_token), pad_token=pad_token)
        self.inputs = {item.name: item.type for item in self.session.get_inputs()}

    def predict(self, texts):
        encoded = self.tokenizer.encode_batch(texts)
        values = {
            'input_ids': [item.ids for item in encoded],
            'attention_mask': [item.attention_mask for item in encoded],
            'token_type_ids': [item.type_ids for item in encoded],
        }
        feed = {key: np.asarray(values[key], dtype=np.int64 if 'int64' in kind else np.int32)
                for key, kind in self.inputs.items()}
        return self.session.run(None, feed)[0]


class ModelManager:
    def __init__(self):
        self.embedder = self.reranker = None
        self.loaded = self.warmed = False
        self.load_ms = self.warmup_ms = None
        self.lock = threading.RLock()

    def load_embedder(self):
        with self.lock:
            if self.embedder is None:
                self.embedder = CpuModel('granite')

    def load(self):
        with self.lock:
            if self.loaded:
                return
            started = time.perf_counter()
            self.load_embedder()
            self.reranker = CpuModel('mmarco')
            self.loaded = True
            self.load_ms = round((time.perf_counter() - started) * 1000, 2)

    def encode(self, texts):
        with self.lock:
            self.load_embedder()
            if not texts:
                return np.empty((0, VECTOR_SIZE), dtype=np.float32)
            batches = []
            for offset in range(0, len(texts), BATCH_SIZE):
                # Granite R2 uses CLS pooling, followed by L2 normalization.
                output = self.embedder.predict(texts[offset:offset + BATCH_SIZE])
                vectors = output[:, 0, :] if output.ndim == 3 else output
                vectors = np.asarray(vectors, dtype=np.float32)
                if vectors.shape[1] != VECTOR_SIZE or not np.isfinite(vectors).all():
                    raise RuntimeError('Invalid Granite embedding output')
                vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
                batches.append(vectors)
            return np.concatenate(batches)

    def embed(self, query):
        return self.encode([query])[0].tolist()

    def rerank(self, pairs):
        with self.lock:
            self.load()
            scores = []
            for offset in range(0, len(pairs), BATCH_SIZE):
                batch = [tuple(pair) for pair in pairs[offset:offset + BATCH_SIZE]]
                logits = self.reranker.predict(batch).reshape(-1)
                scores.extend((1 / (1 + np.exp(-np.clip(logits, -80, 80)))).tolist())
            return np.asarray(scores, dtype=np.float32)

    def warmup(self):
        with self.lock:
            self.load()
            if self.warmed:
                return
            started = time.perf_counter()
            self.embed('Turismo en Lavalleja')
            self.rerank([['Minas', 'Minas es la capital de Lavalleja.']])
            self.warmed = True
            self.warmup_ms = round((time.perf_counter() - started) * 1000, 2)

    def status(self):
        return {
            'loaded': self.loaded, 'warmed': self.warmed,
            'embedding_model': EMBED_MODEL, 'reranker_model': RERANK_MODEL,
            'device': 'cpu', 'dtype': 'uint8', 'backend': 'onnxruntime',
            'providers': ['CPUExecutionProvider'], 'threads': CPU_THREADS,
            'max_tokens': MAX_TOKENS, 'batch_size': BATCH_SIZE,
            'load_ms': self.load_ms, 'warmup_ms': self.warmup_ms,
        }
