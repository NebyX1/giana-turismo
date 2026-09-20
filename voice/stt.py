"""Local Whisper large-v3-turbo STT for the Pipecat 1.10 pipeline.

The model is deliberately process-scoped: SmallWebRTC reconnections create a
new FrameProcessor, but they must not load a second copy of the weights.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path

import ctranslate2
import numpy as np
from faster_whisper import WhisperModel
from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601

from voice.trace import trace_event

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = ROOT / "models" / "whisper-large-v3-turbo"
MODEL_ID = "openai/whisper-large-v3-turbo"
CONVERTED_MODEL_REPO = os.getenv("WHISPER_TURBO_CT2_REPO", "mobiuslabsgmbh/faster-whisper-large-v3-turbo")

_MODEL: WhisperModel | None = None
_MODEL_KEY: tuple[str, str, int, str] | None = None
_MODEL_LOCK = threading.Lock()
_INFERENCE_LOCK = asyncio.Lock()


def _setting(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def whisper_config() -> dict:
    return {
        "provider": _setting("STT_PROVIDER", "whisper_turbo"),
        "model": _setting("STT_MODEL", "large-v3-turbo"),
        "model_path": str(Path(_setting("STT_MODEL_PATH", str(DEFAULT_MODEL_PATH))).resolve()),
        "device": _setting("STT_DEVICE", "cuda").lower(),
        "device_index": int(_setting("STT_DEVICE_INDEX", "0")),
        "language": _setting("STT_LANGUAGE", "es"),
        "task": _setting("STT_TASK", "transcribe"),
        "compute_type": _setting("STT_COMPUTE_TYPE", "int8_float16"),
        "beam_size": int(_setting("STT_BEAM_SIZE", "1")),
        "num_workers": int(_setting("STT_NUM_WORKERS", "1")),
        "hotwords": _setting("STT_HOTWORDS", "Lavalleja Minas Cerro Arequita Villa Serrana Salto del Penitente Solís de Mataojo José Pedro Varela Mariscala Zapicán Pirarajá Parque Salus Giana"),
    }


def _validate_cuda(cfg: dict) -> None:
    if cfg["device"] != "cuda":
        raise RuntimeError(f"BLOCKED_CUDA: STT_DEVICE debe ser cuda, recibido {cfg['device']!r}")
    count = ctranslate2.get_cuda_device_count()
    if count <= cfg["device_index"]:
        raise RuntimeError(f"BLOCKED_CUDA: CTranslate2 detecta {count} GPU(s), no existe device_index={cfg['device_index']}")
    supported = ctranslate2.get_supported_compute_types("cuda", device_index=cfg["device_index"])
    if cfg["compute_type"] not in supported:
        raise RuntimeError(f"BLOCKED_CUDA: compute_type={cfg['compute_type']} no soportado; disponibles={sorted(supported)}")


def _load_shared_model(cfg: dict) -> WhisperModel:
    global _MODEL, _MODEL_KEY
    model_path = Path(cfg["model_path"])
    if not model_path.is_dir():
        raise RuntimeError(f"STT_MODEL_MISSING: no existe el modelo CT2 local en {model_path}")
    required = ("config.json", "model.bin", "tokenizer.json")
    missing = [name for name in required if not (model_path / name).is_file()]
    if missing:
        raise RuntimeError(f"STT_MODEL_INVALID: faltan {', '.join(missing)} en {model_path}")
    _validate_cuda(cfg)
    key = (str(model_path), cfg["compute_type"], cfg["device_index"], cfg["model"])
    with _MODEL_LOCK:
        if _MODEL is None or _MODEL_KEY != key:
            started = time.perf_counter()
            trace_event("stt", "whisper_load_started", detail=f"model={MODEL_ID} repo={CONVERTED_MODEL_REPO} path={model_path}")
            _MODEL = WhisperModel(str(model_path), device="cuda", device_index=cfg["device_index"], compute_type=cfg["compute_type"], cpu_threads=1, num_workers=cfg["num_workers"])
            _MODEL_KEY = key
            trace_event("stt", "whisper_loaded", elapsed_ms=round((time.perf_counter() - started) * 1000, 2), detail=f"model={MODEL_ID} repo={CONVERTED_MODEL_REPO} device=cuda compute_type={cfg['compute_type']}")
        return _MODEL


def prepare_whisper_model() -> WhisperModel:
    """Load and warm the one process-scoped model before accepting voice."""
    cfg = whisper_config()
    model = _load_shared_model(cfg)
    # Consume a real CT2 inference during startup. Silence is intentional: it
    # validates device, tokenizer and generator consumption without inventing text.
    audio = np.zeros(16000, dtype=np.float32)
    list(model.transcribe(audio, language=cfg["language"], task=cfg["task"], beam_size=cfg["beam_size"], temperature=0.0, condition_on_previous_text=False, vad_filter=False, word_timestamps=False)[0])
    trace_event("stt", "whisper_warmup_complete", detail=f"model={MODEL_ID} device=cuda compute_type={cfg['compute_type']}")
    return model


class GianaWhisperTurboSTTService(WhisperSTTService):
    """Pipecat adapter with full faster-whisper generator work off-loop."""

    Settings = WhisperSTTService.Settings

    @property
    def wants_wav_segments(self) -> bool:
        return False

    def __init__(self, *, settings=None, **kwargs):
        cfg = whisper_config()
        self._giana_cfg = cfg
        self._model = _load_shared_model(cfg)
        super().__init__(settings=settings, device="cuda", compute_type=cfg["compute_type"], **kwargs)

    def _load(self):
        # WhisperSTTService.__init__ calls this hook. The factory already loaded
        # the shared model and this hook intentionally does not load another one.
        self._model = _load_shared_model(self._giana_cfg)

    async def run_stt(self, audio: bytes):
        if not self._model:
            yield ErrorFrame("STT_MODEL_INVALID: Whisper model is not loaded")
            return
        cfg = self._giana_cfg
        started = time.perf_counter()
        try:
            async with _INFERENCE_LOCK:
                def transcribe_sync():
                    samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
                    # Silero can leave a short residual segment around a stop
                    # event. Do not ask Whisper to invent text from digital
                    # silence; this is an energy gate, not a duration rule.
                    if samples.size == 0 or float(np.max(np.abs(samples))) < 0.003:
                        return [], None
                    segments, info = self._model.transcribe(
                        samples,
                        language=cfg["language"], task=cfg["task"], beam_size=cfg["beam_size"],
                        temperature=0.0, condition_on_previous_text=False, vad_filter=False,
                        word_timestamps=False, hotwords=cfg["hotwords"], no_speech_threshold=0.6,
                        compression_ratio_threshold=2.4, log_prob_threshold=-1.0,
                    )
                    # Iteration is part of CT2 inference and must remain in this
                    # worker, not resume on the event loop.
                    return [(segment.text, segment.no_speech_prob) for segment in segments], info

                result, info = await asyncio.to_thread(transcribe_sync)
            text = " ".join(text.strip() for text, no_speech in result if text.strip() and no_speech < 0.4).strip()
            trace_event("stt", "whisper_transcription_complete", elapsed_ms=round((time.perf_counter() - started) * 1000, 2), detail=text, model=MODEL_ID, device="cuda", compute_type=cfg["compute_type"], audio_ms=round(len(audio) / 32, 2), segment_count=len(result))
            if text:
                yield TranscriptionFrame(text, self._user_id, time_now_iso8601(), Language.ES)
        except Exception as exc:
            trace_event("stt", "whisper_transcription_failed", status="error", elapsed_ms=round((time.perf_counter() - started) * 1000, 2), detail=f"{type(exc).__name__}: {exc}")
            yield ErrorFrame(f"STT_WHISPER_TURBO_ERROR: {type(exc).__name__}: {exc}")


def create_stt_service():
    cfg = whisper_config()
    if cfg["provider"] == "moonshine":
        from pipecat.services.moonshine.stt import Model, MoonshineSTTService
        return MoonshineSTTService(settings=MoonshineSTTService.Settings(model=Model.BASE_STREAMING, language=Language.ES))
    if cfg["provider"] != "whisper_turbo":
        raise RuntimeError(f"STT_PROVIDER_INVALID: {cfg['provider']!r}; use whisper_turbo o moonshine")
    return GianaWhisperTurboSTTService(settings=GianaWhisperTurboSTTService.Settings(model=cfg["model"], language=Language.ES, hotwords=cfg["hotwords"], no_speech_prob=0.4))
