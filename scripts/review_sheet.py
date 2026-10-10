"""
Writes reports/tag_review.html: every image next to the tags the pipeline stored
for it. OPEN IT AND LOOK. This is the 2-minute check that catches stale or
misaligned tags (renamed files, wrong mock JSON) before they silently wreck
matching quality.

Usage: python scripts/review_sheet.py   (then open reports/tag_review.html)
"""
import base64
import html
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image as PILImage

from app.database import SessionLocal, init_db
from app.models import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def thumb(path):
    im = PILImage.open(path).convert("RGB")
    im.thumbnail((360, 360))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def main():
    init_db()
    db = SessionLocal()
    cards = []
    try:
        for i in db.query(Image).order_by(Image.filename).all():
            flag = " &#9873; LOW CONFIDENCE" if i.flagged_low_confidence else ""
            cards.append(
                f"<div class=c><img src='{thumb(os.path.join(ROOT, i.path))}'><b>{html.escape(i.filename)}</b>{flag}<br>"
                f"<i>{html.escape(i.subject or '-')}</i> ({i.confidence})<br>{html.escape(i.caption or '(untagged)')}<br>"
                f"<small>{html.escape(', '.join(i.attributes()))}</small></div>"
            )
    finally:
        db.close()
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    out = os.path.join(ROOT, "reports", "tag_review.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write("<meta charset=utf-8><style>body{font:14px sans-serif;display:flex;flex-wrap:wrap;gap:12px;padding:12px}"
                ".c{width:370px;border:1px solid #ccc;padding:6px}img{width:100%}small{color:#666}</style>" + "".join(cards))
    print(f"Wrote {out} ({len(cards)} images). Check each caption matches its photo.")


if __name__ == "__main__":
    main()
