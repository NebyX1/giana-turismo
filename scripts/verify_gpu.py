import json
import os
import time
from pathlib import Path

import torch
from sentence_transformers import CrossEncoder, SentenceTransformer


EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "ibm-granite/granite-embedding-97m-multilingual-r2")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")


def vram():
    return int(torch.cuda.memory_allocated()) if torch.cuda.is_available() else 0


def main():
    if not torch.cuda.is_available():
        raise SystemExit("CUDA no disponible; M0 no puede continuar sin fallback silencioso")
    device = "cuda"
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"CUDA disponible: {torch.cuda.is_available()}")
    before = vram()
    embedding = SentenceTransformer(EMBEDDING_MODEL, device=device)
    after_embedding = vram()
    reranker = CrossEncoder(RERANKER_MODEL, device=device)
    after_models = vram()
    print(f"modelo embedding: {EMBEDDING_MODEL}")
    print(f"device embedding: {embedding.device}")
    print(f"modelo reranker: {RERANKER_MODEL}")
    print(f"device reranker: {next(reranker.model.parameters()).device}")
    print(f"vector dim: {embedding.get_sentence_embedding_dimension()}")
    print(f"VRAM antes: {before}")
    print(f"VRAM después de embedding: {after_embedding}")
    print(f"VRAM después de ambos modelos: {after_models}")

    t0 = time.perf_counter()
    vector = embedding.encode(["¿Dónde puedo comer algo vegano en Minas?"], convert_to_numpy=True)
    embedding_ms = (time.perf_counter() - t0) * 1000
    torch.cuda.synchronize()
    peak_embedding = torch.cuda.max_memory_allocated()

    pairs = [
        ["comida vegana en Minas", "Hay opciones vegetarianas y veganas en establecimientos de Minas."],
        ["camping con electricidad", "El camping dispone de parcelas con conexión eléctrica."],
        ["teléfono de la Catedral", "Contacto telefónico de la Catedral de Minas."],
    ]
    torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    scores = reranker.predict(pairs)
    torch.cuda.synchronize()
    rerank_ms = (time.perf_counter() - t0) * 1000
    peak_query = max(peak_embedding, torch.cuda.max_memory_allocated())
    result = {
        "gpu": torch.cuda.get_device_name(0),
        "cuda_available": True,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_device": str(embedding.device),
        "reranker_model": RERANKER_MODEL,
        "reranker_device": str(next(reranker.model.parameters()).device),
        "vector_dim": int(vector.shape[-1]),
        "vram_before_bytes": before,
        "vram_after_models_bytes": after_models,
        "vram_peak_query_bytes": int(peak_query),
        "embedding_latency_ms": embedding_ms,
        "reranking_latency_ms": rerank_ms,
        "embedding_probe_norm": float((vector ** 2).sum() ** 0.5),
        "reranker_scores": [float(s) for s in scores],
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/gpu.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"scores mMARCO: {result['reranker_scores']}")
    print("reporte: reports/gpu.json")


if __name__ == "__main__":
    main()
