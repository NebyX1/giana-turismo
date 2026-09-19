"""Synthetic post-STT chain: backend JSON -> Pipecat text frames -> Piper audio."""
import asyncio
import io
import sys
import wave
from pathlib import Path

import httpx
from pipecat.frames.frames import LLMTextFrame

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice.pipeline import GianaRAGProcessor


async def main():
    processor = GianaRAGProcessor()
    frames = []

    async def capture(frame, *args, **kwargs):
        frames.append(frame)

    processor.push_frame = capture
    generation = processor.controller.start()
    await processor._answer("¿Qué puedo hacer en Minas un día de lluvia?", generation)
    await processor.http_client.aclose()
    text = "".join(frame.text for frame in frames if isinstance(frame, LLMTextFrame))
    if not text:
        raise RuntimeError("Pipecat no recibió un texto de asistente")
    response = httpx.post("http://127.0.0.1:5001/synthesize", json={"text": text}, timeout=30)
    response.raise_for_status()
    if response.content[:4] != b"RIFF":
        raise RuntimeError("Piper no devolvió WAV")
    with wave.open(io.BytesIO(response.content)) as audio:
        if audio.getnframes() <= 0:
            raise RuntimeError("WAV sin frames")
    Path("logs/post_stt_smoke.wav").write_bytes(response.content)
    print(f"POST_STT_SYNTHETIC_PASS frames={len(frames)} wav_bytes={len(response.content)}")


if __name__ == "__main__":
    asyncio.run(main())
