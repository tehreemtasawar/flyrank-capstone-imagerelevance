"""
Sweeps SIMILARITY_THRESHOLD over the labeled eval set so the threshold is
chosen from data, not a feeling. Prints, per threshold: strict top-1 precision,
wrong-subject suggestions, false accepts on no-match posts, and coverage.

Pick the lowest threshold with 0 false accepts on the no-match posts that keeps
precision/coverage high, put it in .env, then re-run scripts/eval.py.

Usage:  python scripts/tune_threshold.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database import SessionLocal
from app.evaluation import compute_rankings, load_eval_set, score


def main():
    db = SessionLocal()
    try:
        rankings = compute_rankings(db, load_eval_set())
    finally:
        db.close()

    top = [r["ranked"][0]["similarity_score"] for r in rankings if r["ranked"]]
    print(f"similarity range over all posts' best image: {min(top):.3f} .. {max(top):.3f}\n")
    print(f"{'thresh':>7} {'top1 strict':>12} {'species':>9} {'wrong-subj':>11} {'false-accept':>13} {'no-match ok':>12} {'coverage':>10}")
    lo, hi = int(min(top) * 100) - 2, int(max(top) * 100) + 3
    for t in [x / 100 for x in range(max(lo, 1), min(hi, 100))]:
        r = score(rankings, t, settings.CONFIDENCE_THRESHOLD)
        s, sp, nm, cv = r["top1_strict"], r["species_level"], r["no_match"], r["coverage"]
        mark = "  <-- current" if abs(t - settings.SIMILARITY_THRESHOLD) < 1e-9 else ""
        print(f"{t:>7.2f} {s[0]:>5}/{s[1]:<6} {sp[0]:>4}/{sp[1]:<4} {r['wrong_subject_suggestions']:>11} "
              f"{r['false_accepts']:>13} {nm[0]:>6}/{nm[1]:<5} {cv[0]:>5}/{cv[1]:<4}{mark}")


if __name__ == "__main__":
    main()
