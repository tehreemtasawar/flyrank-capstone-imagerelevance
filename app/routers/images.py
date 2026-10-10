from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.batch_jobs import create_job, run_job
from app.database import get_db
from app.models import BatchJob, Image
from app.schemas import BatchJobOut, ImageOut
from app.serializers import image_out

router = APIRouter(tags=["images"])


@router.post("/images/batch-process", response_model=BatchJobOut, status_code=202)
def batch_process(background: BackgroundTasks, response: Response, db: Session = Depends(get_db)):
    """
    Starts the vision + embedding batch job IN THE BACKGROUND and returns
    immediately with a job id (poll GET /jobs/{id}). Idempotent: if a job is
    already queued/running, that job is returned instead of starting another.
    """
    job, created = create_job(db)
    if created:
        background.add_task(run_job, job.id)
    else:
        response.status_code = 200
    return job


@router.get("/jobs", response_model=List[BatchJobOut])
def list_jobs(db: Session = Depends(get_db)):
    return db.query(BatchJob).order_by(BatchJob.id.desc()).limit(50).all()


@router.get("/jobs/{job_id}", response_model=BatchJobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(BatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/images", response_model=List[ImageOut])
def list_images(flagged: Optional[bool] = None, db: Session = Depends(get_db)):
    q = db.query(Image)
    if flagged is not None:
        q = q.filter(Image.flagged_low_confidence.is_(flagged))
    return [image_out(i) for i in q.order_by(Image.filename).all()]


@router.get("/images/{image_id}", response_model=ImageOut)
def get_image(image_id: int, db: Session = Depends(get_db)):
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    return image_out(img)
