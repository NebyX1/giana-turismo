"""Exercise the real CPU models and report timings, without calling Ollama."""
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from backend.app.cpu_models import ModelManager
from backend.app.model_policy import ROOT


def measure(operation, repeat=5):
    times = []
    for _ in range(repeat):
        started = time.perf_counter()
        operation()
        times.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(times), 2)


def main():
    manager = ModelManager()
    manager.warmup()
    query = '¿Dónde queda el Cerro Arequita en Lavalleja?'
    passages = [
        'El Cerro Arequita está al norte de Minas, en Lavalleja, Uruguay.',
        'La Torre Eiffel es un monumento en París, Francia.',
        'Una receta de torta de chocolate con harina y azúcar.',
    ]
    vectors = manager.encode([query, *passages])
    assert vectors.shape == (4, 384) and np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    similarities = vectors[1:] @ vectors[0]
    assert int(similarities.argmax()) == 0, similarities
    scores = manager.rerank([[query, passage] for passage in passages])
    assert np.isfinite(scores).all() and int(scores.argmax()) == 0, scores
    # INT8 dynamic quantization varies slightly with batch padding; semantic alignment must remain high.
    single = np.asarray(manager.embed(query))
    assert float(single @ vectors[0]) > .98
    report = {
        'status': 'PASS', 'models': manager.status(),
        'embedding_median_ms': measure(lambda: manager.embed(query)),
        'rerank_3_median_ms': measure(lambda: manager.rerank([[query, text] for text in passages])),
        'rerank_24_median_ms': measure(lambda: manager.rerank([[query, text] for text in passages] * 8), 3),
        'similarities': similarities.tolist(), 'reranker_scores': scores.tolist(),
    }
    (ROOT / 'reports').mkdir(exist_ok=True)
    (ROOT / 'reports/cpu_verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
