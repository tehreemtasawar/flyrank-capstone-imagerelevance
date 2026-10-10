# AI Image Understanding & Content Matching Engine

FlyRank Internship · Backend Track · Capstone.

Looks at an image library, tags what is actually in each image with a vision model,
and matches the right image to the right blog post **by meaning, not filenames**.
A red-fox post gets the red-fox photo, never the wolf. When nothing is a good
enough match, it says **"no confident match"** and explains why instead of guessing.

The core of the project is the **mismatch guard** (`app/guard.py`): a safety layer
combining classifier confidence, semantic-similarity thresholds and a corpus-driven
subject check to refuse wrong pairings with a human-readable reason.

Design notes (problem, data model, API surface, layers, non-goals): see [`DESIGN.md`](DESIGN.md).

## Architecture

```
Images --(background batch job: retries, progress, cost log, budget guard)-->
   Vision model (Gemini Flash | mock JSON) --> schema validation (Pydantic)
   --> {subject, category, attributes, caption, confidence} --> images table
   --> embed(caption) ------------------------------------------> image vectors

Posts --> embed(title + body) --------------------------------> post vectors

GET /posts/{id}/images
   --> similarity ranking (cosine: image vectors x post vector)
   --> MISMATCH GUARD per candidate:
         1. metadata present?
         2. classifier confidence >= CONFIDENCE_THRESHOLD?
         3. subject check: does the post reference ANOTHER known subject
            more strongly than this image's subject?
         4. cosine similarity >= SIMILARITY_THRESHOLD?
   --> first accepted candidate  |  "No confident match" + reasons
   --> stored as a Suggestion --> Review API: approve / reject / inspect why
```

| Layer | Files |
|---|---|
| HTTP | `app/routers/` (images + jobs, posts, suggestions) · `app/main.py` |
| Logic | `app/guard.py` · `app/matching.py` · `app/vision_service.py` · `app/embedding_service.py` · `app/batch_jobs.py` · `app/cost_tracker.py` · `app/evaluation.py` |
| Data | `app/models.py` · `app/database.py` · `migrations/` (Alembic) |
| Contracts | `app/schemas.py` (vision-output schema + API schemas) |

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env            # Windows PowerShell: Copy-Item .env.example .env
                                # then add your free GEMINI_API_KEY (https://aistudio.google.com, no card)
python scripts/seed.py          # migrate DB, tag the 40 images, load + embed 37 posts
uvicorn app.main:app            # http://localhost:8000/docs
```

Then: `python scripts/eval.py` (quality numbers) and `pytest` (72 tests, no network or key needed).
The default database is SQLite (`capstone.db`, created and migrated automatically). To use Postgres, set
`DATABASE_URL` in `.env` and install a Postgres driver such as `psycopg2-binary`.

**Vision modes.** `USE_MOCK_VISION=true` (default in `.env.example`) reads pre-written tag JSON
from `data/mock_vision/`; `false` calls Gemini live. Both go through the *same* schema validation,
storage, embedding and guard code. **Embeddings are real Gemini embeddings whenever `GEMINI_API_KEY`
is set**; with no key the app falls back to a non-semantic hash embedding (plumbing only).

**A Gemini key is required to reproduce the results below.** The hash embeddings score far lower than
the 0.75 similarity threshold, so without a key most or all posts will return `NO_CONFIDENT_MATCH`.

## API

| Endpoint | What it does |
|---|---|
| `POST /images/batch-process` | Starts the vision+embedding job **in the background** → `202` + job id. Idempotent: a job already running is returned, not duplicated |
| `GET /jobs/{id}` · `GET /jobs` | Progress: status, total/processed/flagged/failed/skipped |
| `GET /images[?flagged=true]` · `GET /images/{id}` | Validated tags; low-confidence images are flagged |
| `POST /posts` · `GET /posts` · `GET /posts/{id}` | Create (validated, embedded, idempotent) / read posts |
| `GET /posts/{id}/images?limit=5` | **The core call.** Chosen image or `NO_CONFIDENT_MATCH`, plus the ranked candidates each with a guard verdict + reason |
| `GET /posts/{id}/check/{image_id}` | **Force** any image as the candidate (e.g. the wolf for the fox post) and see the guard's verdict. Read-only |
| `GET /suggestions[?review_status=]` · `GET /suggestions/{id}` | Review queue / inspect why |
| `POST /suggestions/{id}/review` `{"action":"approve"\|"reject"}` | Review workflow (idempotent; can't approve a no-match) |

Bad input → clean `422`/`404`/`409`, never a `500`.

```bash
curl localhost:8000/posts/1/images
curl localhost:8000/posts/1/check/34       # forced wolf on a fox post -> REJECT + reason
curl -X POST localhost:8000/suggestions/1/review -H 'Content-Type: application/json' -d '{"action":"approve"}'
```

## Results

<!-- EVAL:START (auto-written by `python scripts/eval.py --update-readme`) -->
Measured 2026-10-10 · similarity threshold 0.75 · confidence threshold 0.6 · embeddings `gemini` · vision `mock JSON` (see Vision tagging below)

| Metric | Result |
|---|---|
| **Top-1 precision** (strict; 18 posts about one specific photo) | **16/18 = 88.89%** |
| Top-1 incl. `also_acceptable` near-duplicates | 18/18 = 100.00% |
| Species-level top-1 (18 specific + 12 concept posts, incl. "Vulpes vulpes") | 30/30 = 100.00% |
| Wrong-subject suggestions (guard misses) | 0 |
| "No confident match" correct, unrelated posts | 5/5 = 100.00% |
| "No confident match" correct, hard cases (subject absent from library) | 2/2 = 100.00% |
| Coverage (positive posts that received a suggestion) | 30/30 = 100.00% |
| Raw rank-1 precision before the guard (for reference) | 16/18 = 88.89% |
<!-- EVAL:END -->

### How the eval set is built (and why it was rebuilt)
`data/eval_set.json` has 37 labeled posts in four tiers: **18 `specific`** posts each written
about one particular photo (one labeled correct image, optionally a second near-duplicate
that is also accepted), **12 `concept`** posts about a species (any photo of that species
is right; includes the "Vulpes vulpes" / "Canis lupus" equivalence cases), **5 `no_match`**
unrelated posts, and **2 `hard_no_match`** posts about plausible animals that are *not* in the
library (pandas, cats). Labels were assigned by looking at the photos (`scripts/review_sheet.py`),
before running the matcher.

The first version of this eval scored 1/10. That was mostly a **labeling bug, not a model bug**:
the posts did not describe any particular photo, so "fox_02 is the correct image for the
breeding-season post" was arbitrary, and several labels pointed at the wrong species entirely.
See `BUILDLOG.md`.

### Threshold tuning (`python scripts/tune_threshold.py`)
Cosine scores from `gemini-embedding-001` are compressed into a narrow high band. On the first
12 posts, unrelated tech posts scored a best-image similarity of **0.717 and 0.730**, while
correct animal posts scored **0.777 to 0.858**. A threshold of 0.12 (tuned for the non-semantic
fallback) therefore accepted a wolf photo for "Best Programming Languages in 2026";
**0.75** separates the two groups. `tune_threshold.py` sweeps the threshold over the full eval set and prints precision,
wrong-subject suggestions, false accepts and coverage per value so the choice is defended by data.

**Caveat:** the safe window is narrow. Threshold 0.74 admits one unrelated post and 0.76 drops one correct
post. On the final run, the closest unrelated post (the pandas post, best image `bear_02.jpg`) scored 0.744, only
0.006 under the 0.75 threshold, and the programming post scored 0.717. The threshold was tuned on the same
37-post set it is scored on, so the numbers are optimistic; a held-out set is the obvious next step.

**About the two "misses" in the results table:** both are near-duplicates, not wrong subjects. The golden-retriever
post got `dog_01.jpg` instead of the labeled `dog_06.jpg` (two similar golden retrievers holding a flower), and
the red-deer post got `deer_04.jpg` instead of `deer_02.jpg` (two red deer stags). The labels were fixed before
the run and I did not change them to improve the score; counting the second photo as acceptable gives 18/18.

## Mismatch guard: what it does and doesn't catch

- **Catches:** low-confidence classifications; unrelated posts (similarity); and species mix-ups
  where the post names *another subject in the library* more strongly than the image's own
  (fox post + wolf photo; "brown bear" post + polar-bear photo; "red deer" post + red-fox photo;
  "wolf" post + husky photo).
- **Subject matching** is whole-word, singularised, stopword-filtered, and compares *how many*
  words of each subject appear in the post (so a shared generic word like "red" can't hide a mismatch).
  The real bugs found while building it are written up in `BUILDLOG.md`.
- **Does not reliably catch** (honest limitation): a post about an animal that is *absent* from the
  library (e.g. pandas) when its embedding is close to a present animal (bears) and the post text names
  no known subject. Those rely on the similarity threshold alone; see the `hard_no_match` row above.
  Next step: embed each distinct subject label and require the post to be closer to the candidate's
  subject than to a generic-animal baseline.

## Limitations

- **Vision tagging is a mix of live Gemini output and hand-written JSON.** The free Gemini tier allowed about
  20 vision calls per day, so 11 of the 40 images (the 8 bears, `deer_01`, `deer_02`, `deer_04`) were tagged by
  live Gemini and 29 by Claude writing JSON from each photo, loaded through the mock path. FlyRank's Q&A (staff
  reply, Aug 6, 2026, to another intern) said that writing responses manually in Gemini chat, storing them as
  JSON and mocking the LLM call is fine, and asked for a README note. My variant differs only in which model
  wrote the JSON. Validation, storage, embeddings and guard are identical, but the tags are not independent
  model output. `BUILDLOG.md` has the history, including a stale-tag bug caused by renamed files. To tag an
  image live: `python scripts/run_batch.py --reprocess <file.jpg>` with `USE_MOCK_VISION=false`.
- The two low-confidence examples (`fox_08.jpg` 0.46, `wolf_08.jpg` 0.50) have hand-assigned confidences in
  AI-written mock JSON; live Gemini rated both 0.98 when I re-tagged them. The flagging logic is real and tested,
  but those two values are synthetic.
- Corpus is small (40 images, 5 species), so the numbers are indicative, not statistically strong.
- Embeddings are stored as JSON and compared in Python (fine at this size; use pgvector beyond a few thousand images).
- Review interface is API-only, per the brief's scope. No auth (single-tenant demo).
- Background jobs use FastAPI `BackgroundTasks` + a job table, not a distributed queue; a server restart mid-job
  leaves it `running` (re-run `POST /images/batch-process` after clearing it, or just run `scripts/run_batch.py`).

## Tests & tooling

`pytest`: 72 hermetic tests (temp DB, fake embedder): guard rules and regression tests for the historical guard
bugs, schema validation, vision retry/invalid-output handling, batch job (idempotency, flagging, per-call cost
rows, budget guard, resumability), every endpoint including 4xx paths, forced wolf-on-fox rejection,
"Vulpes vulpes" concept match, migrations vs. models.

| Script | Purpose |
|---|---|
| `scripts/seed.py` | migrate + tag images + load posts (never touches data files) |
| `scripts/review_sheet.py` | `reports/tag_review.html`: photo next to its stored tags. **Look at it** |
| `scripts/eval.py [--update-readme]` | quality metrics; writes the Results block above |
| `scripts/tune_threshold.py` | threshold sweep |
| `scripts/collect_evidence.py` | runs all six probes → `reports/evidence_run.md` for EVIDENCE.md |
| `scripts/recompute_embeddings.py` | re-embed after changing embedding model (no vision calls) |

Images: resized to 900px or less; sources are listed in `data/images/CREDITS.md`. Config: `.env.example`. License: MIT.