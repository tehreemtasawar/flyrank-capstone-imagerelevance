import datetime
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.cost_tracker import log_cost
from app.database import get_db
from app.embedding_service import EmbeddingError, cosine_similarity, get_embedding
from app.guard import evaluate, evaluate_candidates
from app.matching import rank_images
from app.models import Image, Post, Suggestion
from app.schemas import GuardCheckOut, PostCreate, PostMatchOut, PostOut, RankedCandidate
from app.serializers import suggestion_out

router = APIRouter(prefix="/posts", tags=["posts"])


def _post_text(post: Post) -> str:
    return f"{post.title}. {post.body}"


def _get_post(db: Session, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if not post.embedding():
        raise HTTPException(status_code=409, detail="Post has no embedding yet")
    return post


def _candidates(db: Session):
    imgs = db.query(Image).filter(Image.processed.is_(True)).all()
    return [
        {"image_id": i.id, "filename": i.filename, "subject": i.subject, "category": i.category,
         "confidence": i.confidence, "embedding": i.embedding()}
        for i in imgs
    ]


@router.post("", response_model=PostOut)
def create_post(payload: PostCreate, db: Session = Depends(get_db)):
    # Idempotent: re-posting identical content returns the existing post.
    existing = db.query(Post).filter(Post.title == payload.title, Post.body == payload.body).first()
    if existing:
        return existing
    try:
        embedding, model_name = get_embedding(_post_text(payload))
    except EmbeddingError as e:
        raise HTTPException(status_code=502, detail=f"Embedding service unavailable: {e}")
    post = Post(title=payload.title, body=payload.body,
                embedding_json=json.dumps(embedding), embedding_model=model_name)
    db.add(post)
    db.commit()
    db.refresh(post)
    log_cost(db, "embedding", "posts", post.id, model_name)
    return post


@router.get("", response_model=List[PostOut])
def list_posts(db: Session = Depends(get_db)):
    return db.query(Post).order_by(Post.id).all()


@router.get("/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.get("/{post_id}/images", response_model=PostMatchOut)
def get_suggested_image(post_id: int, limit: int = Query(5, ge=1, le=50), db: Session = Depends(get_db)):
    """
    Core endpoint: rank every processed image against the post, run the
    mismatch guard on the ranked list, and return either the accepted image or
    an explicit "no confident match" with reasons — plus the ranked candidates,
    each with its own verdict, so you can inspect WHY images were chosen/refused.

    The outcome is stored as a Suggestion for the review queue. Calling this
    repeatedly does not create duplicates while the outcome is unchanged.
    """
    post = _get_post(db, post_id)
    try:
        ranked = rank_images(post.embedding(), _candidates(db))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    verdicts = evaluate_candidates(_post_text(post), ranked, settings.SIMILARITY_THRESHOLD, settings.CONFIDENCE_THRESHOLD)
    chosen = next(((c, r) for c, r in verdicts if r.decision == "ACCEPT"), None)

    if chosen:
        chosen_id, guard = chosen[0]["image_id"], chosen[1]
        score = chosen[0]["similarity_score"]
    elif verdicts:
        top_c, top_r = verdicts[0]
        n_low = sum(1 for _, r in verdicts if r.code == "LOW_SIMILARITY")
        n_subj = sum(1 for _, r in verdicts if r.code == "SUBJECT_MISMATCH")
        summary = (
            f"Best-ranked image {top_c['filename']} was refused: {top_r.reason}. "
            f"Highest similarity was {top_c['similarity_score']:.2f} (threshold {settings.SIMILARITY_THRESHOLD:.2f}); "
            f"of {len(verdicts)} candidates, {n_low} fell below the similarity threshold and "
            f"{n_subj} had a subject that does not match the post."
        )
        from app.guard import GuardResult
        chosen_id, guard, score = None, GuardResult("REJECT", summary, top_r.code), top_c["similarity_score"]
    else:
        from app.guard import GuardResult
        chosen_id, guard, score = None, GuardResult("REJECT", "No candidate images available", "NO_METADATA"), None

    suggestion = (
        db.query(Suggestion).filter(Suggestion.post_id == post.id).order_by(Suggestion.id.desc()).first()
    )
    if suggestion and suggestion.image_id == chosen_id and suggestion.guard_decision == guard.decision:
        suggestion.similarity_score, suggestion.guard_reason = score, guard.reason  # refresh, keep review status
    else:
        suggestion = Suggestion(post_id=post.id, image_id=chosen_id, similarity_score=score,
                                guard_decision=guard.decision, guard_reason=guard.reason)
        db.add(suggestion)
    db.commit()
    db.refresh(suggestion)

    top = [
        RankedCandidate(rank=i + 1, image_id=c["image_id"], filename=c["filename"], subject=c["subject"],
                        similarity_score=round(c["similarity_score"], 4),
                        guard_decision=r.decision, guard_reason=r.reason)
        for i, (c, r) in enumerate(verdicts[:limit])
    ]
    if chosen_id:
        message = f"Suggested {chosen[0]['filename']}: {guard.reason}"
    else:
        message = f"No confident match for this post. {guard.reason}"
    return PostMatchOut(post_id=post.id, decision="MATCH" if chosen_id else "NO_CONFIDENT_MATCH",
                        message=message, suggestion=suggestion_out(suggestion), candidates=top)


@router.get("/{post_id}/check/{image_id}", response_model=GuardCheckOut)
def check_image_against_post(post_id: int, image_id: int, db: Session = Depends(get_db)):
    """
    Force a specific image as the candidate for a post and run it through the
    mismatch guard (e.g. the wolf for the red-fox post). Returns the verdict and
    the human-readable reason. Read-only: nothing is stored.
    """
    post = _get_post(db, post_id)
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    if not img.processed or not img.embedding():
        raise HTTPException(status_code=409, detail="Image has not been processed yet")
    try:
        sim = cosine_similarity(post.embedding(), img.embedding())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    known = sorted({i.subject for i in db.query(Image).filter(Image.processed.is_(True)) if i.subject})
    res = evaluate(_post_text(post), img.subject, img.category, img.confidence, sim,
                   settings.SIMILARITY_THRESHOLD, settings.CONFIDENCE_THRESHOLD, known)
    return GuardCheckOut(post_id=post.id, image_id=img.id, filename=img.filename, subject=img.subject,
                         similarity_score=round(sim, 4), similarity_threshold=settings.SIMILARITY_THRESHOLD,
                         guard_decision=res.decision, guard_reason=res.reason)
