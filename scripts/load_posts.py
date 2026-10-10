"""
Loads data/posts.json into the database, embedding each post (one embedding
call per NEW post). Re-runnable: existing posts (same title) are skipped.

Usage: python scripts/load_posts.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cost_tracker import log_cost
from app.database import SessionLocal, init_db
from app.embedding_service import EmbeddingError, get_embedding
from app.models import Post

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        with open(os.path.join(ROOT, "data", "posts.json"), encoding="utf-8") as f:
            posts = json.load(f)
        loaded = failed = 0
        for p in posts:
            if db.query(Post).filter(Post.title == p["title"]).first():
                continue
            try:
                emb, model = get_embedding(f"{p['title']}. {p['body']}")
            except EmbeddingError as e:
                print(f"FAILED to embed '{p['title']}': {e}")
                failed += 1
                continue
            post = Post(title=p["title"], body=p["body"], embedding_json=json.dumps(emb), embedding_model=model)
            db.add(post)
            db.commit()
            db.refresh(post)
            log_cost(db, "embedding", "posts", post.id, model)
            loaded += 1
        print(f"Loaded {loaded} new posts, {len(posts) - loaded - failed} already existed, {failed} failed.")
        sys.exit(1 if failed else 0)
    finally:
        db.close()
