"""Local 16-kHz RNNoise/Silero/Whisper evaluation; no human mic or backend."""
from __future__ import annotations

import asyncio
import json
import time

import numpy as np
import soxr
import soundfile as sf
from pipecat.audio.vad.vad_analyzer import VADState

from voice.denoise import create_input_filter
from voice.input_quality import evaluate_audio, measure_audio
from voice.pipeline import create_vad_analyzer
from voice.stt import GianaWhisperTurboSTTService, prepare_whisper_model
from tests.audio_noise.generate_fixtures import CASES, DEST


RATE = 16000


def noise_cases():
    rng = np.random.default_rng(2026)
    t = np.arange(RATE * 2, dtype=np.float32) / RATE
    burst = np.zeros_like(t); burst[5000:5200] = .6 * np.exp(-np.arange(200)/25) * rng.normal(0, 1, 200)
    clicks = np.zeros_like(t); clicks[[2000, 6500, 12000, 18000]] = .9
    keyboard = np.zeros_like(t)
    for at in [1600, 4600, 7000, 11000, 15000, 21000, 28000]: keyboard[at:at+30] = rng.normal(0, .2, 30)
    fan = .002*np.sin(2*np.pi*115*t) + rng.normal(0, .001, len(t))
    rub = np.zeros_like(t); rub[10000:11500] = .014 * rng.normal(0, 1, 1500)
    return {
        'silence': np.zeros_like(t), 'white_low': rng.normal(0, .0002, len(t)),
        'pink_low': np.cumsum(rng.normal(0, .00001, len(t))) / 30,
        'hum_50': .002*np.sin(2*np.pi*50*t), 'hum_60': .002*np.sin(2*np.pi*60*t),
        'click': burst, 'multiple_clicks': clicks, 'keyboard': keyboard,
        'fan': fan, 'rub': rub,
    }


def frozen_voice(name: str) -> np.ndarray:
    samples, rate = sf.read(DEST / f'{name}.wav', dtype='float32')
    if samples.ndim > 1: samples = samples.mean(axis=1)
    return soxr.resample(samples, rate, RATE) if rate != RATE else samples


async def run_case(name: str, samples: np.ndarray, stt=None):
    # A live microphone has silence both before and after the utterance; VAD
    # and RNNoise are stateful and must be exercised in that streaming context.
    samples = np.pad(np.clip(samples, -1, 1), (RATE, RATE))
    pcm = (samples * 32767).astype(np.int16).tobytes()
    denoise = create_input_filter()
    if denoise: await denoise.start(RATE)
    vad = create_vad_analyzer()
    vad.set_sample_rate(RATE)
    output = bytearray(); speaking = False
    start = time.perf_counter()
    try:
        for offset in range(0, len(pcm), 640):
            chunk = pcm[offset:offset+640]
            clean = await denoise.filter(chunk) if denoise else chunk
            output.extend(clean)
            if clean and vad._run_analyzer(clean) == VADState.SPEAKING: speaking = True
    finally:
        if denoise: await denoise.stop()
    denoise_vad_ms = round((time.perf_counter()-start)*1000, 1)
    evidence = measure_audio(np.frombuffer(bytes(output), np.int16).astype(np.float32)/32768)
    result = {'case': name, 'vad': speaking, 'audio_gate': evaluate_audio(evidence).reason, 'rms': round(evidence.rms, 5), 'denoise_vad_ms': denoise_vad_ms}
    if stt and speaking:
        started = time.perf_counter()
        frames = [frame async for frame in stt.run_stt(bytes(output))]
        result.update(stt_ms=round((time.perf_counter()-started)*1000, 1), frames=[type(frame).__name__ for frame in frames], text=' '.join(getattr(frame, 'text', '') for frame in frames))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


async def main():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    existing, sr = sf.read(root/'tests/e2e/fixtures/voice-resilience/input-1-1.wav', dtype='float32')
    if existing.ndim > 1: existing = existing.mean(axis=1)
    if sr != RATE: existing = soxr.resample(existing, sr, RATE)
    positives = {'existing_voice': existing}
    for name, text in CASES.items():
        positives[text] = frozen_voice(name)
    positives['soft_minas'] = positives['Minas.'] * .35
    rng = np.random.default_rng(3)
    positives['minas_fan'] = positives['Minas.'] + .002*np.sin(2*np.pi*110*np.arange(len(positives['Minas.']))/RATE)
    positives['minas_white'] = positives['Minas.'] + rng.normal(0, .003, len(positives['Minas.']))
    negatives = [await run_case(k, v) for k,v in noise_cases().items()]
    prepare_whisper_model()
    stt = GianaWhisperTurboSTTService(settings=GianaWhisperTurboSTTService.Settings(model='large-v3-turbo'))
    positives_out = [await run_case(k, v, stt) for k,v in positives.items()]
    summary = {'negatives_vad_rejected': sum(not x['vad'] for x in negatives), 'negatives': len(negatives), 'positives_stt_accepted': sum('TranscriptionFrame' in x.get('frames', []) for x in positives_out), 'positives': len(positives_out), 'failed_positive_cases': [x['case'] for x in positives_out if 'TranscriptionFrame' not in x.get('frames', [])], 'mean_filter_vad_ms': round(sum(x['denoise_vad_ms'] for x in positives_out)/len(positives_out), 1), 'mean_stt_ms': round(sum(x.get('stt_ms', 0) for x in positives_out)/len(positives_out), 1)}
    print('SUMMARY', json.dumps(summary), flush=True)
    if summary['negatives_vad_rejected'] != len(negatives) or summary['positives_stt_accepted'] != len(positives_out): raise SystemExit(1)


if __name__ == '__main__': asyncio.run(main())
