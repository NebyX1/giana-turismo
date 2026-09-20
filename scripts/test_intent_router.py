"""Deterministic intent-router contract tests; no models, RAG, or network calls."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.intent_router import CONVERSATION, CURRENT_INFO, GIANA_META, OUT_OF_SCOPE, TOURISM_RAG, WEB_FOLLOWUP, classify_intent, conversation_answer, conversation_kind, normalize_transcript


CASES = {
    "hola": (CONVERSATION, False),
    "¿me escuchás?": (CONVERSATION, False),
    "Hola, Gianna. ¿Me podés escuchar?": (CONVERSATION, False),
    "Hola, Jana. ¿Podés escuchar lo que estoy hablando?": (CONVERSATION, False),
    "Pero me podés escuchar o no me podés escuchar? No.": (CONVERSATION, False),
    "Hola Giana, ¿cómo estás?": (CONVERSATION, False),
    "No me respondiste a la pregunta: ¿cómo estás?": (CONVERSATION, False),
    "Necesito que me ayudes diciéndome cómo estás": (CONVERSATION, False),
    "¿Sos estúpida?": (CONVERSATION, False),
    "Sos una inútil": (CONVERSATION, False),
    "Andate a la mierda": (CONVERSATION, False),
    "La puta que te parió": (CONVERSATION, False),
    "Sos una basura": (CONVERSATION, False),
    "¿Tenés novio?": (CONVERSATION, False),
    "¿Dónde vivís?": (CONVERSATION, False),
    "¿Cuál es tu color favorito?": (CONVERSATION, False),
    "Podemos hablar de otra cosa": (CONVERSATION, False),
    "Contame un chiste": (CONVERSATION, False),
    "¿Cómo estás y dónde puedo comer en Minas?": (TOURISM_RAG, True),
    "¿Me escuchás? ¿Dónde puedo comer en Minas?": (TOURISM_RAG, True),
    "¿quién sos?": (GIANA_META, False),
    "¿cuál es tu misión?": (GIANA_META, False),
    "¿qué podés hacer?": (GIANA_META, False),
    "¿qué hacer en Minas?": (TOURISM_RAG, True),
    "¿dónde comer en Villa Serrana?": (TOURISM_RAG, True),
    "¿está abierto hoy?": (CURRENT_INFO, False),
    "hoy quiero conocer Minas": (TOURISM_RAG, True),
    "ahora quiero ir al Cerro Arequita": (TOURISM_RAG, True),
    "dale animate y buscálo en la web": (WEB_FOLLOWUP, False),
    "busca en la web información sobre el nuevo hotel plaza": (WEB_FOLLOWUP, False),
    "te estoy pidiendo que los busques en la web": (WEB_FOLLOWUP, False),
    "Si, debes buscarlos en internet": (WEB_FOLLOWUP, False),
    "qué sitios web tiene la intendencia": (TOURISM_RAG, True),
    "qué puedo hacer en Valencia": (OUT_OF_SCOPE, False),
    "recomendame un hotel en Punta del Este": (OUT_OF_SCOPE, False),
    "cómo llego desde Montevideo a Minas": (TOURISM_RAG, True),
    "¿Qué podés contarme de ser varequita?": (TOURISM_RAG, True),
    "dónde quedarme en las ciudadaninas esta noche": (TOURISM_RAG, True),
    "gracias": (CONVERSATION, False),
    "Gracias por la ayuda, hasta después": (CONVERSATION, False),
    "Muchas gracias por todo, chau": (CONVERSATION, False),
    "chau": (CONVERSATION, False),
}

NORMALIZATION = {
    "¿Qué podés contarme de ser varequita?": "¿Qué podés contarme de Cerro Arequita?",
    "qué hay en el cerro arequitá": "qué hay en el Cerro Arequita",
    "dónde quedarme en las ciudadaninas esta noche": "dónde quedarme en las Minas esta noche",
    "Hola, Jana. ¿Podés escuchar?": "Hola, Giana. ¿Podés escuchar?",
    "hoteles en Minas": "hoteles en Minas",
}


for query, (expected, rag) in CASES.items():
    actual = classify_intent(query)
    actual_rag = actual == TOURISM_RAG
    assert actual == expected, f"{query!r}: expected {expected}, got {actual}"
    assert actual_rag == rag, f"{query!r}: expected rag={rag}, got rag={actual_rag}"

for raw, expected in NORMALIZATION.items():
    actual = normalize_transcript(raw)
    assert actual == expected, f"normalize {raw!r}: expected {expected!r}, got {actual!r}"

assert conversation_kind('¿Sos estúpida?') == 'abuse'
assert 'insultos o agresiones' in conversation_answer('¿Sos estúpida?', 0)
assert conversation_answer('¿Sos estúpida?', 0) != conversation_answer('¿Sos estúpida?', 1)
assert conversation_kind('¿Cómo estás?') == 'wellbeing'
assert 'Estoy bien' in conversation_answer('¿Cómo estás?', 0)
assert conversation_answer('¿Cómo estás?', 0) != conversation_answer('¿Cómo estás?', 1)
assert conversation_kind('¿Tenés novio?') == 'personal'
assert 'asistente virtual turística' in conversation_answer('¿Tenés novio?', 0)

print(f"INTENT_ROUTER_PASS cases={len(CASES)} normalization={len(NORMALIZATION)}")
