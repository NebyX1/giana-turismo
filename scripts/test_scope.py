"""Real HTTP scope tests against the running backend: Giana must never leave Lavalleja."""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:5000/api/ask-text"
SESSION = "scope-test"
failures = []


def ask(question):
    body = json.dumps({"question": question, "session_id": SESSION, "source": "probe"}).encode("utf-8")
    request = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def check(label, condition, detail):
    print(f"{'PASS' if condition else 'FAIL'} {label}: {detail}")
    if not condition:
        failures.append(label)


# 1. Lugar extranjero explícito -> fuera de alcance, sin RAG ni web.
r = ask("qué puedo hacer en Valencia")
check("out_of_scope_valencia", r["route"] == "OUT_OF_SCOPE" and "lavalleja" in r["answer"].lower(), f"route={r['route']} answer={r['answer'][:90]}")

# 2. Web con tema propio, anclada: la respuesta no puede mencionar lugares de otros países.
r = ask("busca en la web información sobre el nuevo hotel plaza")
answer = r["answer"].lower()
foreign = [w for w in ("valencia", "malvarrosa", "españa", "madrid", "buenos aires") if w in answer]
check("web_anchored_hotel_plaza", r["route"] == "WEB_SEARCH" and not foreign, f"route={r['route']} foreign={foreign} answer={r['answer'][:110]}")

# 3. Pregunta local + seguimiento "buscalo" sin tema -> hereda el tema anterior.
ask("dónde puedo quedarme en Minas esta noche")
r = ask("dale animate y buscálo en la web")
check("web_followup_inherits_topic", r["route"] == "WEB_SEARCH" and "hotel" in r["answer"].lower() or "aloj" in r["answer"].lower(), f"route={r['route']} answer={r['answer'][:110]}")

# 4. Transcripción imperfecta de topónimo -> responde sobre Arequita sin señalar el error.
r = ask("¿Qué podés contarme de ser varequita?")
check("stt_alias_arequita", r["route"] != "OUT_OF_SCOPE" and "arequita" in r["answer"].lower() and "varequita" not in r["answer"].lower(), f"normalized={r.get('normalized_query')} answer={r['answer'][:110]}")

# 5. "hoy" no debe desviar una pregunta turística normal.
r = ask("hoy quiero conocer Minas, qué me recomendás")
check("hoy_is_not_current_info", r["intent"] == "TOURISM_RAG" and r["state"] == "ANSWERABLE", f"intent={r['intent']} state={r['state']}")

# 6. Saludo con nombre mal transcrito.
r = ask("Hola Jana, ¿podés escuchar lo que estoy hablando?")
check("greeting_alias", r["route"] == "CONVERSATION", f"route={r['route']} answer={r['answer']}")

print()
print("SCOPE_TEST_FAIL: " + ", ".join(failures) if failures else "SCOPE_TEST_PASS")
sys.exit(1 if failures else 0)
