"""
Re-embeds every processed image caption and every post with the CURRENT
embedding backend, WITHOUT re-running vision (which has a much smaller quota).
Use after changing EMBEDDING_BACKEND / GEMINI_EMBEDDING_MODEL.

Usage: python scripts/recompute_embeddings.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cost_tracker import log_cost
from app.database import SessionLocal, init_db
from app.embedding_service import get_embedding
from app.models import Image, Post


def main():
    init_db()
    db = SessionLocal()
    try:
        n = 0
        for img in db.query(Image).filter(Image.processed.is_(True)).all():
            if img.caption:
                emb, model = get_embedding(img.caption)
                img.embedding_json, img.embedding_model = json.dumps(emb), model
                db.commit()
                log_cost(db, "embedding", "images", img.id, model)
                n += 1
        m = 0
        for post in db.query(Post).all():
            emb, model = get_embedding(f"{post.title}. {post.body}")
            post.embedding_json, post.embedding_model = json.dumps(emb), model
            db.commit()
            log_cost(db, "embedding", "posts", post.id, model)
            m += 1
        print(f"Re-embedded {n} images and {m} posts.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
