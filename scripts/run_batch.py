"""
Runs the vision + embedding batch job directly (no server needed).

Usage:
  python scripts/run_batch.py                       # process everything not yet done
  python scripts/run_batch.py --reprocess a.jpg b.jpg   # wipe + redo specific images
  python scripts/run_batch.py --reprocess-all       # wipe + redo every image (uses vision quota!)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.batch_jobs import create_job, run_job
from app.config import settings
from app.database import SessionLocal, init_db
from app.models import BatchJob

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reprocess", nargs="*", default=[])
    ap.add_argument("--reprocess-all", action="store_true")
    args = ap.parse_args()

    init_db()
    db = SessionLocal()
    try:
        reprocess = args.reprocess
        if args.reprocess_all:
            reprocess = sorted(f for f in os.listdir(settings.IMAGES_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png")))
        job, created = create_job(db)
        if not created:
            print(f"Job {job.id} already {job.status}; refusing to start a duplicate.")
            sys.exit(1)
        job_id = job.id
    finally:
        db.close()

    run_job(job_id, reprocess=reprocess)

    db = SessionLocal()
    try:
        j = db.get(BatchJob, job_id)
        print(f"Batch job {j.id}: {j.status}")
        print(f"  total: {j.total}\n  processed: {j.processed}\n  flagged_low_confidence: {j.flagged_low_confidence}"
              f"\n  failed: {j.failed}\n  skipped_already_done: {j.skipped}")
        if j.error:
            print(f"  note: {j.error}")
    finally:
        db.close()
