"""Validate sentence tokenization before accepting any voice connections."""
import os
from pathlib import Path


def prepare_text_runtime():
    import nltk
    from nltk.tokenize import sent_tokenize

    root = Path(os.environ.get("GIANA_NLTK_DATA", Path(__file__).resolve().parents[1] / "data" / "nltk_data")).resolve()
    # An explicit corpus path avoids Windows Store APPDATA redirection. Keep
    # NLTK's path checks enabled; authorize only this data directory.
    if str(root) not in nltk.data.path:
        nltk.data.path.insert(0, str(root))
    nltk.data.find("tokenizers/punkt_tab/english", paths=[str(root)])
    sentences = sent_tokenize("Hola. Soy Giana. Seguimos conversando.")
    if len(sentences) != 3:
        raise RuntimeError("Sentence tokenizer preflight failed")
    return root
