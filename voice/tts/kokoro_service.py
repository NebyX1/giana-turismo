"""Kokoro PyTorch/CUDA adapter for Pipecat 1.10."""
from __future__ import annotations

import asyncio
import os
import re
import threading
import time
from pathlib import Path

import numpy as np
import torch
from kokoro import KPipeline
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language
from scipy.signal import resample_poly

from voice.trace import trace_event

ROOT = Path(__file__).resolve().parents[2]
MODEL_REPO = "hexgrad/Kokoro-82M"
SOURCE_RATE = 24000
TARGET_RATE = 16000
_RUNTIME: KPipeline | None = None
_RUNTIME_LOCK = threading.Lock()
_INFERENCE_LOCK = asyncio.Lock()


def kokoro_config() -> dict:
    return {
        "provider": os.getenv("TTS_PROVIDER", "piper").strip().lower(),
        "model": os.getenv("KOKORO_MODEL", MODEL_REPO).strip(),
        "voice": os.getenv("KOKORO_VOICE", "ef_dora").strip(),
        "lang_code": os.getenv("KOKORO_LANG_CODE", "e").strip(),
        "device": os.getenv("KOKORO_DEVICE", "cuda").strip().lower(),
        "speed": float(os.getenv("KOKORO_SPEED", "1.0")),
        "dtype": os.getenv("KOKORO_DTYPE", "float32").strip().lower(),
    }


def _load_runtime(cfg: dict) -> KPipeline:
    global _RUNTIME
    if cfg["device"] != "cuda":
        raise RuntimeError(f"BLOCKED_KOKORO_CUDA: KOKORO_DEVICE debe ser cuda, recibido {cfg['device']!r}")
    if not torch.cuda.is_available():
        raise RuntimeError("BLOCKED_KOKORO_CUDA: torch.cuda.is_available() es falso")
    if cfg["dtype"] != "float32":
        raise RuntimeError(f"KOKORO_DTYPE no soportado para el perfil inicial: {cfg['dtype']!r}; usar float32")
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            started = time.perf_counter()
            trace_event("tts", "kokoro_load_started", detail=f"model={cfg['model']} voice={cfg['voice']} lang_code={cfg['lang_code']} device=cuda dtype=float32")
            _RUNTIME = KPipeline(lang_code=cfg["lang_code"], repo_id=cfg["model"], device="cuda")
            _RUNTIME.model.eval()
            # Load the requested voice once, before the first browser response.
            _RUNTIME.load_voice(cfg["voice"])
            trace_event("tts", "kokoro_loaded", elapsed_ms=round((time.perf_counter() - started) * 1000, 2), detail=f"model={cfg['model']} voice={cfg['voice']} device=cuda dtype=float32")
        return _RUNTIME


def prepare_kokoro() -> KPipeline:
    """Load, voice-load and warm the resident runtime in the voice process."""
    cfg = kokoro_config()
    pipeline = _load_runtime(cfg)
    started = time.perf_counter()
    with torch.inference_mode():
        results = list(pipeline("Hola, soy Gianna.", voice=cfg["voice"], speed=cfg["speed"]))
    if not results or not any(result.audio is not None and result.audio.numel() for result in results):
        raise RuntimeError("KOKORO_WARMUP_FAILED: no se generó audio")
    trace_event("tts", "kokoro_warmup_complete", elapsed_ms=round((time.perf_counter() - started) * 1000, 2), detail=f"samples={sum(int(r.audio.numel()) for r in results if r.audio is not None)}")
    return pipeline


def _phoneme_len(pipeline: KPipeline, text: str) -> int:
    phonemes, _ = pipeline.g2p(text)
    return len(phonemes or "")


def split_kokoro_text(pipeline: KPipeline, text: str, budget: int = 480) -> list[str]:
    """Split at sentence/word boundaries before Kokoro's 510-phoneme limit."""
    text = text.strip()
    if not text:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[.!?…])\s+", text) if part.strip()]
    chunks: list[str] = []
    for sentence in sentences:
        if _phoneme_len(pipeline, sentence) <= budget:
            chunks.append(sentence)
            continue
        words = sentence.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if _phoneme_len(pipeline, candidate) <= budget:
                current = candidate
            else:
                if not current:
                    raise ValueError(f"KOKORO_TEXT_UNSPLITTABLE: palabra excede el presupuesto fonético: {word!r}")
                chunks.append(current)
                current = word
        if current:
            chunks.append(current)
    # Coverage guard: whitespace may differ, but no source word may vanish.
    if " ".join(chunks).split() != text.split():
        raise ValueError("KOKORO_TEXT_COVERAGE_FAILED: segmentación no conserva todas las palabras")
    return chunks


def _float_to_pcm16(audio: np.ndarray) -> bytes:
    audio = np.asarray(audio, dtype=np.float32)
    if not np.isfinite(audio).all():
        raise ValueError("KOKORO_AUDIO_NONFINITE")
    audio = np.clip(audio, -1.0, 1.0)
    return (audio * 32767.0).astype(np.int16).tobytes()


def _synthesize_sync(pipeline: KPipeline, cfg: dict, text: str) -> tuple[list[bytes], dict]:
    chunks = split_kokoro_text(pipeline, text)
    pcm_chunks: list[bytes] = []
    source_samples = 0
    started = time.perf_counter()
    with torch.inference_mode():
        for index, chunk in enumerate(chunks):
            # list() is intentional: every generator result is consumed.
            results = list(pipeline(chunk, voice=cfg["voice"], speed=cfg["speed"], split_pattern=None))
            for result in results:
                if result.audio is None:
                    continue
                audio = result.audio.detach().float().cpu().numpy()
                source_samples += int(audio.shape[0])
                resampled = resample_poly(audio, TARGET_RATE, SOURCE_RATE).astype(np.float32)
                pcm_chunks.append(_float_to_pcm16(resampled))
            trace_event("tts", "kokoro_segment_synthesized", detail=f"segment={index + 1}/{len(chunks)} chars={len(chunk)}", segment_index=index, segment_total=len(chunks), source_rate=SOURCE_RATE, target_rate=TARGET_RATE)
    return pcm_chunks, {"segment_total": len(chunks), "source_samples": source_samples, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}


class KokoroTTSService(TTSService):
    """Minimal Pipecat TTSService; Kokoro model and voice are process-scoped."""

    def __init__(self, **kwargs):
        cfg = kokoro_config()
        self._kokoro_cfg = cfg
        self._pipeline = _load_runtime(cfg)
        super().__init__(sample_rate=TARGET_RATE, **kwargs)

    async def run_tts(self, text: str, context_id: str):
        started = time.perf_counter()
        cfg = self._kokoro_cfg
        trace_event("tts", "kokoro_input_received", detail=text, provider="kokoro", voice=cfg["voice"], context_id=context_id, text_length=len(text))
        try:
            async with _INFERENCE_LOCK:
                pcm_chunks, meta = await asyncio.to_thread(_synthesize_sync, self._pipeline, cfg, text)
            trace_event("tts", "kokoro_response_complete", elapsed_ms=round((time.perf_counter() - started) * 1000, 2), detail=f"context_id={context_id} chars={len(text)} segments={meta['segment_total']} source_samples={meta['source_samples']}", provider="kokoro", voice=cfg["voice"], source_rate=SOURCE_RATE, target_rate=TARGET_RATE, context_id=context_id, text_length=len(text))
            for index, pcm in enumerate(pcm_chunks):
                yield TTSAudioRawFrame(pcm, TARGET_RATE, 1, context_id=context_id)
        except asyncio.CancelledError:
            trace_event("tts", "kokoro_cancelled", status="error", detail=f"context_id={context_id}", context_id=context_id)
            raise
        except Exception as exc:
            trace_event("tts", "kokoro_error", status="error", elapsed_ms=round((time.perf_counter() - started) * 1000, 2), detail=f"context_id={context_id} {type(exc).__name__}: {exc}", context_id=context_id)
            yield ErrorFrame(f"TTS_KOKORO_ERROR: {type(exc).__name__}: {exc}")


def create_tts_service(*, piper_url: str, aiohttp_session):
    cfg = kokoro_config()
    if cfg["provider"] == "kokoro":
        return KokoroTTSService(push_text_frames=False, push_stop_frames=False)
    if cfg["provider"] != "piper":
        raise RuntimeError(f"TTS_PROVIDER_INVALID: {cfg['provider']!r}; usar kokoro o piper")
    from voice.pipeline import TracedPiperTTSService
    return TracedPiperTTSService(base_url=piper_url, aiohttp_session=aiohttp_session, sample_rate=TARGET_RATE, settings=TracedPiperTTSService.Settings(voice=os.getenv("PIPER_VOICE", "es_AR-daniela-high"), language=Language.ES))
