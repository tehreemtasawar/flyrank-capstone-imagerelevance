"""
One-step demo seed: migrate DB -> tag all images (live Gemini or mock JSON,
per USE_MOCK_VISION) -> load + embed posts. Safe to re-run.

NOTE: this never touches data/images, data/posts.json or data/eval_set.json.

Usage: python scripts/seed.py
"""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
for script in ("run_batch.py", "load_posts.py"):
    print(f"\n=== {script} ===")
    rc = subprocess.call([sys.executable, os.path.join(here, script)])
    if rc != 0:
        sys.exit(rc)
print("\nSeed complete. Next: python scripts/eval.py")
