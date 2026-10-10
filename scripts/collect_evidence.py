"""
Runs all six acceptance probes against YOUR database (in-process, no server
needed) and writes reports/evidence_run.md in paste-ready form for EVIDENCE.md.

Run after seed.py:   python scripts/collect_evidence.py
"""
import contextlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import func

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import CostLog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = []


def section(title, body, lang=""):
    out.append(f"### {title}\n```{lang}\n{body.rstrip()}\n```\n")


def show(r):
    return f"HTTP {r.status_code}\n" + json.dumps(r.json(), indent=2)


def pid(client, needle):
    for p in client.get("/posts").json():
        if needle.lower() in p["title"].lower():
            return p["id"]
    raise SystemExit(f"post containing '{needle}' not loaded; run scripts/load_posts.py")


def main():
    with TestClient(app) as c:
        # PROBE 1
        imgs = c.get("/images").json()
        flagged = [i for i in imgs if i["flagged_low_confidence"]]
        jobs = c.get("/jobs").json()
        section("Probe 1 - batch job, schema-valid tags, low-confidence flagged",
                f"images processed: {sum(i['processed'] for i in imgs)}/{len(imgs)}\n"
                f"latest batch jobs: {json.dumps(jobs[:3], indent=1)}\n"
                f"flagged low-confidence ({len(flagged)}):\n" +
                "\n".join(f"  {i['filename']}: {i['subject']} conf={i['confidence']}" for i in flagged) +
                "\n\nsample tag record:\n" + json.dumps(c.get(f"/images/{imgs[0]['id']}").json(), indent=2), "text")

        # PROBE 2
        fox = pid(c, "Snow Winters")
        r = c.get(f"/posts/{fox}/images?limit=8")
        section(f"Probe 2 - GET /posts/{fox}/images (fox post; fox first, wolf/dog lower)", show(r), "json")

        # PROBE 3
        wolf_id = next(i["id"] for i in imgs if i["filename"] == "wolf_02.jpg")
        r = c.get(f"/posts/{fox}/check/{wolf_id}")
        section(f"Probe 3 - force wolf_02.jpg as candidate for the fox post: GET /posts/{fox}/check/{wolf_id}", show(r), "json")
        husky_id = next(i["id"] for i in imgs if i["filename"] == "dog_09.jpg")
        wolfpost = pid(c, "Snarl")
        r = c.get(f"/posts/{wolfpost}/check/{husky_id}")
        section(f"Probe 3b - look-alike: the husky (dog_09.jpg) forced onto a wolf post", show(r), "json")

        # PROBE 4
        for needle in ("Programming Languages", "Giant Pandas"):
            p = pid(c, needle)
            section(f"Probe 4 - no suitable image: GET /posts/{p}/images ({needle})", show(c.get(f"/posts/{p}/images?limit=3")), "json")

        # review workflow
        s = c.get("/suggestions").json()
        if s:
            sid = next((x["id"] for x in s if x["image_id"]), s[0]["id"])
            r = c.post(f"/suggestions/{sid}/review", json={"action": "approve"})
            section(f"Review workflow - POST /suggestions/{sid}/review {{approve}}", show(r), "json")

    # PROBE 5
    import runpy
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        runpy.run_path(os.path.join(ROOT, "scripts", "eval.py"), run_name="__main__")
    section("Probe 5 - python scripts/eval.py", buf.getvalue(), "text")

    # PROBE 6
    db = SessionLocal()
    try:
        rows = db.query(CostLog.call_type, CostLog.model_name, CostLog.success, func.count(), func.sum(CostLog.estimated_cost_usd)).group_by(
            CostLog.call_type, CostLog.model_name, CostLog.success).all()
        last = db.query(CostLog).order_by(CostLog.id.desc()).limit(5).all()
        section("Probe 6 - cost log (every AI call attributed)",
                "call_type  model                      success  calls  cost_usd\n" +
                "\n".join(f"{a:<10} {b:<26} {str(s):<8} {n:<6} {float(t or 0):.4f}" for a, b, s, n, t in rows) +
                "\n\nlast 5 rows:\n" + "\n".join(f"  #{r.id} {r.call_type} {r.ref_table}:{r.ref_id} {r.model_name} ${r.estimated_cost_usd}" for r in last), "text")
    finally:
        db.close()

    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    path = os.path.join(ROOT, "reports", "evidence_run.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Evidence run\nsimilarity_threshold={settings.SIMILARITY_THRESHOLD} confidence_threshold={settings.CONFIDENCE_THRESHOLD} "
                f"mock_vision={settings.USE_MOCK_VISION} embedding_backend={settings.EMBEDDING_BACKEND}\n\n" + "\n".join(out))
    print(f"Wrote {path} - paste the sections into EVIDENCE.md")


if __name__ == "__main__":
    main()
