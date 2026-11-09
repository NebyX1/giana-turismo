import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


def main():
    load_dotenv()
    key = os.getenv("OLLAMA_API_KEY", "")
    if not key:
        print("OLLAMA_API_KEY: ausente")
        raise SystemExit(2)
    print("OLLAMA_API_KEY: presente (valor oculto)")
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333").replace("qdrant:6333", "localhost:6333")
    response = requests.get(f"{qdrant_url}/", timeout=10)
    response.raise_for_status()
    print(f"Qdrant: PASS ({response.status_code})")
    payload = {"model": os.getenv("OLLAMA_MODEL", "deepseek-v4.1-flash"), "prompt": "Respondé únicamente: M0 PASS", "stream": False}
    llm = requests.post("https://ollama.com/api/generate", headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=60)
    if llm.status_code >= 400:
        print(f"DeepSeek: FAIL ({llm.status_code})")
        print(llm.text[:300])
        raise SystemExit(3)
    print("DeepSeek: PASS (respuesta recibida)")
    print("M0 smoke: PASS")


if __name__ == "__main__":
    main()
