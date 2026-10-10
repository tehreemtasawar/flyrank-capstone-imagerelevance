"""
Evaluation logic shared by scripts/eval.py, scripts/tune_threshold.py and
scripts/collect_evidence.py, so the README number is produced by ONE code path.

Eval entry kinds (data/eval_set.json):
  specific       post written about one specific photo; `correct_image_filename`
                 is the labeled answer (+ optional `also_acceptable`).
  concept        post about a species; any image of `expected_prefix` is right
                 (species-level check, incl. "Vulpes vulpes" -> fox photos).
  no_match       unrelated post; the system must answer "no confident match".
  hard_no_match  plausible-but-absent subject (e.g. pandas, cats); same expectation,
                 reported separately because it is the guard's hardest case.
"""
import json
import os
from typing import Dict, List

from sqlalchemy.orm import Session

from app.guard import best_candidate_or_none
from app.matching import rank_images
from app.models import Image, Post

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_eval_set() -> List[dict]:
    with open(os.path.join(ROOT, "data", "eval_set.json"), encoding="utf-8") as f:
        return json.load(f)


def compute_rankings(db: Session, eval_set: List[dict]) -> List[dict]:
    """Rank once (expensive part); thresholds are applied later so sweeps are cheap."""
    imgs = db.query(Image).filter(Image.processed.is_(True)).all()
    cands = [{"image_id": i.id, "filename": i.filename, "subject": i.subject, "category": i.category,
              "confidence": i.confidence, "embedding": i.embedding()} for i in imgs]
    out = []
    for e in eval_set:
        post = db.query(Post).filter(Post.title == e["post_title"]).first()
        ranked = rank_images(post.embedding(), cands) if post else None
        out.append({"entry": e, "post": post, "ranked": ranked})
    return out


def score(rankings: List[dict], sim_th: float, conf_th: float) -> Dict:
    rows = []
    for r in rankings:
        e, post, ranked = r["entry"], r["post"], r["ranked"]
        if post is None:
            rows.append({"title": e["post_title"], "kind": e["kind"], "chosen": "POST NOT LOADED", "ok": False, "reason": ""})
            continue
        chosen_id, guard = best_candidate_or_none(f"{post.title}. {post.body}", ranked, sim_th, conf_th)
        by_id = {c["image_id"]: c for c in ranked}
        chosen = by_id[chosen_id]["filename"] if chosen_id else None
        raw_top1 = ranked[0]["filename"] if ranked else None
        kind = e["kind"]
        if kind == "specific":
            ok = chosen == e["correct_image_filename"]
            lenient = chosen in ([e["correct_image_filename"]] + e.get("also_acceptable", []))
            species_ok = chosen is not None and chosen.startswith(e["expected_prefix"] + "_")
        elif kind == "concept":
            ok = lenient = species_ok = chosen is not None and chosen.startswith(e["expected_prefix"] + "_")
        else:
            ok = lenient = species_ok = chosen is None
        rows.append({"title": e["post_title"], "kind": kind, "chosen": chosen, "raw_top1": raw_top1,
                     "expected": e.get("correct_image_filename") or e.get("expected_prefix") or "NO MATCH",
                     "ok": ok, "lenient": lenient, "species_ok": species_ok,
                     "reason": guard.reason, "sim": by_id[chosen_id]["similarity_score"] if chosen_id else (ranked[0]["similarity_score"] if ranked else None)})

    def frac(kinds, key):
        sel = [r for r in rows if r["kind"] in kinds]
        n = sum(1 for r in sel if r.get(key))
        return n, len(sel)

    spec = [r for r in rows if r["kind"] == "specific"]
    positives = [r for r in rows if r["kind"] in ("specific", "concept")]
    suggested = [r for r in positives if r["chosen"] and r["chosen"] != "POST NOT LOADED"]
    return {
        "rows": rows,
        "top1_strict": frac(("specific",), "ok"),
        "top1_lenient": frac(("specific",), "lenient"),
        "species_level": frac(("specific", "concept"), "species_ok"),
        "no_match": frac(("no_match",), "ok"),
        "hard_no_match": frac(("hard_no_match",), "ok"),
        "wrong_subject_suggestions": sum(1 for r in suggested if not r["species_ok"]),
        "false_accepts": sum(1 for r in rows if r["kind"] in ("no_match", "hard_no_match") and r["chosen"]),
        "coverage": (len(suggested), len(positives)),
        "raw_top1_strict": (sum(1 for r in spec if r.get("raw_top1") == r["expected"]), len(spec)),
    }
