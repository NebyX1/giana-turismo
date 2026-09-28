"""Grounded replies to requests about Gianna's own preceding answer."""

import re

from backend.app.presentation import strip_citation_markers
from backend.app.temporal import plain


_RECALL_PATTERNS = (
    r"\b(?:que|de que|cual)\b.{0,65}\b(?:estabas|venias)\s+(?:diciendo|contando|explicando|comentando|hablando)\b",
    r"\b(?:que|de que)\b.{0,65}\b(?:dijiste|decias|contaste|comentaste|hablabas)\b",
    r"\b(?:repeti|repetime|repite|repetir|recordame|recuerdame)\b.{0,90}\b(?:lo que|eso|respuesta|dijiste|decias|contaste|antes|recien|ultimo)\b",
    r"\b(?:segui|continua|retoma|retomemos)\b.{0,90}\b(?:contando|diciendo|explicando|hablando|respuesta|antes|lo que|tema)\b",
    r"\b(?:tu|la)\s+(?:respuesta|explicacion|comentario)\s+(?:de antes|anterior|de recien)\b",
    r"\b(?:de que|que)\s+(?:veniamos|estabamos)\s+hablando\b",
)


def is_recap_request(text: str) -> bool:
    """Detect an explicit reference to our prior speech, even after STT noise."""
    normalized = re.sub(r"\s+", " ", plain(text)).strip()
    return any(re.search(pattern, normalized) for pattern in _RECALL_PATTERNS)


def preceding_answer(history: list[dict]) -> str | None:
    """Prefer the last factual answer; social replies must not hide it."""
    substantive = [turn for turn in history if turn.get("assistant") and turn.get("intent") not in
                   {"CONVERSATION", "GIANA_META", "CURRENT_TIME"}]
    candidates = substantive or [turn for turn in history if turn.get("assistant")]
    return strip_citation_markers(candidates[-1]["assistant"]) if candidates else None


def recap_answer(history: list[dict]) -> str:
    previous = preceding_answer(history)
    if not previous:
        return "No tengo una respuesta anterior registrada en esta conversación. ¿Qué tema querés retomar?"
    # Extract sentences from the actual answer, not a new model generation.
    # This avoids inventing facts or running a new web search just to recap.
    sentences = re.split(r"(?<=[.!?])\s+", previous)
    excerpt = []
    for sentence in sentences:
        if excerpt and (len(excerpt) >= 3 or len(" ".join(excerpt)) + len(sentence) > 500):
            break
        excerpt.append(sentence)
    return "Te estaba contando esto: " + " ".join(excerpt).strip()
