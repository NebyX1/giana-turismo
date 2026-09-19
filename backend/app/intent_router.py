import re


CONVERSATION = "CONVERSATION"
GIANA_META = "GIANA_META"
TOURISM_RAG = "TOURISM_RAG"
CURRENT_INFO = "CURRENT_INFO"
WEB_FOLLOWUP = "WEB_FOLLOWUP"
OUT_OF_SCOPE = "OUT_OF_SCOPE"

LAVALLEJA_PLACES = (
    "lavalleja", "minas", "villa serrana", "aguas blancas", "solís de mataojo", "solis de mataojo",
    "josé pedro varela", "jose pedro varela", "mariscala", "zapicán", "zapican", "pirarajá", "piraraja",
    "polanco", "arequita", "penitente", "salus", "manantiales serranos", "geoparque", "verdún", "verdun",
    "cerro místico", "cerro mistico", "campanero", "santa lucía", "santa lucia", "nico pérez", "nico perez",
)

# Lugares con nombre propio que un turista puede mencionar y no pertenecen a Lavalleja.
FOREIGN_PLACES = (
    "montevideo", "punta del este", "maldonado", "colonia", "rocha", "canelones", "salto", "paysandú", "paysandu",
    "rivera", "tacuarembó", "tacuarembo", "durazno", "florida", "flores", "soriano", "río negro", "rio negro",
    "artigas", "cerro largo", "treinta y tres", "san josé", "san jose", "buenos aires", "valencia", "madrid",
    "barcelona", "parís", "paris", "roma", "londres", "nueva york", "miami", "río de janeiro", "rio de janeiro",
    "san pablo", "sao paulo", "santiago de chile", "lima", "bogotá", "bogota", "ciudad de méxico", "mexico",
    "méxico", "españa", "argentina", "brasil", "chile", "cancún", "cancun", "bariloche", "mendoza", "córdoba",
    "cordoba", "rosario", "gramado", "florianópolis", "florianopolis", "porto alegre",
)

# Variantes que Moonshine produce con frecuencia para topónimos del corpus.
STT_ALIASES = {
    "arequita": ("ser varequita", "cerro arequitá", "ser arequita", "varequita", "arekita", "are quita", "arequíta", "arequitá"),
    "minas": ("ciudadaninas", "ciudad de minas"),
    "villa serrana": ("villaserrana", "villa cerrana", "villa serana", "bilha serrana", "villaserana"),
    "penitente": ("penintente", "pénitente"),
    "salus": ("parque salú", "salú"),
    "lavalleja": ("la valleja", "lavaleja", "la balleja", "lavalleya", "labaieja", "lavalleha", "laballeja"),
    "aguas blancas": ("agua blanca", "aguasblancas"),
    "geoparque": ("geo parque", "geoparke", "geoparc"),
    "giana": ("gianna", "shanna", "jana", "yana", "geana", "jiana"),
}

CANONICAL_FORMS = {"arequita": "Cerro Arequita", "giana": "Giana", "salus": "Parque Salus"}


def normalize_transcript(text: str) -> str:
    """Corrige topónimos mal transcritos por STT antes de clasificar y recuperar."""
    normalized = text
    for canonical, variants in STT_ALIASES.items():
        replacement = CANONICAL_FORMS.get(canonical, canonical.title())
        for variant in sorted(variants, key=len, reverse=True):
            pattern = re.compile(r"\b" + re.escape(variant) + r"\b", re.IGNORECASE)
            normalized = pattern.sub(replacement, normalized)
    # "Cerro Cerro Arequita" cuando el usuario ya dijo "cerro".
    return re.sub(r"\b(cerro)\s+cerro\b", r"\1", normalized, flags=re.IGNORECASE)


def mentions_lavalleja(q: str) -> bool:
    return any(place in q for place in LAVALLEJA_PLACES)


def mentions_foreign_place(q: str) -> bool:
    return any(re.search(r"\b" + re.escape(place) + r"\b", q) for place in FOREIGN_PLACES)


def is_web_request(q: str) -> bool:
    if re.search(r"\b(bus(?:c[aá]|qu[eé])\w{0,5}|consult[aá]\w{0,3}|fijate|fíjate|averigu[aá]\w{0,3}|chequea|revis[aá])\b.{0,40}\b(web|internet|online|en línea|en linea|google)\b", q):
        return True
    if re.search(r"\b(web|internet)\b.{0,30}\b(busc|busq|consult|averigu|fijate)", q):
        return True
    return q.strip(" .!¡¿?") in {"buscalo en la web", "buscá en la web", "busca en la web", "buscar en la web", "en la web", "en internet", "sí, buscalo", "si, buscalo", "dale, buscalo"}


def classify_intent(text: str) -> str:
    q = re.sub(r"\s+", " ", normalize_transcript(text).lower().strip())
    meta_terms = (
        "quién sos", "quien sos", "qué sos", "que sos", "cómo te llamás",
        "como te llamas", "cuál es tu misión", "cual es tu mision",
        "qué hacés", "que haces", "qué podés hacer", "que podes hacer",
        "para qué servís", "para que servis",
    )
    if any(term in q for term in meta_terms):
        return GIANA_META
    if is_web_request(q):
        return WEB_FOLLOWUP
    if mentions_foreign_place(q) and not mentions_lavalleja(q):
        return OUT_OF_SCOPE
    # "hoy"/"ahora" sólo son información actual si preguntan por apertura, horario o disponibilidad.
    current_terms = (
        "está abierto", "esta abierto", "abierto ahora", "abre hoy", "cierra hoy", "cuánto cuesta hoy",
        "cuanto cuesta hoy", "hay lugar esta noche", "evento hay hoy", "hay lugar hoy", "disponibilidad hoy",
        "horario de hoy", "horarios de hoy", "hoy está", "hoy esta", "ahora está", "ahora esta", "qué eventos hay",
        "que eventos hay", "clima hoy", "tiempo hoy",
    )
    if any(term in q for term in current_terms):
        return CURRENT_INFO
    audio_check = re.search(r"\b(?:me (?:pod[eé]s )?escuchar|me escuch[aá]s|pod[eé]s escucharme|me o[íi]s|pod[eé]s escuchar(?: lo que| bien)?|me est[aá]s escuchando)\b", q)
    tourism_terms = (
        "minas", "lavalleja", "villa serrana", "arequita", "penitente", "comer",
        "comida", "vegano", "alojar", "alojamiento", "hotel", "cabaña", "camping", "geoparque", "paseo",
        "hacer", "turismo", "visitar", "conocer", "recomend", "restaurante", "cerro", "sierra", "salto",
    )
    tourism_query = any(term in q for term in tourism_terms)
    conversation_terms = {
        "hola", "hola giana", "buenas", "gracias", "dale", "ok", "cómo andás",
        "como andas", "estás ahí", "estas ahi", "me escuchás", "me escuchas", "chau", "adiós", "adios",
        "muchas gracias", "perfecto", "genial", "bien", "no", "sí", "si",
    }
    if q.strip(" .!¡¿?") in conversation_terms or (audio_check and not tourism_query):
        return CONVERSATION
    return TOURISM_RAG


def conversation_answer(text: str) -> str:
    q = text.lower().strip()
    if "gracia" in q:
        return "¡De nada! Cuando quieras, seguimos recorriendo Lavalleja."
    if "chau" in q or "adi" in q:
        return "¡Hasta luego! Que disfrutes Lavalleja."
    if "escuch" in q or "ahí" in q or "ahi" in q or "oís" in q or "ois" in q:
        return "Sí, te escucho. ¿Qué querés conocer de Lavalleja?"
    return "¡Hola! Decime, ¿en qué te puedo ayudar?"


def out_of_scope_answer(text: str) -> str:
    q = text.lower()
    place = next((p for p in FOREIGN_PLACES if re.search(r"\b" + re.escape(p) + r"\b", q)), None)
    if place:
        return f"Sobre {place.title()} no puedo ayudarte: soy la asistente turística de Lavalleja. Si querés, te cuento qué hacer en Minas, Villa Serrana o el Cerro Arequita."
    return "Eso queda fuera de Lavalleja, que es mi especialidad. ¿Querés que te recomiende algo del departamento?"
