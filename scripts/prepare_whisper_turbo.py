"""Download the pinned CTranslate2 conversion and verify CUDA load/warmup."""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
from huggingface_hub import HfApi
from faster_whisper.utils import download_model

ROOT = Path(__file__).resolve().parents[1]
REPO = os.getenv("WHISPER_TURBO_CT2_REPO", "mobiuslabsgmbh/faster-whisper-large-v3-turbo")
DEFAULT_PATH = ROOT / "models" / "whisper-large-v3-turbo"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", default=os.getenv("STT_MODEL_PATH", str(DEFAULT_PATH)))
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    target = Path(args.model_path).resolve(); target.parent.mkdir(parents=True, exist_ok=True)
    revision = HfApi().model_info(REPO, revision="main").sha
    path = download_model(REPO, output_dir=str(target), revision=revision)
    manifest = {"requested_model":"openai/whisper-large-v3-turbo", "effective_ct2_repo":REPO, "revision":revision, "path":str(Path(path).resolve()), "files":{n:(target/n).is_file() for n in ("config.json","model.bin","tokenizer.json","preprocessor_config.json")}}
    (target / "GIANA_MODEL_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if args.smoke:
        env=os.environ.copy(); env.update(STT_MODEL_PATH=str(target), STT_PROVIDER="whisper_turbo")
        return subprocess.run([sys.executable, str(ROOT/"scripts"/"whisper_cuda_smoke.py")], cwd=ROOT, env=env).returncode
    return 0

if __name__ == "__main__": raise SystemExit(main())
