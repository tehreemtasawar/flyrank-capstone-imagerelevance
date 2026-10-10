"""
Embedding service: text -> list[float].

Two explicit backends, chosen by EMBEDDING_BACKEND (never switched silently):
  - "gemini": real semantic embeddings (free tier). Failures RAISE EmbeddingError
    after retries — we never quietly substitute a different vector space, because
    mixing vector spaces makes every similarity score meaningless.
  - "local": deterministic hashed bag-of-words. NOT semantic. Exists so the
    plumbing can be run and tested with zero network access.
"""
import hashlib
import math
import time
from typing import List, Tuple

from app.config import settings

EMBED_DIM = 128
LOCAL_MODEL_NAME = "local-hash-embedding"
MAX_RETRIES = 3

_STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "of", "to", "for", "and", "or",
    "is", "are", "was", "were", "be", "been", "this", "that", "these",
    "those", "it", "its", "as", "with", "by", "from", "into", "over",
    "here", "here's", "post", "covers", "about",
}


class EmbeddingError(Exception):
    pass


def _local_embedding(text: str) -> List[float]:
    vec = [0.0] * EMBED_DIM
    words = [w.strip(".,!?'\"") for w in text.lower().split()]
    for word in (w for w in words if w and w not in _STOPWORDS):
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBED_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _gemini_embedding(text: str) -> List[float]:
    import google.generativeai as genai

    genai.configure(api_key=settings.GEMINI_API_KEY)
    result = genai.embed_content(
        model=settings.GEMINI_EMBEDDING_MODEL,
        content=text,
        task_type="SEMANTIC_SIMILARITY",
    )
    return result["embedding"]


def embedding_model_name() -> str:
    return LOCAL_MODEL_NAME if settings.EMBEDDING_BACKEND == "local" else settings.GEMINI_EMBEDDING_MODEL


def get_embedding(text: str) -> Tuple[List[float], str]:
    """Returns (embedding, model_name). Raises EmbeddingError if it cannot."""
    if settings.EMBEDDING_BACKEND == "local":
        return _local_embedding(text), LOCAL_MODEL_NAME

    if not settings.GEMINI_API_KEY:
        raise EmbeddingError("EMBEDDING_BACKEND=gemini but GEMINI_API_KEY is not set")

    last = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _gemini_embedding(text), settings.GEMINI_EMBEDDING_MODEL
        except Exception as e:  # SDK raises many types; most are retryable
            last = e
            if "API_KEY_INVALID" in str(e) or "API key not valid" in str(e):
                raise EmbeddingError(f"Invalid Gemini API key - fix GEMINI_API_KEY in .env ({e})".split("\n")[0])
            time.sleep(2 * attempt)
    raise EmbeddingError(f"Gemini embedding failed after {MAX_RETRIES} attempts: {last}")


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if len(a) != len(b):
        raise ValueError(
            f"Embedding dimension mismatch ({len(a)} vs {len(b)}): vectors come from different "
            f"embedding models. Run scripts/recompute_embeddings.py."
        )
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
