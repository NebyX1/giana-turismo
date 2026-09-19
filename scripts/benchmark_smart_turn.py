"""Small local CPU benchmark for the bundled Smart Turn model."""
import statistics
import time

import numpy as np
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3


analyzer = LocalSmartTurnAnalyzerV3(cpu_count=1)
samples = np.zeros(16000 * 8, dtype=np.float32)
durations = []
for _ in range(20):
    started = time.perf_counter()
    analyzer._predict_endpoint(samples)
    durations.append((time.perf_counter() - started) * 1000)
print({"samples": len(durations), "p50_ms": round(statistics.median(durations), 2), "p95_ms": round(sorted(durations)[18], 2), "cpu_count": 1})
