"""
Computes quality metrics on the labeled eval set (data/eval_set.json) using the
SAME ranking + guard code as the API.

Headline number (README): top-1 precision on the `specific` posts — of all posts
written about one specific photo, the share whose first suggested image was the
labeled correct one.

Usage:  python scripts/eval.py                  # print results
        python scripts/eval.py --update-readme   # also rewrite the results block in README.md
Run after run_batch.py and load_posts.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database import SessionLocal
from app.evaluation import compute_rankings, load_eval_set, score


def pct(t):
    n, d = t
    return f"{n}/{d} = {n / d:.2%}" if d else "n/a"


def readme_block(res):
    from datetime import date
    return (
        "<!-- EVAL:START (auto-written by `python scripts/eval.py --update-readme`) -->\n"
        f"Measured {date.today().isoformat()} · similarity threshold {settings.SIMILARITY_THRESHOLD} · "
        f"confidence threshold {settings.CONFIDENCE_THRESHOLD} · embeddings `{settings.EMBEDDING_BACKEND}` · "
        f"vision `{'mock JSON' if settings.USE_MOCK_VISION else 'live Gemini'}` (see Vision tagging below)\n\n"
        "| Metric | Result |\n|---|---|\n"
        f"| **Top-1 precision** (strict; 18 posts about one specific photo) | **{pct(res['top1_strict'])}** |\n"
        f"| Top-1 incl. `also_acceptable` near-duplicates | {pct(res['top1_lenient'])} |\n"
        f"| Species-level top-1 (18 specific + 12 concept posts, incl. \"Vulpes vulpes\") | {pct(res['species_level'])} |\n"
        f"| Wrong-subject suggestions (guard misses) | {res['wrong_subject_suggestions']} |\n"
        f"| \"No confident match\" correct, unrelated posts | {pct(res['no_match'])} |\n"
        f"| \"No confident match\" correct, hard cases (subject absent from library) | {pct(res['hard_no_match'])} |\n"
        f"| Coverage (positive posts that received a suggestion) | {pct(res['coverage'])} |\n"
        f"| Raw rank-1 precision before the guard (for reference) | {pct(res['raw_top1_strict'])} |\n"
        "<!-- EVAL:END -->"
    )


def update_readme(res):
    import re
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")
    text = open(path, encoding="utf-8").read()
    new, n = re.subn(r"<!-- EVAL:START.*?<!-- EVAL:END -->", lambda m: readme_block(res), text, flags=re.S)
    if n == 0:
        sys.exit("README.md has no EVAL:START/EVAL:END markers")
    open(path, "w", encoding="utf-8").write(new)
    print("README.md results block updated.")


def main():
    db = SessionLocal()
    try:
        res = score(compute_rankings(db, load_eval_set()), settings.SIMILARITY_THRESHOLD, settings.CONFIDENCE_THRESHOLD)
    finally:
        db.close()

    print(f"similarity_threshold={settings.SIMILARITY_THRESHOLD}  confidence_threshold={settings.CONFIDENCE_THRESHOLD}\n")
    print(f"{'Kind':<14}{'Post':<50}{'Suggested':<14}{'Expected':<14}OK")
    print("-" * 98)
    for r in res["rows"]:
        print(f"{r['kind']:<14}{r['title'][:48]:<50}{str(r['chosen']):<14}{str(r['expected']):<14}{'YES' if r['ok'] else 'NO'}")
        if not r["ok"] and r.get("reason"):
            print(f"{'':<14}  -> {r['reason'][:90]}")
    print("-" * 98)
    print(f"Top-1 precision (strict, specific posts):   {pct(res['top1_strict'])}   <-- headline")
    print(f"Top-1 precision (incl. also_acceptable):    {pct(res['top1_lenient'])}")
    print(f"Species-level top-1 (specific + concept):   {pct(res['species_level'])}")
    print(f"Wrong-subject suggestions (guard misses):   {res['wrong_subject_suggestions']}")
    print(f"'No confident match' correct (unrelated):   {pct(res['no_match'])}")
    print(f"'No confident match' correct (hard, absent subject): {pct(res['hard_no_match'])}")
    print(f"Coverage (posts that got a suggestion):     {pct(res['coverage'])}")
    print(f"[for reference] raw rank-1 before guard:    {pct(res['raw_top1_strict'])}")
    if "--update-readme" in sys.argv:
        update_readme(res)


if __name__ == "__main__":
    main()
