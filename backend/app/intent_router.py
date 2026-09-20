import re
from backend.app.temporal import has_relative_time, is_event_query, plain


CONVERSATION = "CONVERSATION"
GIANA_META = "GIANA_META"
TOURISM_RAG = "TOURISM_RAG"
CURRENT_INFO = "CURRENT_INFO"
WEB_FOLLOWUP = "WEB_FOLLOWUP"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
CURRENT_TIME = "CURRENT_TIME"

LAVALLEJA_PLACES = (
    "lavalleja", "minas", "villa serrana", "aguas blancas", "solís de mataojo", "solis de mataojo",
    "josé pedro varela", "jose pedro varela", "mariscala", "zapicán", "zapican", "pirarajá", "piraraja",
    "polanco", "arequita", "penitente", "salus", "manantiales serranos", "geoparque", "verdún", "verdun",
    "cerro místico", "cerro mistico", "campanero", "santa lucía", "santa lucia", "nico pérez", "nico perez",
    "cerro artigas", "parque rodó", "parque rodo",
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
    if not web_allowed(q):
        return False
    if re.search(r'\ben (?:la )?(?:web|internet)\b', q):
        return True
    if re.search(r"\b(bus(?:c[aá]|qu[eé])\w{0,5}|consult[aá]\w{0,3}|fijate|fíjate|averigu[aá]\w{0,3}|chequea|revis[aá])\b.{0,40}\b(web|internet|online|en línea|en linea|google)\b", q):
        return True
    if re.search(r"\b(web|internet)\b.{0,30}\b(busc|busq|consult|averigu|fijate)", q):
        return True
    return q.strip(" .!¡¿?") in {"buscalo en la web", "buscá en la web", "busca en la web", "buscar en la web", "en la web", "en internet", "sí, buscalo", "si, buscalo", "dale, buscalo"}


def web_allowed(text):
    return not re.search(r'\b(?:no (?:busques|uses|consultes|buscas)|sin (?:usar|buscar en)|solo (?:el |tu |la )?(?:rag|guia))\b', plain(text))


def conversation_kind(text: str) -> str:
    """Classify bounded social turns that must never reach RAG or the web."""
    q = re.sub(r'\s+', ' ', plain(normalize_transcript(text))).strip(' .!¡¿?')
    if re.search(
        r'\b(?:hij[ao] de (?:mil )?putas?|la puta que te pario|put[ao]|forr[ao]|idiota|imbecil|estupid[ao]|'
        r'inutil|pelotud[ao]|bolud[ao]|tarad[ao]|malparid[ao]|basura|mierda|callate|cerra el orto|andate|'
        r'jodete|te odio|no servis para nada|das asco)\b', q
    ):
        return 'abuse'
    # Do not swallow a useful tourism request merely because it starts with
    # friendly small talk ("¿cómo estás y dónde puedo comer en Minas?").
    tourism_request = mentions_lavalleja(q) or bool(re.search(
        r'\b(?:donde (?:comer|aloj|ir)|hotel|camping|restaurante|paseo|visitar|evento|actividad|turismo|recomend)\b', q
    ))
    if not tourism_request and re.search(
        r'\b(?:como estas|como andas|como te va|que tal estas|todo bien|estas bien|como te sentis)\b', q
    ):
        return 'wellbeing'
    if re.fullmatch(
        r'(?:y )?(?:vos )?(?:sos (?:real|humana|una persona)|tenes (?:novi[ao]|familia|amigos|edad|sentimientos)|'
        r'cuantos anos tenes|donde vivis|te gusta [a-z0-9 ]+|cual es tu [a-z0-9 ]+ favorito|podes sentir|dormis|comes)', q
    ):
        return 'personal'
    if re.fullmatch(
        r'(?:podemos hablar de otra cosa|hablemos de otra cosa|contame (?:algo|un chiste)|que opinas(?: de [a-z0-9 ]+)?|'
        r'decime algo|estoy aburrid[ao])', q
    ):
        return 'scope'
    return ''


def pure_conversation(text: str) -> bool:
    """Compositional offline fast path; consume ALL text, never swallow a query.

    A greeting prefix alone cannot suppress a trailing request for facts.
    Remaining unknown words go to semantic selection, not to this fast path.
    """
    if conversation_kind(text):
        return True
    q = re.sub(r'[^a-z0-9 ]', ' ', plain(normalize_transcript(text)))
    q = re.sub(r'\s+', ' ', q).strip()
    units = [r'hola', r'buenas(?: tardes| noches| dias)?', r'buen(?:os)? dias',
             r'giana', r'che', r'bueno', r'por favor',
             r'(?:muchas )?gracias(?: por (?:la ayuda|todo|ayudarme))?',
             r'hasta (?:luego|despues|manana)', r'adios', r'chau', r'salud',
             r'estas ahi', r'seguis ahi(?: conmigo)?', r'estas funcionando', r'funcionas',
             r'me (?:escuchas|recibis|ois)(?: bien)?', r'me estas escuchando',
             r'me podes escuchar', r'podes escucharme', r'se oye lo que digo',
             r'uno dos tres', r'probando', r'para', r'dejame pensar',
             r'perfecto', r'genial', r'dale', r'ok', r'bien', r'si', r'no']
    return bool(q and re.fullmatch(r'(?:(?:'+'|'.join(units)+r')(?: |$))+',q))


def classify_intent(text: str) -> str:
    q = re.sub(r"\s+", " ", normalize_transcript(text).lower().strip())
    plain_q = plain(q)
    if pure_conversation(q):
        return CONVERSATION
    if not is_event_query(q) and re.search(r'\b(que (?:dia|fecha|hora)(?: y (?:dia|fecha|hora))?(?: es| son| tenemos| estamos)|en que (?:dia|fecha) estamos|que dia de la semana|(?:el )?dia de hoy.*cual es|decime la (?:hora|fecha)|sabes (?:la fecha|que dia|que hora)|fecha (?:y hora|actual)|hora actual)\b', plain_q):
        return CURRENT_TIME
    meta_terms = (
        "quién sos", "quien sos", "qué sos", "que sos", "cómo te llamás",
        "como te llamas", "cuál es tu misión", "cual es tu mision",
        "qué hacés", "que haces", "qué podés hacer", "que podes hacer",
        "para qué servís", "para que servis",
    )
    if any(term in q for term in meta_terms):
        return GIANA_META
    if mentions_foreign_place(q) and not mentions_lavalleja(q):
        return OUT_OF_SCOPE
    if is_web_request(q):
        return WEB_FOLLOWUP
    if is_event_query(q) and web_allowed(q) and not re.search(r'\b(historia|origen|que es)\b', plain_q):
        return CURRENT_INFO
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
        "muchas gracias", "perfecto", "genial", "bien", "no", "sí", "si", "salud",
    }
    if q.strip(" .!¡¿?") in conversation_terms or (audio_check and not tourism_query):
        return CONVERSATION
    return TOURISM_RAG


def conversation_answer(text: str, variant: int = 0) -> str:
    q = text.lower().strip()
    kind = conversation_kind(text)
    if kind == 'abuse':
        answers = (
            'Estoy para ayudarte, pero no puedo responder a insultos o agresiones. Si querés, preguntame algo sobre turismo en Lavalleja.',
            'Podemos seguir conversando con respeto. Puedo ayudarte con lugares, actividades, gastronomía y alojamiento en Lavalleja.',
            'No voy a responder a agresiones. Cuando quieras retomar con respeto, estoy acá para ayudarte a conocer Lavalleja.',
        )
        return answers[variant % len(answers)]
    if kind == 'wellbeing':
        answers = (
            'Gracias por preguntar. Estoy bien y lista para ayudarte con turismo en Lavalleja. ¿Qué te gustaría conocer?',
            'Todo bien por acá, gracias. Soy una asistente turística y puedo ayudarte con lugares, actividades, gastronomía y alojamiento en Lavalleja.',
            'Estoy funcionando bien y preparada para ayudarte a recorrer Lavalleja. Decime qué lugar o actividad te interesa.',
        )
        return answers[variant % len(answers)]
    if kind == 'personal':
        answers = (
            'Gracias por preguntar. Soy una asistente virtual turística: no tengo vida personal, pero puedo ayudarte con todo lo relacionado al turismo en Lavalleja.',
            'Soy una asistente virtual, así que no tengo experiencias personales. Mi especialidad es ayudarte a descubrir Lavalleja.',
            'No tengo vida personal como una persona, pero sí puedo orientarte sobre lugares, actividades, comida y alojamiento en Lavalleja.',
        )
        return answers[variant % len(answers)]
    if kind == 'scope':
        answers = (
            'Podemos conversar, aunque mi especialidad es el turismo en Lavalleja. Puedo recomendarte lugares, actividades, gastronomía y alojamiento.',
            'Estoy enfocada en ayudarte a conocer Lavalleja. Si querés, contame qué tipo de paseo o experiencia buscás.',
            'Mi tema es Lavalleja y su oferta turística. Puedo ayudarte a elegir un lugar para visitar, comer o alojarte.',
        )
        return answers[variant % len(answers)]
    if any(term in plain(q) for term in ('entendiendo mal', 'no entendiste', 'no me entendiste')):
        return 'Perdón, entendí mal. Decime qué parte querés que corrija.'
    if any(term in plain(q) for term in ('dejame pensar', 'espera', 'para un momento')):
        return 'Claro, te escucho cuando quieras seguir.'
    if q.strip(' .!¡¿?') == 'salud':
        return '¡Salud! Te escucho, seguimos cuando quieras.'
    if "gracia" in q:
        return "¡De nada! Cuando quieras, seguimos recorriendo Lavalleja."
    if "chau" in q or "adi" in q or 'hasta ' in q:
        return "¡Hasta luego! Que disfrutes Lavalleja."
    if "escuch" in q or "ahí" in q or "ahi" in q or "oís" in q or "ois" in q or any(t in plain(q) for t in ('recibis','funcion','se oye','probando')):
        return "Sí, te escucho. ¿Qué querés conocer de Lavalleja?"
    return "¡Hola! Decime, ¿en qué te puedo ayudar?"


def out_of_scope_answer(text: str) -> str:
    q = text.lower()
    place = next((p for p in FOREIGN_PLACES if re.search(r"\b" + re.escape(p) + r"\b", q)), None)
    if place:
        return f"Sobre {place.title()} no puedo ayudarte: soy la asistente turística de Lavalleja. Si querés, te cuento qué hacer en Minas, Villa Serrana o el Cerro Arequita."
    return "Eso queda fuera de Lavalleja, que es mi especialidad. ¿Querés que te recomiende algo del departamento?"
