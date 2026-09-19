import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.main import app

QUESTIONS = [
    "¿Dónde puedo comer algo vegano en Minas?", "¿Dónde puedo tomar un helado con opciones sin gluten en Minas?",
    "¿El camping del Penitente tiene electricidad en las parcelas?", "¿Laguna de los Cuervos tiene camping habilitado?",
    "¿Puedo ir con mascota a Salus?", "¿Puedo llevar perro al Penitente?", "¿Dónde tomar té sin gluten en Villa Serrana?",
    "¿Hay comida vegana cerca de Mariscala?", "Si me alojo en Granja Penitente, ¿qué lugar para comer tengo al lado?",
    "¿Hotel Minas tiene estacionamiento propio garantizado?", "¿Cerro Místico acepta niños pequeños?", "¿Nico Pérez está en Lavalleja?",
    "¿Arequita es solamente subir un cerro?", "¿Puedo visitar libremente Cueva Amarilla?", "¿Puedo ir al Parque de Minas a almorzar sin hospedarme?",
    "¿Dónde cargo un auto eléctrico si me quedo en Villa Serrana?", "¿Dónde puedo dormir en José Pedro Varela?", "¿Cuál es el teléfono de la Catedral de Minas?",
    "¿Qué puedo hacer en Minas un día de lluvia?", "¿Los parrilleros del Penitente son gratis y también la entrada al parque?",
]


def main():
    results = []
    with app.test_client() as client:
        for question in QUESTIONS:
            response = client.post("/api/ask-text", json={"question": question, "session_id": "m1-smoke"})
            payload = response.get_json()
            results.append({"question": question, "http": response.status_code, "state": payload.get("state"), "evidence": len(payload.get("evidence", [])), "error_code": payload.get("error_code")})
            print(json.dumps(results[-1], ensure_ascii=False))
    Path(ROOT / "reports").mkdir(exist_ok=True)
    Path(ROOT / "reports/m1_smoke.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = [r for r in results if r["http"] != 200 or r["state"] not in ("ANSWERABLE", "PARTIAL") or not r["evidence"]]
    print(json.dumps({"total": len(results), "failures": len(failures), "report": "reports/m1_smoke.json"}, ensure_ascii=False))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__": main()
