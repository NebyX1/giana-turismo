"""Fail-closed wrapper around Pipecat's local RNNoise input filter."""
from __future__ import annotations

import os
import time

from pipecat.audio.filters.rnnoise_filter import RNNoiseFilter

from voice.trace import trace_event


class RequiredRNNoiseFilter(RNNoiseFilter):
    async def start(self, sample_rate: int):
        await super().start(sample_rate)
        if not self._rnnoise_ready:
            raise RuntimeError("RNNOISE_UNAVAILABLE: AUDIO_DENOISE_ENABLED=true, but pyrnnoise/resampler could not initialize")
        try:
            # pyrnnoise creates its audiolab graph lazily on the first chunk.
            # Exercise it now so incompatible native packages fail at startup.
            await super().filter(bytes((sample_rate // 50) * 2))
        except Exception as exc:
            raise RuntimeError(f"RNNOISE_UNAVAILABLE: filter cannot process {sample_rate} Hz PCM: {exc}") from exc
        trace_event("audio", "denoise_started", sample_rate=sample_rate, detail="RNNoise CPU; internal 48 kHz")
        self._chunks = 0
        self._total_ms = 0.0

    async def filter(self, audio: bytes) -> bytes:
        started = time.perf_counter()
        result = await super().filter(audio)
        self._chunks += 1
        self._total_ms += (time.perf_counter() - started) * 1000
        if self._chunks % 250 == 0:
            trace_event("audio", "denoise_latency", elapsed_ms=round(self._total_ms / self._chunks, 3), chunks=self._chunks)
        return result


def create_input_filter():
    return RequiredRNNoiseFilter() if os.getenv("AUDIO_DENOISE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"} else None
