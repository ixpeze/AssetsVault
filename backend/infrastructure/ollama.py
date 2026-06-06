"""
infrastructure.ollama — Ollama HTTP adapter.

All external AI calls go through this module. Mock this module in tests;
never mock `requests` internals directly.
"""
import logging
import requests
from ..constants import OLLAMA_URL, EMBED_MODEL

log = logging.getLogger(__name__)


def get_embedding(text: str) -> list | None:
    """Return a 768-dim embedding vector for *text*, or None on failure."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json().get("embedding")
    except Exception as e:
        log.warning("[Ollama] Embedding error: %s", e)
    return None
