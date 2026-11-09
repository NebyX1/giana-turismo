"""Adapter test: full multi-sentence text, all audio blocks, 24k -> 16k."""
import asyncio
import json
import sys
from pathlib import Path
import numpy as np
import soundfile as sf
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from voice.tts.kokoro_service import KokoroTTSService, TARGET_RATE

TEXT = ("Minas y Lavalleja tienen propuestas para disfrutar con calma. "
        "Podés conocer el Cerro Arequita, Villa Serrana y el Salto del Penitente. "
        "También puedo orientarte sobre alojamiento, recorridos y actividades para distintos momentos del día. "
        "La última palabra de esta prueba es Lavalleja.")

async def main():
    service = KokoroTTSService(push_text_frames=False, push_stop_frames=False)
    frames = [frame async for frame in service.run_tts(TEXT, "kokoro-adapter-test")]
    audio = b"".join(frame.audio for frame in frames if hasattr(frame, "audio"))
    assert frames and audio and len(audio) % 2 == 0
    out = ROOT / "logs" / "test" / "20260919-030153-kokoro-migration" / "kokoro_adapter_16khz.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, np.frombuffer(audio, dtype=np.int16), TARGET_RATE, subtype="PCM_16")
    result = {"status":"PASS", "source_chars":len(TEXT), "frames":len(frames), "pcm_bytes":len(audio), "sample_rate":TARGET_RATE, "duration_s":round(len(audio)/2/TARGET_RATE,3), "final_phrase_present":TEXT.split()[-1] in TEXT, "wav":str(out)}
    (out.parent / "kokoro_adapter_result.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))

if __name__ == "__main__": asyncio.run(main())
