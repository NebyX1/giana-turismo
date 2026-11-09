"""Create a 16 kHz Kokoro speech fixture for the real WebRTC browser gate."""
import asyncio, sys
from pathlib import Path
import numpy as np
import soundfile as sf
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from voice.tts.kokoro_service import KokoroTTSService, TARGET_RATE
TEXT="¿Qué puedo visitar en Minas?"
async def main():
    service=KokoroTTSService(push_text_frames=False, push_stop_frames=False)
    frames=[f async for f in service.run_tts(TEXT,"webrtc-input-fixture")]
    audio=b"".join(f.audio for f in frames if hasattr(f,"audio"))
    path=ROOT/"logs"/"test"/"20260919-030153-kokoro-migration"/"kokoro_input_query_16khz.wav"
    path.parent.mkdir(parents=True,exist_ok=True); sf.write(path,np.frombuffer(audio,dtype=np.int16),TARGET_RATE,subtype="PCM_16")
    print(path)
if __name__=="__main__": asyncio.run(main())
