import json
import os
import re
import sqlite3
import threading
import time
import uuid
import traceback
from pathlib import Path

import requests
import torch
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from qdrant_client import QdrantClient
from sentence_transformers import CrossEncoder, SentenceTransformer
from voice.trace import trace_event
from backend.app.intent_router import CONVERSATION, CURRENT_INFO, GIANA_META, OUT_OF_SCOPE, TOURISM_RAG, WEB_FOLLOWUP, classify_intent, conversation_answer, normalize_transcript, out_of_scope_answer
from backend.app.persona import persona_answer
try:
    from livekit.api import AccessToken, VideoGrants
except ImportError:
    AccessToken = VideoGrants = None

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DB = ROOT / "data/generated/giana.sqlite3"
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").replace("qdrant:6333", "localhost:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "giana_granite_v2")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "ibm-granite/granite-embedding-97m-multilingual-r2")
RERANK_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
GPU_LOCK = threading.Lock()
QDRANT = QdrantClient(url=QDRANT_URL)


class ModelManager:
    """Owns the single CUDA model pair and makes startup/warmup explicit."""

    def __init__(self):
        self.embedder = None
        self.reranker = None
        self.loaded = False
        self.warmed = False
        self.load_ms = None
        self.warmup_ms = None

    def load(self):
        if self.loaded:
            return
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requerida por M1; no se permite fallback silencioso")
        started = time.perf_counter()
        dtype = torch.float16
        self.embedder = SentenceTransformer(EMBED_MODEL, device="cuda", model_kwargs={"torch_dtype": dtype})
        self.reranker = CrossEncoder(RERANK_MODEL, device="cuda", model_kwargs={"torch_dtype": dtype})
        self.embedder.eval()
        self.reranker.model.eval()
        self.loaded = True
        self.load_ms = round((time.perf_counter() - started) * 1000, 2)

    def warmup(self):
        self.load()
        if self.warmed:
            return
        started = time.perf_counter()
        with torch.inference_mode():
            self.embedder.encode("warmup", normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
            self.reranker.predict([["warmup", "warmup"]])
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        self.warmed = True
        self.warmup_ms = round((time.perf_counter() - started) * 1000, 2)

    def embed(self, query):
        self.load()
        with GPU_LOCK, torch.inference_mode():
            return self.embedder.encode(query, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False).tolist()

    def rerank(self, pairs):
        self.load()
        with GPU_LOCK, torch.inference_mode():
            return self.reranker.predict(pairs)

    def status(self):
        return {
            "loaded": self.loaded,
            "warmed": self.warmed,
            "embedding_model": EMBED_MODEL,
            "reranker_model": RERANK_MODEL,
            "device": "cuda" if self.loaded else None,
            "dtype": "float16" if self.loaded else None,
            "load_ms": self.load_ms,
            "warmup_ms": self.warmup_ms,
        }


MODELS = ModelManager()
DIAGNOSTICS_ENABLED = os.getenv("GIANA_DIAGNOSTICS", "false").lower() == "true"
COUNTERS = {name: 0 for name in (
    "granite_encode_count", "reranker_predict_count", "qdrant_query_count", "fts_query_count",
    "rag_query_count", "llm_request_count", "moonshine_final_transcript_count", "piper_synthesis_count",
    "web_search_count", "web_fetch_count",
)}
COUNTER_LOCK = threading.Lock()


def count(name):
    if DIAGNOSTICS_ENABLED:
        with COUNTER_LOCK:
            COUNTERS[name] += 1


def now_ms(started):
    return round((time.perf_counter() - started) * 1000, 2)

app = Flask(__name__)
CONSENTS = {}
ACTIVE_GENERATIONS = {}
SESSION_HISTORY = {}


def strip_web_request_words(text):
    cleaned = re.sub(r"\b(dale|animate|anímate|por favor|s[ií]|ok|bueno|entonces|mir[aá]|te estoy pidiendo que|quiero que|podés|podes|puedes)\b", " ", text, flags=re.I)
    cleaned = re.sub(r"\b(bus(?:c[aá]|qu[eé])\w{0,5}|consult[aá]\w{0,3}|fijate|averigu[aá]\w{0,3}|información sobre|informacion sobre|info sobre)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(en (?:la )?web|en internet|online|en l[ií]nea|en google)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:¿?¡!")
    return cleaned


def standalone_query(session_id, query):
    history = SESSION_HISTORY.get(session_id, [])
    q = query.lower().strip()
    followup = q.startswith(("y ", "y?", "otros", "otra", "ese", "esa", "sí", "si ")) or q in {"¿y otros lugares?", "y otros lugares?"}
    if classify_intent(query) == WEB_FOLLOWUP:
        topic = strip_web_request_words(query)
        # "dale, buscalo en la web" no trae tema propio: el tema es el turno anterior.
        if len(topic) < 8 and history:
            previous = strip_web_request_words(history[-1]["user"])
            return previous or history[-1]["user"]
        return topic or query
    if followup and history:
        return f"{query} (seguimiento de la consulta anterior: {history[-1]['user']})"
    return query


def remember_turn(session_id, user, assistant):
    history = SESSION_HISTORY.setdefault(session_id, [])
    history.append({"user": user, "assistant": assistant})
    del history[:-10]


def lexical(query, limit=20):
    terms = [x for x in query.replace("?", " ").split() if len(x) > 2]
    match = " OR ".join('"' + x.replace('"', '') + '"' for x in terms) or '"lavalleja"'
    with sqlite3.connect(DB) as db:
        rows = db.execute("SELECT source_fts.block_id, source_fts.title, source_fts.text, b.start_line, b.end_line, b.source_refs, bm25(source_fts) score FROM source_fts JOIN source_blocks b ON b.block_id=source_fts.block_id WHERE source_fts MATCH ? ORDER BY score LIMIT ?", (match, limit)).fetchall()
    count("fts_query_count")
    return [{"chunk_id": r[0], "title": r[1], "text": r[2], "start_line": r[3], "end_line": r[4], "source_refs": json.loads(r[5]) if r[5] else [], "lexical_score": r[6]} for r in rows]


def structured_lookup(query):
    """Fast path for exact entity/contact/catalog questions."""
    q = query.lower()
    with sqlite3.connect(DB) as db:
        rows = db.execute("SELECT e.entity_id,e.name,e.zone,e.location_text,e.description,e.status,e.start_line,e.end_line,GROUP_CONCAT(c.contact,' | ') FROM entities e LEFT JOIN entity_contacts c ON c.entity_id=e.entity_id GROUP BY e.entity_id").fetchall()
    hits = []
    for row in rows:
        name = row[1]
        if name.lower() not in q and not any(part in q for part in name.lower().split() if len(part) > 4):
            continue
        if any(x in q for x in ("teléfono", "telefono", "contacto", "dirección", "direccion")):
            text = f"{name}. Ubicación: {row[3] or 'no publicada'}. Contactos: {row[8] or 'no publicados'}. Estado: {row[5]}"
            hits.append({"chunk_id": row[0], "title": name, "text": text, "start_line": row[6], "end_line": row[7], "source_refs": [], "structured": True})
        elif any(x in q for x in ("estado", "cerrado", "activo")):
            text = f"{name}: estado catalogado como {row[5]}. {row[4]}"
            hits.append({"chunk_id": row[0], "title": name, "text": text, "start_line": row[6], "end_line": row[7], "source_refs": [], "structured": True})
    if not hits and any(term in q for term in ("teléfono", "telefono", "email", "correo", "contacto", "dirección", "direccion", "listado", "categoría", "categoria")):
        hits = [{**row, "structured": True} for row in lexical(query, limit=6)]
    return hits[:6]


def dense(query, limit=20):
    count("granite_encode_count")
    vector = MODELS.embed(query)
    count("qdrant_query_count")
    hits = QDRANT.query_points(collection_name=COLLECTION, query=vector, limit=limit, with_payload=True).points
    return [{**h.payload, "dense_score": h.score} for h in hits]


def retrieve_with_route(query, timings=None):
    started = time.perf_counter()
    timings = timings if timings is not None else {}
    exact = structured_lookup(query)
    if exact:
        timings["structured_ms"] = now_ms(started)
        return exact, "FAST_STRUCTURED"
    timings["structured_ms"] = now_ms(started)
    fts_started = time.perf_counter(); lex = lexical(query); timings["fts_ms"] = now_ms(fts_started)
    embed_started = time.perf_counter(); den = dense(query); timings["embedding_qdrant_ms"] = now_ms(embed_started)
    rrf_started = time.perf_counter()
    merged = {}
    for rank, row in enumerate(lex):
        key = row.get("chunk_id") or row.get("block_id")
        merged.setdefault(key, {}).update(row); merged[key]["rrf"] = merged[key].get("rrf", 0) + 1 / (60 + rank + 1)
    for rank, row in enumerate(den):
        key = row["chunk_id"]
        merged.setdefault(key, {}).update(row); merged[key]["rrf"] = merged[key].get("rrf", 0) + 1 / (60 + rank + 1)
    candidates = sorted(merged.values(), key=lambda x: x["rrf"], reverse=True)[:6]
    timings["rrf_ms"] = now_ms(rrf_started)
    route = "HYBRID"
    top_gap = candidates[0]["rrf"] - candidates[1]["rrf"] if len(candidates) > 1 else 1.0
    semantic = any(term in query.lower() for term in ("qué", "que", "dónde", "donde", "recomend", "puedo", "lluvia", "sin gluten", "vegano"))
    if len(candidates) > 1 and semantic and top_gap < 0.001:
        route = "HYBRID_RERANK"
        rerank_started = time.perf_counter()
        count("reranker_predict_count")
        scores = MODELS.rerank([[query, x["text"][:1700]] for x in candidates[:6]])
        timings["rerank_ms"] = now_ms(rerank_started)
        for item, score in zip(candidates, scores): item["rerank_score"] = float(score)
        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
    return candidates[:6], route


def retrieve(query, timings=None):
    count("rag_query_count")
    return retrieve_with_route(query, timings=timings)


def second_chance(query):
    """Small deterministic reformulation set; maximum three alternatives."""
    q = query.lower()
    alternatives = [query]
    replacements = [("comer", "restaurante"), ("helado", "heladería"), ("perro", "mascotas"), ("electricidad", "conexión eléctrica"), ("té", "casa de té")]
    for old, new in replacements:
        if old in q:
            alternatives.append(re.sub(old, new, query, flags=re.I))
    alternatives = list(dict.fromkeys(alternatives))[:3]
    merged = {}
    for alt in alternatives:
        for item in retrieve_with_route(alt)[0]:
            merged[item.get("chunk_id")] = item
    return sorted(merged.values(), key=lambda x: x.get("rrf", 0), reverse=True)[:6]


LLM_SESSION = requests.Session()


def llm_answer(query, evidence, timings=None, trace_context=None, context=None, retrieval_query=None):
    timings = timings if timings is not None else {}
    key = os.getenv("OLLAMA_API_KEY", "")
    if not key:
        return None, "LLM_UNAVAILABLE"
    package = "\n\n".join(f"[{i+1}] {x['title']} (líneas {x['start_line']}-{x['end_line']}; fuentes {x.get('source_refs', [])})\n{x['text']}" for i, x in enumerate(evidence))
    context_text = "\n".join(f"Usuario: {x['user']}\nGiana: {x['assistant']}" for x in (context or [])[-4:])
    freshness = "Si pide hoy, ahora o esta noche y la evidencia no confirma horarios actuales, aclaralo y ofrecé buscarlo en la web; no afirmes que un lugar está abierto."
    scope = (
        "Sos Giana, la asistente turística del departamento de Lavalleja, Uruguay. Tu alcance es exclusivamente Lavalleja "
        "(Minas, Villa Serrana, Aguas Blancas, Solís de Mataojo, José Pedro Varela, Mariscala, Zapicán, Pirarajá, Polanco, Cerro Arequita, "
        "Salto del Penitente, Parque Salus, Geoparque Manantiales Serranos y alrededores). Si una parte de la evidencia habla de un lugar "
        "fuera de Lavalleja (otra ciudad, otro país, cadenas internacionales), IGNORALA por completo y decí que no tenés ese dato para Lavalleja. "
        "Nunca recomiendes ni describas lugares fuera del departamento. Si el usuario nombra un lugar que no es de Lavalleja, aclaralo con amabilidad "
        "y ofrecé alternativas dentro de Lavalleja. Si el nombre que usa el usuario parece una transcripción imperfecta de un lugar de la evidencia "
        "(por ejemplo 'ser varequita' por Cerro Arequita), asumí que se refiere a ese lugar y respondé sobre él sin señalar el error."
    )
    prompt = f"""{scope}\nRespondé en español rioplatense usando solamente la evidencia. No inventes datos. Si falta algo, decilo. Para conversación por voz, respondé de forma concisa: normalmente entre 1 y 4 frases. Ampliá sólo si el usuario lo pide. {freshness}\nPregunta actual: {query}\nConsulta de recuperación: {retrieval_query or query}\nCONTEXTO REAL RECIENTE:\n{context_text or '(sin contexto previo)'}\n\nEVIDENCIA:\n{package}"""
    base = os.getenv("OLLAMA_BASE_URL", "https://ollama.com").rstrip("/")
    headers = {"Authorization": f"Bearer {key}"}

    def run_model(model, read_timeout, event_name):
        count("llm_request_count")
        started = time.perf_counter()
        first_seen = False
        parts = []
        if trace_context:
            trace_event("backend", "llm_request_started", **trace_context, detail=f"model={model}")
        try:
            with LLM_SESSION.post(f"{base}/api/generate", headers=headers, json={"model": model, "prompt": prompt, "stream": True}, stream=True, timeout=(5, read_timeout)) as response:
                timings["llm_connect_ms"] = now_ms(started)
                response.raise_for_status()
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if not first_seen:
                        first_seen = True
                        timings["llm_first_token_ms"] = now_ms(started)
                        if trace_context:
                            trace_event("backend", "llm_first_chunk", **trace_context, detail=f"model={model}", elapsed_ms=timings["llm_first_token_ms"])
                    try:
                        parts.append(json.loads(line).get("response", ""))
                    except json.JSONDecodeError:
                        continue
            timings["llm_total_ms"] = now_ms(started)
            answer = "".join(parts).strip()
            if not answer:
                raise requests.RequestException("empty model response")
            if trace_context:
                trace_event("backend", event_name, **trace_context, detail=f"model={model}", elapsed_ms=timings["llm_total_ms"])
            return answer, first_seen, None
        except requests.RequestException as exc:
            timings["llm_total_ms"] = now_ms(started)
            app.logger.exception("LLM model %s failed: %s", model, type(exc).__name__)
            if trace_context:
                trace_event("backend", "llm_timeout" if isinstance(exc, requests.Timeout) else "api_exception", **trace_context, status="error", detail=f"model={model} {type(exc).__name__}: {exc}", elapsed_ms=timings["llm_total_ms"])
            return "".join(parts).strip(), first_seen, exc

    primary = os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
    answer, first_seen, error = run_model(primary, 10, "llm_finished")
    if error is None:
        return answer, None
    if first_seen:
        return answer, "LLM_STREAM_INTERRUPTED"

    if trace_context:
        trace_event("backend", "llm_primary_failed", **trace_context, status="error", detail=f"model={primary}; fallback=glm-5.3-flash:cloud")
        trace_event("backend", "llm_fallback_started", **trace_context, detail="model=glm-5.3-flash:cloud")
    fallback_answer, _, fallback_error = run_model("glm-5.3-flash:cloud", 20, "llm_fallback_finished")
    if fallback_error is None:
        return fallback_answer, None
    if trace_context:
        trace_event("backend", "llm_fallback_failed", **trace_context, status="error", detail=f"{type(fallback_error).__name__}: {fallback_error}")
    return None, "LLM_UNAVAILABLE"


def web_headers():
    key = os.getenv("OLLAMA_API_KEY", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


LAVALLEJA_SIGNALS = (
    "lavalleja", "minas", "villa serrana", "aguas blancas", "solís de mataojo", "solis de mataojo", "josé pedro varela",
    "jose pedro varela", "mariscala", "zapicán", "zapican", "pirarajá", "piraraja", "polanco", "arequita", "penitente",
    "salus", "manantiales serranos", "uruguay", ".uy", "+598", "ruta 8", "ruta 12", "ruta 60",
)


def in_lavalleja_scope(text):
    t = (text or "").lower()
    return any(signal in t for signal in LAVALLEJA_SIGNALS)


def web_search(query):
    if not os.getenv("OLLAMA_API_KEY"):
        return None, "WEB_AUTH_ERROR"
    # La búsqueda siempre viaja anclada al territorio; sin esto aparecen hoteles de otros países.
    anchored = query if in_lavalleja_scope(query) and "uruguay" in query.lower() else f"{query} Lavalleja Uruguay"
    try:
        count("web_search_count")
        r = requests.post("https://ollama.com/api/web_search", headers=web_headers(), json={"query": anchored}, timeout=45)
        r.raise_for_status()
        return r.json(), None
    except requests.RequestException:
        return None, "WEB_SEARCH_ERROR"


def web_fetch(url):
    if not os.getenv("OLLAMA_API_KEY"):
        return None, "WEB_AUTH_ERROR"
    try:
        count("web_fetch_count")
        r = requests.post("https://ollama.com/api/web_fetch", headers=web_headers(), json={"url": url}, timeout=45)
        r.raise_for_status()
        return r.json(), None
    except requests.RequestException:
        return None, "WEB_FETCH_ERROR"


def web_results_to_evidence(results):
    evidence = []
    for item in (results or {}).get("results", [])[:6]:
        title = item.get("title") or "Resultado web"
        url = item.get("url") or ""
        content = (item.get("content") or "").strip()[:1500]
        if not content:
            continue
        # Un resultado sin ninguna señal territorial casi siempre es otro lugar homónimo.
        if not in_lavalleja_scope(f"{title} {url} {content}"):
            continue
        evidence.append({"title": title, "start_line": None, "end_line": None, "source_refs": [url] if url else [], "text": content})
    return evidence[:4]


def web_followup_response(query, retrieval_query, session_id, history, trace_context, generation_id):
    """The user already asked explicitly to search the web (WEB_FOLLOWUP); do it for real."""
    trace_event("backend", "web_search_started", **trace_context, detail=retrieval_query)
    results, error = web_search(retrieval_query)
    if error:
        trace_event("backend", "web_search_failed", **trace_context, status="error", detail=error)
        answer = "No pude buscar en la web ahora mismo. ¿Seguimos con lo que tengo en la guía local?"
        remember_turn(session_id, query, answer)
        return jsonify({"answer": answer, "state": "SYSTEM_ERROR", "error_code": error, "route": "WEB_SEARCH", "intent": WEB_FOLLOWUP, "rag_invoked": False, "web_invoked": True, "generation_id": generation_id, "evidence": []})
    evidence = web_results_to_evidence(results)
    trace_event("backend", "web_search_finished", **trace_context, detail=f"results={len(evidence)}")
    if not evidence:
        answer = "Busqué en la web pero no encontré nada confiable sobre eso en Lavalleja."
        remember_turn(session_id, query, answer)
        return jsonify({"answer": answer, "state": "NO_EVIDENCE", "route": "WEB_SEARCH", "intent": WEB_FOLLOWUP, "rag_invoked": False, "web_invoked": True, "generation_id": generation_id, "evidence": []})
    answer, error = llm_answer(retrieval_query, evidence, timings={}, trace_context=trace_context, context=history, retrieval_query=retrieval_query)
    if error:
        trace_event("backend", "api_response_finished", **trace_context, status="error", detail=error)
        return jsonify({"answer": None, "state": "SYSTEM_ERROR", "error_code": error, "route": "WEB_SEARCH", "intent": WEB_FOLLOWUP, "rag_invoked": False, "web_invoked": True, "evidence": evidence}), 503
    remember_turn(session_id, retrieval_query, answer)
    trace_event("backend", "api_response_finished", **trace_context, detail="HTTP 200 WEB_SEARCH")
    return jsonify({"answer": answer, "state": "ANSWERABLE", "route": "WEB_SEARCH", "intent": WEB_FOLLOWUP, "rag_invoked": False, "web_invoked": True, "generation_id": generation_id, "evidence": evidence})


@app.get("/health")
def health():
    return jsonify({"status": "ok", "embedding_model": EMBED_MODEL, "reranker_model": RERANK_MODEL, "cuda": True, "collection": COLLECTION})


@app.get("/ready")
def ready():
    collection_ready = False
    try:
        collection_ready = QDRANT.collection_exists(COLLECTION)
    except Exception:
        pass
    is_ready = MODELS.loaded and MODELS.warmed and collection_ready
    return jsonify({"status": "ready" if is_ready else "not_ready", "qdrant_ready": collection_ready, "models_loaded": MODELS.loaded, "models_warmed": MODELS.warmed, "llm_configured": bool(os.getenv("OLLAMA_API_KEY"))}), (200 if is_ready else 503)


@app.get("/api/diagnostics")
def diagnostics():
    with COUNTER_LOCK:
        counters = dict(COUNTERS)
    voice_counters_path = ROOT / "run" / "voice_counters.json"
    if voice_counters_path.exists():
        try:
            counters.update(json.loads(voice_counters_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return jsonify({"enabled": DIAGNOSTICS_ENABLED, "counters": counters, "models": MODELS.status()})


@app.post("/api/debug/trace")
@app.post("/api/debug/event")
def debug_trace_event():
    if not DIAGNOSTICS_ENABLED:
        return jsonify({"error": "diagnostics disabled"}), 404
    body = request.get_json(silent=True) or {}
    trace_event(body.get("component", "frontend"), body.get("event", "frontend_event"), session_id=body.get("session_id", ""), turn_id=body.get("turn_id", ""), generation_id=body.get("generation_id", ""), status=body.get("status", "ok"), detail=body.get("detail", ""), elapsed_ms=body.get("elapsed_ms"), source=body.get("source", "human"), qa_session_id=body.get("qa_session_id", ""), error_code=body.get("error_code", ""))
    return jsonify({"ok": True})


@app.get("/api/debug/last-turn")
def debug_last_turn():
    if not DIAGNOSTICS_ENABLED:
        return jsonify({"error": "diagnostics disabled"}), 404
    trace_path = ROOT / "logs" / "voice_trace.jsonl"
    events = []
    session_filter = request.args.get("session_id", "")
    if trace_path.exists():
        for line in trace_path.read_text(encoding="utf-8").splitlines()[-300:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if session_filter:
        events = [x for x in events if x.get("session_id") in {session_filter, ""}]
    qa_filter = request.args.get("qa_session", "")
    if qa_filter:
        events = [x for x in events if x.get("qa_session_id") == qa_filter]
    turn_ids = [x.get("turn_id") for x in events if x.get("turn_id")]
    last = turn_ids[-1] if turn_ids else ""
    # Keep connection/frontend events (which may precede the first transcript
    # and have no turn id) alongside the latest real turn.
    selected = [x for x in events if not last or not x.get("turn_id") or x.get("turn_id") == last]
    return jsonify({"turn_id": last, "events": selected})


@app.post("/api/ask-text")
def ask_text():
    body = request.get_json(silent=True) or {}
    raw_query = (body.get("question") or body.get("query") or "").strip()
    if not raw_query: return jsonify({"error": "question is required"}), 400
    # Los topónimos mal transcritos se corrigen antes de clasificar, recuperar y responder.
    query = normalize_transcript(raw_query)
    session_id = body.get("session_id", "default")
    turn_id = body.get("turn_id", f"text-{uuid.uuid4().hex[:8]}")
    generation_id = body.get("generation_id") or str(uuid.uuid4())
    trace_context = {"session_id": session_id, "turn_id": turn_id, "generation_id": generation_id, "source": body.get("source", "probe"), "qa_session_id": body.get("qa_session_id", "")}
    trace_event("backend", "api_ask_received", **trace_context, detail=query if query == raw_query else f"{query} (original: {raw_query})")
    ACTIVE_GENERATIONS[session_id] = generation_id
    retrieval_query = standalone_query(session_id, query)
    history = list(SESSION_HISTORY.get(session_id, []))
    trace_event("backend", "standalone_query_resolved", **trace_context, detail=retrieval_query, context_turns=len(history))
    intent_started = time.perf_counter()
    intent = classify_intent(query)
    intent_ms = now_ms(intent_started)
    rag_invoked = intent in {TOURISM_RAG, CURRENT_INFO}
    route = "PERSONA" if intent == GIANA_META else "CONVERSATION" if intent == CONVERSATION else "OUT_OF_SCOPE" if intent == OUT_OF_SCOPE else "WEB_SEARCH" if intent == WEB_FOLLOWUP else "HYBRID_RERANK"
    trace_event("backend", "intent_classified", **trace_context, detail=f"intent={intent} route={route} rag_invoked={str(rag_invoked).lower()}", intent=intent, route=route, rag_invoked=rag_invoked, elapsed_ms=intent_ms)
    if intent in {GIANA_META, CONVERSATION, OUT_OF_SCOPE}:
        answer = persona_answer(query) if intent == GIANA_META else out_of_scope_answer(query) if intent == OUT_OF_SCOPE else conversation_answer(query)
        remember_turn(session_id, query, answer)
        trace_event("backend", "rag_skipped", **trace_context, detail=f"intent={intent}", intent=intent, route=route, rag_invoked=False)
        trace_event("backend", "assistant_text_ready", **trace_context, detail=f"{route.lower()} answer_length={len(answer)}", intent=intent, route=route, rag_invoked=False)
        return jsonify({"answer": answer, "state": "ANSWERABLE", "route": route, "intent": intent, "rag_invoked": False, "generation_id": generation_id, "evidence": [], "normalized_query": query, "debug": {"timings": {"intent_ms": intent_ms, "rag_ms": 0, "total_ms": now_ms(intent_started)}}})
    if intent == WEB_FOLLOWUP:
        return web_followup_response(query, retrieval_query, session_id, history, trace_context, generation_id)
    timings = {"structured_ms": None, "fts_ms": None, "embedding_ms": None, "qdrant_ms": None, "rrf_ms": None, "rerank_ms": None, "evidence_ms": None, "llm_connect_ms": None, "llm_first_token_ms": None, "llm_total_ms": None}
    request_started = time.perf_counter()
    try:
        trace_event("backend", "structured_started", **trace_context)
        evidence, route = retrieve(retrieval_query, timings=timings)
        trace_event("backend", "structured_finished", **trace_context, detail=route)
        if "embedding_qdrant_ms" in timings:
            timings["embedding_ms"] = timings.pop("embedding_qdrant_ms")
    except Exception as exc:
        app.logger.exception("retrieval failure: %s", type(exc).__name__)
        trace_event("backend", "api_exception", **trace_context, status="error", detail=f"{type(exc).__name__}: {exc}")
        return jsonify({"answer": None, "state": "SYSTEM_ERROR", "error_code": "RAG_INDEX_UNAVAILABLE", "intent": intent, "rag_invoked": True, "evidence": []}), 503
    if not evidence:
        try: evidence = second_chance(retrieval_query); route = "HYBRID_RERANK"
        except Exception as exc:
            app.logger.exception("second chance retrieval failure")
            trace_event("backend", "api_exception", **trace_context, status="error", detail=f"{type(exc).__name__}: {exc}")
            return jsonify({"answer": None, "state": "SYSTEM_ERROR", "error_code": "RAG_INDEX_UNAVAILABLE", "intent": intent, "rag_invoked": True, "evidence": []}), 503
    state = "ANSWERABLE" if evidence else "NO_EVIDENCE"
    timings["evidence_ms"] = now_ms(request_started)
    if ACTIVE_GENERATIONS.get(session_id) != generation_id:
        return jsonify({"answer": None, "state": "INTERRUPTED", "generation_id": generation_id, "evidence": []})
    answer, error = llm_answer(query, evidence, timings=timings, trace_context=trace_context, context=history, retrieval_query=retrieval_query) if evidence else ("No encontré evidencia suficiente en la guía local.", None)
    if error:
        trace_event("backend", "api_response_finished", **trace_context, status="error", detail=error, elapsed_ms=timings.get("total_ms"))
        return jsonify({"answer": None, "state": "SYSTEM_ERROR", "error_code": error, "intent": intent, "rag_invoked": True, "evidence": evidence}), 503
    response = {"answer": answer, "state": state, "route": route, "intent": intent, "rag_invoked": True, "generation_id": generation_id, "evidence": [{k: x.get(k) for k in ["title", "start_line", "end_line", "source_refs", "text"]} for x in evidence]}
    remember_turn(session_id, query, answer)
    response["standalone_query"] = retrieval_query
    response["normalized_query"] = query
    if DIAGNOSTICS_ENABLED:
        timings["total_ms"] = now_ms(request_started)
        response["debug"] = {"timings": timings, "conversation_context_turns": len(history), "standalone_query": retrieval_query}
    trace_event("backend", "api_response_finished", **trace_context, detail=f"HTTP 200 {route}", elapsed_ms=timings.get("total_ms"))
    return jsonify(response)


@app.post("/api/web/consent")
def consent():
    body = request.get_json(silent=True) or {}
    session_id, query = body.get("session_id", "default"), (body.get("query") or "").strip()
    if not query: return jsonify({"error": "query is required"}), 400
    request_id = str(uuid.uuid4())
    CONSENTS[(session_id, request_id)] = {"query": query, "expires_at": time.time() + int(os.getenv("WEB_CONSENT_TTL_SECONDS", "120"))}
    return jsonify({"session_id": session_id, "request_id": request_id, "expires_at": CONSENTS[(session_id, request_id)]["expires_at"]})


@app.post("/api/web/search")
def consented_search():
    body = request.get_json(silent=True) or {}
    key = (body.get("session_id", "default"), body.get("request_id", ""))
    consent = CONSENTS.get(key)
    if not consent or consent["expires_at"] < time.time(): return jsonify({"error_code": "WEB_CONSENT_REQUIRED", "state": "ASKING_WEB_PERMISSION"}), 403
    query = body.get("query") or consent["query"]
    data, error = web_search(query)
    if error: return jsonify({"error_code": error, "state": "SYSTEM_ERROR"}), 502
    return jsonify({"state": "WEB_SEARCHING", "source": "web", "ephemeral": True, "timestamp": time.time(), "results": data})


@app.post("/api/web/fetch")
def fetch_web():
    body = request.get_json(silent=True) or {}
    data, error = web_fetch(body.get("url", ""))
    if error: return jsonify({"error_code": error, "state": "SYSTEM_ERROR"}), 502
    return jsonify({"source": "web", "ephemeral": True, "timestamp": time.time(), "result": data})


@app.post("/api/livekit/token")
def livekit_token():
    if AccessToken is None or not os.getenv("LIVEKIT_API_KEY") or not os.getenv("LIVEKIT_API_SECRET"):
        return jsonify({"error_code": "LIVEKIT_CONFIG_MISSING"}), 503
    body = request.get_json(silent=True) or {}
    room = body.get("room", "giana")
    identity = body.get("identity", f"guest-{uuid.uuid4().hex[:8]}")
    token = AccessToken(os.getenv("LIVEKIT_API_KEY"), os.getenv("LIVEKIT_API_SECRET")).with_identity(identity).with_name("Giana guest").with_grants(VideoGrants(room_join=True, room=room)).to_jwt()
    return jsonify({"url": os.getenv("LIVEKIT_URL", ""), "room": room, "identity": identity, "token": token})


if __name__ == "__main__":
    MODELS.load()
    MODELS.warmup()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False, use_reloader=False)
