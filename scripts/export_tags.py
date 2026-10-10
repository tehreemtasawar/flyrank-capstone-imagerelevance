"""
Shows where each image's tags/confidence came from, and optionally exports the
database's tags back into data/mock_vision/*.json so the mock path reproduces
exactly what is in the DB (e.g. after re-tagging an image with live Gemini).

Usage:
  python scripts/export_tags.py fox_08.jpg wolf_08.jpg          # inspect DB vs mock file
  python scripts/export_tags.py fox_08.jpg wolf_08.jpg --write  # overwrite mock JSON from DB
  python scripts/export_tags.py --all                           # inspect every image
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    init_db()
    db = SessionLocal()
    try:
        q = db.query(Image).order_by(Image.filename)
        imgs = q.all() if "--all" in sys.argv else q.filter(Image.filename.in_(args)).all()
        if not imgs:
            sys.exit("No matching images. Pass filenames (fox_08.jpg) or --all.")
        print(f"{'file':<12}{'DB conf':>8}  {'DB source':<22}{'mock-file conf':>15}  in-sync  flagged")
        for i in imgs:
            mp = os.path.join(ROOT, settings.MOCK_VISION_DIR, i.filename.rsplit(".", 1)[0] + ".json")
            mock = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else None
            in_sync = bool(mock) and mock["confidence"] == i.confidence and mock["caption"] == i.caption
            print(f"{i.filename:<12}{i.confidence!s:>8}  {(i.vision_model or '?'):<22}{(mock['confidence'] if mock else '-')!s:>15}  "
                  f"{'yes' if in_sync else 'NO':<8} {'LOW-CONF' if i.flagged_low_confidence else ''}")
            if write:
                out = {"subject": i.subject, "category": i.category, "attributes": i.attributes(),
                       "caption": i.caption, "confidence": i.confidence}
                json.dump(out, open(mp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
                print(f"   -> wrote {mp}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
