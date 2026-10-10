"""
Pydantic schemas.

VisionTagResult is the important one: every vision-model response is validated
against it before anything touches the database. Invalid -> retried or flagged,
never inserted as-is ("never trust invalid model output").
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class VisionTagResult(BaseModel):
    subject: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    attributes: List[str] = Field(default_factory=list)
    caption: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("attributes")
    @classmethod
    def cap_attributes(cls, v):
        return v[:10]  # sanity cap


class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    body: str = Field(..., min_length=1, max_length=20000)

    @field_validator("title", "body")
    @classmethod
    def not_blank(cls, v):
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    body: str


class ImageOut(BaseModel):
    id: int
    filename: str
    subject: Optional[str] = None
    category: Optional[str] = None
    attributes: List[str] = []
    caption: Optional[str] = None
    confidence: Optional[float] = None
    flagged_low_confidence: bool = False
    processed: bool = False
    processing_error: Optional[str] = None


class SuggestionOut(BaseModel):
    id: int
    post_id: int
    image_id: Optional[int]
    similarity_score: Optional[float]
    guard_decision: str
    guard_reason: str
    review_status: str
    image: Optional[ImageOut] = None


class RankedCandidate(BaseModel):
    rank: int
    image_id: int
    filename: str
    subject: Optional[str]
    similarity_score: float
    guard_decision: str
    guard_reason: str


class PostMatchOut(BaseModel):
    """Response of GET /posts/{id}/images — the chosen image (or an explicit
    'no confident match') plus the ranked, explained candidate list."""
    post_id: int
    decision: str  # "MATCH" | "NO_CONFIDENT_MATCH"
    message: str
    suggestion: SuggestionOut
    candidates: List[RankedCandidate]


class GuardCheckOut(BaseModel):
    post_id: int
    image_id: int
    filename: str
    subject: Optional[str]
    similarity_score: float
    similarity_threshold: float
    guard_decision: str
    guard_reason: str


class ReviewAction(BaseModel):
    action: str  # "approve" | "reject"

    @field_validator("action")
    @classmethod
    def valid_action(cls, v):
        if v not in ("approve", "reject"):
            raise ValueError("action must be 'approve' or 'reject'")
        return v


class BatchJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    total: int
    processed: int
    flagged_low_confidence: int
    failed: int
    skipped: int
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
