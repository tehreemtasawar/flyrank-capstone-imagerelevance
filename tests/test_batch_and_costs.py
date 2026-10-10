from app.batch_jobs import create_job, process_images, run_job
from app.config import settings
from app.models import BatchJob, CostLog, Image


def test_batch_endpoint_returns_202_and_job_completes(client, processed, db):
    assert processed["status"] in ("queued", "running", "completed")
    job = client.get(f"/jobs/{processed['id']}").json()
    assert job["status"] == "completed" and job["processed"] == 4 and job["total"] == 4


def test_every_image_gets_schema_valid_tags(client, processed):
    imgs = client.get("/images").json()
    assert len(imgs) == 4 and all(i["processed"] and i["subject"] and i["caption"] for i in imgs)


def test_low_confidence_image_is_flagged(client, processed):
    flagged = client.get("/images", params={"flagged": True}).json()
    assert [i["filename"] for i in flagged] == ["dog_01.jpg"]


def test_rerun_is_idempotent(client, processed, db):
    n_before = db.query(CostLog).count()
    job2 = client.post("/images/batch-process").json()
    assert client.get(f"/jobs/{job2['id']}").json()["skipped"] == 4
    assert db.query(CostLog).count() == n_before  # no new AI calls for finished images


def test_duplicate_trigger_while_running_returns_same_job(db):
    j1, c1 = create_job(db)
    j2, c2 = create_job(db)
    assert c1 and not c2 and j1.id == j2.id


def test_cost_logged_per_call_for_vision_and_embedding(processed, db):
    rows = db.query(CostLog).all()
    assert sum(r.call_type == "vision" for r in rows) == 4
    assert sum(r.call_type == "embedding" for r in rows) == 4
    assert all(r.model_name and r.ref_table == "images" and r.ref_id for r in rows)


def test_invalid_model_output_is_flagged_and_job_reports_errors(client, clean, db):
    (clean / "mock" / "fox_02.json").write_text("{broken")
    job = client.post("/images/batch-process").json()
    j = client.get(f"/jobs/{job['id']}").json()
    assert j["status"] == "completed_with_errors" and j["failed"] == 1 and j["processed"] == 3
    bad = db.query(Image).filter_by(filename="fox_02.jpg").one()
    assert bad.flagged_low_confidence and not bad.processed and bad.processing_error


def test_failed_image_is_retried_on_next_run(client, clean, db):
    good = (clean / "mock" / "fox_02.json").read_text()
    (clean / "mock" / "fox_02.json").write_text("{broken")
    client.post("/images/batch-process")
    (clean / "mock" / "fox_02.json").write_text(good)
    job = client.post("/images/batch-process").json()
    assert client.get(f"/jobs/{job['id']}").json()["processed"] == 1


def test_budget_guard_stops_live_calls(db, monkeypatch):
    monkeypatch.setattr(settings, "USE_MOCK_VISION", False)
    monkeypatch.setattr(settings, "DAILY_VISION_CALL_LIMIT", 0)
    job, _ = create_job(db)
    run_job(job.id)
    db.expire_all()
    j = db.get(BatchJob, job.id)
    assert j.status == "budget_exhausted" and "limit" in j.error


def test_embedding_failure_does_not_waste_vision_call(db, monkeypatch):
    from app.embedding_service import EmbeddingError

    def boom(t):
        raise EmbeddingError("down")
    monkeypatch.setattr("app.batch_jobs.get_embedding", boom)
    s = process_images(db)
    assert s["failed"] == 4 and s["processed"] == 0
    assert db.query(Image).filter(Image.caption.isnot(None)).count() == 4  # vision results kept
    monkeypatch.undo()


def test_reprocess_wipes_and_redoes(db):
    process_images(db)
    s = process_images(db, reprocess=["fox_01.jpg"])
    assert s["processed"] == 1 and s["skipped_already_done"] == 3


def test_unknown_job_404(client):
    assert client.get("/jobs/999").status_code == 404


def test_abandoned_running_job_does_not_block_new_jobs(db):
    import datetime
    old = BatchJob(status="running", started_at=datetime.datetime.utcnow() - datetime.timedelta(hours=1))
    db.add(old); db.commit()
    job, created = create_job(db)
    db.refresh(old)
    assert created and job.id != old.id and old.status == "failed" and "abandoned" in old.error


def test_invalid_api_key_stops_job_immediately(db, monkeypatch):
    from app.embedding_service import EmbeddingError
    calls = []
    def bad_key(t):
        calls.append(1)
        raise EmbeddingError("Invalid Gemini API key - fix GEMINI_API_KEY in .env")
    monkeypatch.setattr("app.batch_jobs.get_embedding", bad_key)
    job, _ = create_job(db)
    run_job(job.id)
    db.expire_all()
    j = db.get(BatchJob, job.id)
    assert j.status == "failed" and "API key" in j.error and len(calls) == 1
