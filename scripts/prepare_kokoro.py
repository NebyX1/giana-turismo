"""Prepare Kokoro-82M/ef_dora, generate complete local samples, and verify CUDA."""
from __future__ import annotations
import hashlib, json, os, time
import sys
from pathlib import Path
import soundfile as sf
import torch
from huggingface_hub import HfApi, snapshot_download
from kokoro import KPipeline
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice.tts.kokoro_service import split_kokoro_text

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs" / "test" / os.getenv("KOKORO_TEST_DIR", "latest-kokoro-migration")
REPO = "hexgrad/Kokoro-82M"
VOICE = "ef_dora"

SAMPLES = {
    "welcome": "Hola, soy Gianna, la asistente turística de Lavalleja. ¿En qué te puedo ayudar hoy?",
    "tourism": "Minas ofrece paisajes, cultura y propuestas para disfrutar con calma. Desde allí podés conocer el Cerro Arequita, Villa Serrana y el Salto del Penitente. También puedo orientarte sobre alojamiento y actividades cercanas.",
    "toponyms": "Minas, Lavalleja, Cerro Arequita, Villa Serrana, Salto del Penitente, Solís de Mataojo, José Pedro Varela, Mariscala, Zapicán, Pirarajá y Parque Salus.",
}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not torch.cuda.is_available():
        raise SystemExit("BLOCKED_KOKORO_CUDA: torch.cuda.is_available() es falso")
    revision = HfApi().model_info(REPO, revision="main").sha
    snapshot = snapshot_download(REPO, revision="main", allow_patterns=["config.json", "kokoro-v1_0.pth", "voices/ef_dora.pt"])
    started = time.perf_counter()
    pipeline = KPipeline(lang_code="e", repo_id=REPO, device="cuda")
    pipeline.model.eval()
    pipeline.load_voice(VOICE)
    load_ms = (time.perf_counter() - started) * 1000
    torch.cuda.reset_peak_memory_stats()
    manifest = {"model": REPO, "revision": revision, "snapshot": snapshot, "voice": VOICE, "lang_code": "e", "device": "cuda", "dtype": "float32", "sample_rate": 24000, "load_ms": round(load_ms, 2), "cuda_device": torch.cuda.get_device_name(0)}
    results = {}
    for name, text in SAMPLES.items():
        chunks = split_kokoro_text(pipeline, text)
        t0 = time.perf_counter(); audio_parts = []
        with torch.inference_mode():
            for chunk in chunks:
                for result in list(pipeline(chunk, voice=VOICE, speed=1.0, split_pattern=None)):
                    if result.audio is not None:
                        audio_parts.append(result.audio.detach().float().cpu().numpy())
        if not audio_parts:
            raise RuntimeError(f"No audio generated for {name}")
        audio = __import__('numpy').concatenate(audio_parts)
        wav = OUT / f"kokoro_{name}_ef_dora_24khz.wav"; sf.write(wav, audio, 24000, subtype="PCM_16")
        results[name] = {"text": text, "chunks": chunks, "source_chars": len(text), "audio_samples": int(audio.size), "duration_s": round(float(audio.size / 24000), 3), "synthesis_ms": round((time.perf_counter()-t0)*1000, 2), "wav": str(wav), "sha256": sha256(wav)}
    manifest["vram_allocated_bytes"] = int(torch.cuda.memory_allocated())
    manifest["vram_peak_bytes"] = int(torch.cuda.max_memory_allocated())
    manifest["samples"] = results
    (OUT / "kokoro_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "kokoro_texts.json").write_text(json.dumps(SAMPLES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
