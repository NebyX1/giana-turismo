"""Small, testable acoustic and Whisper evidence gates for incoming PCM16."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from pipecat.frames.frames import DataFrame


@dataclass
class STTRejectedFrame(DataFrame):
    reason: str = "no_speech"


@dataclass(frozen=True)
class AudioEvidence:
    audio_ms: float
    peak: float
    rms: float
    active_fraction: float
    active_ms: float


@dataclass(frozen=True)
class QualityDecision:
    accepted: bool
    reason: str


def measure_audio(samples: np.ndarray, sample_rate: int = 16000) -> AudioEvidence:
    if samples.size == 0:
        return AudioEvidence(0, 0, 0, 0, 0)
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    # 20 ms windows avoid classifying one sharp click as sustained speech.
    window = max(1, sample_rate // 50)
    frames = [float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64)))) for chunk in np.array_split(samples, math.ceil(samples.size / window))]
    active = sum(value >= 0.003 for value in frames)
    return AudioEvidence(1000 * samples.size / sample_rate, peak, rms, active / len(frames), active * 20)


def evaluate_audio(evidence: AudioEvidence) -> QualityDecision:
    if evidence.peak < 0.003 or evidence.rms < 0.0005:
        return QualityDecision(False, "digital_silence")
    if evidence.active_ms <= 120 and evidence.audio_ms >= 180:
        return QualityDecision(False, "impulsive_audio")
    return QualityDecision(True, "candidate")


def evaluate_transcription_quality(
    evidence: AudioEvidence, segments: list[dict], *,
    max_no_speech_prob: float = 0.6, min_avg_logprob: float = -1.0,
) -> QualityDecision:
    if not segments or not any(str(item.get("text", "")).strip() for item in segments):
        return QualityDecision(False, "vad_no_speech")
    credible = [item for item in segments if str(item.get("text", "")).strip() and float(item.get("no_speech_prob", 1)) <= max_no_speech_prob]
    if not credible:
        return QualityDecision(False, "high_no_speech_probability")
    if all(float(item.get("avg_logprob", -99)) < min_avg_logprob for item in credible) and evidence.active_ms < 350:
        return QualityDecision(False, "low_confidence")
    return QualityDecision(True, "accepted")
