"""Presentation-only cleanup for text that is shown or spoken to visitors."""
import re


_CITATION_MARKER = re.compile(r"\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\]")


def strip_citation_markers(text: str) -> str:
    """Remove internal numeric source markers from the user-facing answer."""
    cleaned = _CITATION_MARKER.sub('', str(text or ''))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"[ \t]+([,.;:])", r"\1", cleaned)
    return cleaned.strip()
