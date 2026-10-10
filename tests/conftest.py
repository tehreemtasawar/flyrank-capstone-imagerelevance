"""
Shared fixtures. Tests are hermetic: temp SQLite DB, temp images + mock vision
JSON, and a deterministic FAKE embedder (topic keywords + synonyms) so no
network or API key is needed. The fake embedder tests the *plumbing and guard
logic*; real semantic quality is measured by scripts/eval.py with Gemini.
"""
import os
import sys
import tempfile
import json

_TMP = tempfile.mkdtemp(prefix="capstone_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"   # must precede app imports
os.environ["EMBEDDING_BACKEND"] = "local"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib
import math

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage

from app.config import settings
from app.database import Base, SessionLocal, engine, init_db

TOPICS = {
    "fox": {"fox", "foxes", "vulpes", "vixen"},
    "wolf": {"wolf", "wolves", "canis", "lupus", "howling", "pack"},
    "dog": {"dog", "dogs", "puppy", "retriever"},
    "tech": {"programming", "python", "fastapi", "backend", "code"},
}
DIM = len(TOPICS) + 32


def fake_embedding(text):
    words = [w.strip(".,!?'\"").lower() for w in text.split()]
    vec = [0.0] * DIM
    for i, (_, kws) in enumerate(TOPICS.items()):
        vec[i] = 3.0 * sum(1 for w in words if w in kws)
    for w in words:
        vec[len(TOPICS) + int(hashlib.md5(w.encode()).hexdigest(), 16) % 32] += 0.2
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / n for v in vec], "fake-test-embedding"


MOCKS = {
    "fox_01": dict(subject="red fox", category="animal", attributes=["orange fur"], caption="A red fox stands in a forest", confidence=0.95),
    "fox_02": dict(subject="red fox", category="animal", attributes=["snow"], caption="A fox walks through snow", confidence=0.92),
    "wolf_01": dict(subject="gray wolf", category="animal", attributes=["pack"], caption="A gray wolf howling with its pack", confidence=0.93),
    "dog_01": dict(subject="domestic dog", category="animal", attributes=["pet"], caption="A dog and a puppy at play", confidence=0.4),  # low confidence
}


@pytest.fixture(scope="session", autouse=True)
def _schema():
    init_db()  # runs the real Alembic migrations
    yield


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    with engine.begin() as c:
        for t in reversed(Base.metadata.sorted_tables):
            c.execute(t.delete())
    img_dir, mock_dir = tmp_path / "images", tmp_path / "mock"
    img_dir.mkdir(), mock_dir.mkdir()
    for name, data in MOCKS.items():
        PILImage.new("RGB", (8, 8), "red").save(img_dir / f"{name}.jpg")
        (mock_dir / f"{name}.json").write_text(json.dumps(data))
    monkeypatch.setattr(settings, "IMAGES_DIR", str(img_dir))
    monkeypatch.setattr(settings, "MOCK_VISION_DIR", str(mock_dir))
    monkeypatch.setattr(settings, "USE_MOCK_VISION", True)
    monkeypatch.setattr(settings, "SIMILARITY_THRESHOLD", 0.3)
    monkeypatch.setattr(settings, "CONFIDENCE_THRESHOLD", 0.6)
    for mod in ("app.batch_jobs", "app.routers.posts"):
        monkeypatch.setattr(f"{mod}.get_embedding", fake_embedding)
    yield tmp_path


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def processed(client):
    """Corpus after the batch job ran."""
    r = client.post("/images/batch-process")
    assert r.status_code == 202
    return r.json()
