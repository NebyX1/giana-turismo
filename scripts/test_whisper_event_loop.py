"""Ensure a non-silent Turbo inference yields to the asyncio event loop."""
import asyncio
import time
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice.stt import create_stt_service

async def main():
    service = create_stt_service()
    ticks = []
    async def heartbeat():
        while True:
            ticks.append(time.perf_counter())
            await asyncio.sleep(0.05)
    task = asyncio.create_task(heartbeat())
    audio = np.random.default_rng(7).normal(0, 1800, 16000).clip(-32768, 32767).astype(np.int16).tobytes()
    frames = [frame async for frame in service.run_stt(audio)]
    task.cancel()
    print(f"WHISPER_EVENT_LOOP_PASS heartbeat_ticks={len(ticks)} frames={[type(f).__name__ for f in frames]}")
    assert len(ticks) >= 2, "event loop heartbeat did not run during STT"

if __name__ == "__main__":
    asyncio.run(main())
