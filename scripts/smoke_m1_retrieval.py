import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.main import retrieve, second_chance

QUESTIONS = [
    "¿Dónde puedo comer algo vegano en Minas?", "¿Dónde puedo tomar un helado con opciones sin gluten en Minas?", "¿El camping del Penitente tiene electricidad en las parcelas?", "¿Laguna de los Cuervos tiene camping habilitado?", "¿Puedo ir con mascota a Salus?", "¿Puedo llevar perro al Penitente?", "¿Dónde tomar té sin gluten en Villa Serrana?", "¿Hay comida vegana cerca de Mariscala?", "Si me alojo en Granja Penitente, ¿qué lugar para comer tengo al lado?", "¿Hotel Minas tiene estacionamiento propio garantizado?", "¿Cerro Místico acepta niños pequeños?", "¿Nico Pérez está en Lavalleja?", "¿Arequita es solamente subir un cerro?", "¿Puedo visitar libremente Cueva Amarilla?", "¿Puedo ir al Parque de Minas a almorzar sin hospedarme?", "¿Dónde cargo un auto eléctrico si me quedo en Villa Serrana?", "¿Dónde puedo dormir en José Pedro Varela?", "¿Cuál es el teléfono de la Catedral de Minas?", "¿Qué puedo hacer en Minas un día de lluvia?", "¿Los parrilleros del Penitente son gratis y también la entrada al parque?",
]

def main():
    results = []
    for q in QUESTIONS:
        evidence = retrieve(q)
        if not evidence: evidence = second_chance(q)
        results.append({"question": q, "evidence": len(evidence), "top": evidence[0]["title"] if evidence else None})
        print(json.dumps(results[-1], ensure_ascii=False))
    Path(ROOT / "reports/m1_retrieval.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = [x for x in results if not x["evidence"]]
    print(json.dumps({"total": len(results), "failures": len(failures), "report": "reports/m1_retrieval.json"}))
    raise SystemExit(1 if failures else 0)

if __name__ == "__main__": main()
