"""
Background batch job: runs every unprocessed image through vision -> validation
-> embedding, with retries, progress tracking, cost logging and a budget guard.

Deliberately plain Python (no Celery/Redis): FastAPI BackgroundTasks runs it off
the request path, a `batch_jobs` row tracks progress, and the same function is
callable from scripts/run_batch.py. Swapping in a real queue later would not
touch vision_service.py, guard.py or matching.py.

Resumable by design: vision and embedding are separate stages, so if embedding
fails after a (quota-limited) vision call succeeded, the next run only repeats
the embedding. Already-processed images are skipped (idempotent re-runs).
"""
import datetime
import json
import logging
import os
import time
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.cost_tracker import PRICES_USD, live_vision_calls_today, log_cost, spend_today_usd
from app.database import SessionLocal
from app.embedding_service import EmbeddingError, get_embedding
from app.models import BatchJob, Image
from app.vision_service import classify_image

log = logging.getLogger("batch")

ACTIVE = ("queued", "running")
STALE_AFTER = datetime.timedelta(minutes=10)


def _reset_image(img: Image):
    img.subject = img.category = img.attributes_json = img.caption = None
    img.confidence = None
    img.flagged_low_confidence = False
    img.embedding_json = img.embedding_model = img.vision_model = None
    img.processed = False
    img.processing_error = None


def _budget_exceeded(db: Session) -> Optional[str]:
    if not settings.USE_MOCK_VISION:
        used = live_vision_calls_today(db)
        if used >= settings.DAILY_VISION_CALL_LIMIT:
            return f"daily live vision call limit reached ({used}/{settings.DAILY_VISION_CALL_LIMIT})"
        price = PRICES_USD.get(settings.GEMINI_VISION_MODEL, 0.0)
        if price > 0 and spend_today_usd(db) + price > settings.DAILY_BUDGET_USD:
            return f"daily budget ${settings.DAILY_BUDGET_USD:.2f} would be exceeded"
    return None


def process_images(db: Session, images_dir: str = None, job: BatchJob = None,
                   reprocess: Optional[Iterable[str]] = None) -> dict:
    images_dir = images_dir or settings.IMAGES_DIR
    if not os.path.isdir(images_dir):
        raise FileNotFoundError(f"Images directory not found: {images_dir}")

    summary = {"processed": 0, "flagged_low_confidence": 0, "failed": 0,
               "skipped_already_done": 0, "stopped_reason": None}
    reprocess = set(reprocess or [])
    files = sorted(f for f in os.listdir(images_dir) if f.lower().endswith((".jpg", ".jpeg", ".png")))
    if job:
        job.total = len(files)
        db.commit()

    def sync_job():
        if job:
            job.processed = summary["processed"]
            job.flagged_low_confidence = summary["flagged_low_confidence"]
            job.failed = summary["failed"]
            job.skipped = summary["skipped_already_done"]
            db.commit()

    for filename in files:
        path = os.path.join(images_dir, filename)
        image = db.query(Image).filter(Image.filename == filename).first()
        if image is None:
            image = Image(filename=filename, path=path)
            db.add(image)
            db.commit()
            db.refresh(image)
        if filename in reprocess:
            _reset_image(image)
            db.commit()

        if image.processed:
            summary["skipped_already_done"] += 1
            sync_job()
            continue

        # ---- stage 1: vision (skipped if an earlier run already got valid tags)
        if image.caption is None or image.confidence is None:
            reason = _budget_exceeded(db)
            if reason:
                summary["stopped_reason"] = reason
                log.warning("Batch stopped: %s", reason)
                break

            def on_call(model_name, success, note, _id=image.id):
                log_cost(db, "vision", "images", _id, model_name, success=success, note=note)

            result, error, model_name = classify_image(filename, path, on_call=on_call)
            if result is None:
                image.processing_error = error
                image.flagged_low_confidence = True  # never guess — flag instead
                db.commit()
                summary["failed"] += 1
                log.error("Vision failed for %s: %s", filename, error)
                sync_job()
                continue

            image.subject, image.category = result.subject, result.category
            image.attributes_json = json.dumps(result.attributes)
            image.caption, image.confidence = result.caption, result.confidence
            image.vision_model = model_name
            image.processing_error = None
            db.commit()
            if not settings.USE_MOCK_VISION:
                time.sleep(settings.VISION_DELAY_SECONDS)  # stay under the free tier's per-minute limit

        image.flagged_low_confidence = image.confidence < settings.CONFIDENCE_THRESHOLD

        # ---- stage 2: embedding of the caption
        try:
            embedding, embed_model = get_embedding(image.caption)
            log_cost(db, "embedding", "images", image.id, embed_model)
        except EmbeddingError as e:
            log_cost(db, "embedding", "images", image.id, settings.GEMINI_EMBEDDING_MODEL, success=False, note=str(e)[:200])
            image.processing_error = f"embedding: {e}"
            db.commit()
            if "Invalid Gemini API key" in str(e):
                raise RuntimeError(str(e))  # every remaining image would fail the same way: stop the job
            summary["failed"] += 1
            log.error("Embedding failed for %s: %s", filename, e)
            sync_job()
            continue

        image.embedding_json = json.dumps(embedding)
        image.embedding_model = embed_model
        image.processing_error = None
        image.processed = True
        db.commit()

        summary["processed"] += 1
        if image.flagged_low_confidence:
            summary["flagged_low_confidence"] += 1
        sync_job()

    return summary


# ---------------------------------------------------------------- job plumbing
def create_job(db: Session):
    """Idempotent trigger: returns (job, created). A second trigger while a job
    is queued/running returns that same job instead of starting a duplicate."""
    active = db.query(BatchJob).filter(BatchJob.status.in_(ACTIVE)).order_by(BatchJob.id.desc()).first()
    if active:
        age = datetime.datetime.utcnow() - (active.started_at or active.created_at)
        if age > STALE_AFTER:  # process was killed (Ctrl+C / crash): don't stay blocked forever
            active.status = "failed"
            active.error = "abandoned: process stopped before the job finished"
            active.finished_at = datetime.datetime.utcnow()
            db.commit()
        else:
            return active, False
    job = BatchJob(status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job, True


def run_job(job_id: int, reprocess: Optional[Iterable[str]] = None):
    """Entry point for BackgroundTasks — owns its own DB session."""
    db = SessionLocal()
    try:
        job = db.get(BatchJob, job_id)
        job.status, job.started_at = "running", datetime.datetime.utcnow()
        db.commit()
        try:
            summary = process_images(db, job=job, reprocess=reprocess)
            if summary["stopped_reason"]:
                job.status, job.error = "budget_exhausted", summary["stopped_reason"]
            elif summary["failed"]:
                job.status = "completed_with_errors"
                job.error = f"{summary['failed']} image(s) failed; re-run the job to retry them"
                log.error("ALERT: batch job %s finished with %s failures", job_id, summary["failed"])
            else:
                job.status = "completed"
        except Exception as e:  # crash of the whole job -> visible, not silent
            db.rollback()
            job = db.get(BatchJob, job_id)
            job.status, job.error = "failed", str(e)[:300]
            log.exception("ALERT: batch job %s crashed", job_id)
        job.finished_at = datetime.datetime.utcnow()
        db.commit()
    finally:
        db.close()
