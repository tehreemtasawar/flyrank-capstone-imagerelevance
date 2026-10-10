"""
Ranks processed images against one post's embedding, highest similarity first.
Pure function over already-loaded data — no DB calls — so it is easy to test
and to swap for a real vector index (pgvector) later.
"""
from typing import Dict, List

from app.embedding_service import cosine_similarity


def rank_images(post_embedding: List[float], images: List[dict]) -> List[dict]:
    """
    images: dicts with image_id, subject, category, confidence, embedding.
    Images without an embedding are skipped. Raises ValueError if an image
    embedding comes from a different model (dimension mismatch).
    Returns the dicts with `similarity_score` added, sorted descending.
    """
    ranked = [
        {**img, "similarity_score": cosine_similarity(post_embedding, img["embedding"])}
        for img in images if img.get("embedding")
    ]
    ranked.sort(key=lambda x: x["similarity_score"], reverse=True)
    return ranked
