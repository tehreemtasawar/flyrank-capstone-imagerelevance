import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Suggestion
from app.schemas import ReviewAction, SuggestionOut
from app.serializers import suggestion_out

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.get("", response_model=List[SuggestionOut])
def list_suggestions(review_status: Optional[str] = Query(None, pattern="^(pending|approved|rejected)$"),
                     db: Session = Depends(get_db)):
    """The review queue — every suggestion with its guard reasoning."""
    q = db.query(Suggestion)
    if review_status:
        q = q.filter(Suggestion.review_status == review_status)
    return [suggestion_out(s) for s in q.order_by(Suggestion.id).all()]


@router.get("/{suggestion_id}", response_model=SuggestionOut)
def get_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    s = db.get(Suggestion, suggestion_id)
    if not s:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return suggestion_out(s)


@router.post("/{suggestion_id}/review", response_model=SuggestionOut)
def review_suggestion(suggestion_id: int, payload: ReviewAction, db: Session = Depends(get_db)):
    """Approve or reject a suggestion. Idempotent: repeating the same action is a no-op."""
    s = db.get(Suggestion, suggestion_id)
    if not s:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if payload.action == "approve" and s.image_id is None:
        raise HTTPException(status_code=409, detail="Nothing to approve: the guard found no confident match")
    new_status = "approved" if payload.action == "approve" else "rejected"
    if s.review_status != new_status:
        s.review_status, s.reviewed_at = new_status, datetime.datetime.utcnow()
        db.commit()
        db.refresh(s)
    return suggestion_out(s)
