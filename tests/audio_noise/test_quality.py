"""Deterministic anti-noise evidence tests (no model or microphone needed)."""
import unittest

import numpy as np

from voice.input_quality import evaluate_audio, evaluate_transcription_quality, measure_audio


class QualityGateTests(unittest.TestCase):
    def test_noise_cases(self):
        rate = 16000
        t = np.arange(rate, dtype=np.float32) / rate
        rng = np.random.default_rng(42)
        click = np.zeros(rate, dtype=np.float32); click[4000:4012] = 0.9
        clicks = np.zeros(rate, dtype=np.float32); clicks[[1000, 4000, 8000, 12000]] = 0.8
        keyboard = np.zeros(rate, dtype=np.float32)
        for point in (2000, 5000, 8000, 11000, 14000): keyboard[point:point+40] = rng.normal(0, 0.18, 40)
        cases = {
            'silence': np.zeros(rate, dtype=np.float32),
            'low_white': rng.normal(0, 0.0002, rate),
            'low_pink': np.cumsum(rng.normal(0, 0.00003, rate)).astype(np.float32) / 50,
            'hum_50': 0.0002 * np.sin(2*np.pi*50*t),
            'hum_60': 0.0002 * np.sin(2*np.pi*60*t),
            'click': click,
            'knock': np.pad(np.sin(2*np.pi*140*t[:80]) * np.linspace(0.65, 0, 80), (2000, rate-2080)),
            'clicks': clicks,
            'keyboard': keyboard,
            'fan': 0.00025*np.sin(2*np.pi*110*t) + rng.normal(0, 0.00015, rate),
        }
        for name, audio in cases.items():
            with self.subTest(name=name):
                self.assertFalse(evaluate_audio(measure_audio(audio)).accepted)

    def test_soft_sustained_audio_not_rejected_by_energy_alone(self):
        # This only tests the acoustic gate; not a synthetic claim of STT accuracy.
        t = np.arange(16000, dtype=np.float32) / 16000
        sample = 0.012 * np.sin(2*np.pi*(130*t + 50*t*t))
        self.assertTrue(evaluate_audio(measure_audio(sample)).accepted)

    def test_whisper_evidence(self):
        audio = measure_audio(np.full(16000, .01, dtype=np.float32))
        self.assertFalse(evaluate_transcription_quality(audio, []).accepted)
        self.assertEqual(evaluate_transcription_quality(audio, [{'text':'Hola', 'no_speech_prob':.9, 'avg_logprob':-.2}]).reason, 'high_no_speech_probability')
        self.assertTrue(evaluate_transcription_quality(audio, [{'text':'Sí', 'no_speech_prob':.1, 'avg_logprob':-.3}]).accepted)
        # A one-word answer is not rejected for its length.
        self.assertTrue(evaluate_transcription_quality(audio, [{'text':'No', 'no_speech_prob':.1, 'avg_logprob':-.3}]).accepted)

    def test_weak_audio_and_bad_logprob_is_rejected(self):
        samples = np.zeros(16000, dtype=np.float32)
        samples[3000:4000] = .02
        evidence = measure_audio(samples)
        result = evaluate_transcription_quality(evidence, [{'text':'algo', 'no_speech_prob':.1, 'avg_logprob':-1.5}])
        self.assertEqual(result.reason, 'low_confidence')


if __name__ == '__main__': unittest.main()
