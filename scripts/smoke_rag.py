import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.main import retrieve, llm_answer


def main():
    questions = ["¿Dónde puedo tomar el té en Villa Serrana?", "¿Nico Pérez está en Lavalleja?", "¿Dónde puedo cargar un auto eléctrico si me quedo en Villa Serrana?"]
    for question in questions:
        evidence = retrieve(question)
        answer, error = llm_answer(question, evidence)
        print(json.dumps({"question": question, "state": "ANSWERABLE" if evidence else "NO_EVIDENCE", "answer": answer, "error": error, "evidence": [{"title": x["title"], "lines": [x["start_line"], x["end_line"]]} for x in evidence]}, ensure_ascii=False))


if __name__ == "__main__": main()
