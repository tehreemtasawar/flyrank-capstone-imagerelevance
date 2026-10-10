"""
Database models.

Design notes (also explained in README):
- `Image.embedding` and `Post.embedding` store a JSON-encoded list of floats.
  At ~50 images this is fine performance-wise; pgvector is listed as optional
  in the brief and can be swapped in later without changing the API surface.
- `Suggestion` is the row the guard writes to and the review API reads/writes —
  it is the single source of truth for "what did we recommend and why".
- `CostLog` gets one row per vision or embedding call — required for the
  cost-tracking probe.
"""
import datetime
import json

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Index
)
from sqlalchemy.orm import relationship

from app.database import Base


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False, unique=True)
    path = Column(String, nullable=False)

    # Vision output (filled in by the batch job)
    subject = Column(String, nullable=True, index=True)
    category = Column(String, nullable=True, index=True)
    attributes_json = Column(Text, nullable=True)  # JSON list of strings
    caption = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    flagged_low_confidence = Column(Boolean, default=False)

    # Embedding of the caption (JSON list of floats) + which model produced it
    embedding_json = Column(Text, nullable=True)
    embedding_model = Column(String, nullable=True)
    vision_model = Column(String, nullable=True)

    processed = Column(Boolean, default=False)
    processing_error = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    def attributes(self):
        return json.loads(self.attributes_json) if self.attributes_json else []

    def embedding(self):
        return json.loads(self.embedding_json) if self.embedding_json else None


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)

    embedding_json = Column(Text, nullable=True)
    embedding_model = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    def embedding(self):
        return json.loads(self.embedding_json) if self.embedding_json else None


class Suggestion(Base):
    __tablename__ = "suggestions"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    image_id = Column(Integer, ForeignKey("images.id"), nullable=True, index=True)

    similarity_score = Column(Float, nullable=True)
    guard_decision = Column(String, nullable=False)  # "ACCEPT" | "REJECT"
    guard_reason = Column(String, nullable=False)

    review_status = Column(String, default="pending", index=True)  # pending | approved | rejected
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    post = relationship("Post")
    image = relationship("Image")


class CostLog(Base):
    __tablename__ = "cost_log"

    id = Column(Integer, primary_key=True, index=True)
    call_type = Column(String, nullable=False)  # "vision" | "embedding"
    ref_table = Column(String, nullable=False)  # "images" | "posts"
    ref_id = Column(Integer, nullable=False)
    model_name = Column(String, nullable=False)
    estimated_cost_usd = Column(Float, default=0.0)
    success = Column(Boolean, default=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class BatchJob(Base):
    """One row per background batch run — progress tracking + failure visibility."""
    __tablename__ = "batch_jobs"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, nullable=False, default="queued", index=True)
    # queued | running | completed | completed_with_errors | budget_exhausted | failed
    total = Column(Integer, default=0)
    processed = Column(Integer, default=0)
    flagged_low_confidence = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


Index("ix_suggestions_post_image", Suggestion.post_id, Suggestion.image_id)
Index("ix_cost_log_ref", CostLog.ref_table, CostLog.ref_id)
