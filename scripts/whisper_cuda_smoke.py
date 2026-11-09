"""Strict CUDA + CT2 + full generator smoke test for the local Turbo model."""
from __future__ import annotations
import json, os, time
from pathlib import Path
import ctranslate2, numpy as np
from faster_whisper import WhisperModel
ROOT=Path(__file__).resolve().parents[1]
def main() -> int:
    index=int(os.getenv("STT_DEVICE_INDEX","0")); compute=os.getenv("STT_COMPUTE_TYPE","int8_float16"); path=Path(os.getenv("STT_MODEL_PATH",str(ROOT/"models"/"whisper-large-v3-turbo"))).resolve()
    count=ctranslate2.get_cuda_device_count(); supported=sorted(ctranslate2.get_supported_compute_types("cuda",device_index=index)) if count>index else []
    result={"model_path":str(path),"cuda_device_count":count,"supported_compute_types":supported,"device":"cuda","compute_type":compute}
    if count<=index or compute not in supported: result["status"]="BLOCKED_CUDA"; print(json.dumps(result,indent=2)); return 2
    start=time.perf_counter(); model=WhisperModel(str(path),device="cuda",device_index=index,compute_type=compute,cpu_threads=1,num_workers=1)
    segments,info=model.transcribe(np.zeros(16000,dtype=np.float32),language="es",task="transcribe",beam_size=1,temperature=0.0,condition_on_previous_text=False,vad_filter=False,word_timestamps=False)
    consumed=list(segments); result.update(status="PASS",elapsed_ms=round((time.perf_counter()-start)*1000,2),segments_consumed=len(consumed),detected_language=getattr(info,"language",None),manifest=str(path/"GIANA_MODEL_MANIFEST.json"))
    (ROOT/"reports").mkdir(exist_ok=True); (ROOT/"reports"/"whisper_cuda_smoke.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
