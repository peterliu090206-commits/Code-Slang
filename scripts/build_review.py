#!/usr/bin/env python3
"""Build docs/data/review_queue.json for docs/review.html (T05).

Static manifest of review state: every spec row plus pending/approved file
presence plus conflict flags (blocked word that still has an image).
Regenerate after every approve/reject/remove-image (review_move.py does this
automatically) and before opening review.html.

Usage:
    py -3 scripts/build_review.py
"""

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS_JSON = ROOT / "scraper" / "image_specs.json"
BLOCKLIST_JSON = ROOT / "scraper" / "blocklist_manual.json"
IMAGES_DIR = ROOT / "docs" / "data" / "images"
PENDING_DIR = ROOT / "docs" / "data" / "images_pending"
OUT = ROOT / "docs" / "data" / "review_queue.json"


def main():
    with open(SPECS_JSON, encoding="utf-8") as f:
        specs = json.load(f)
    try:
        with open(BLOCKLIST_JSON, encoding="utf-8") as f:
            blocked = {str(w).lower() for w in json.load(f).get("words", [])}
    except FileNotFoundError:
        blocked = set()

    rows = []
    for s in specs:
        slug = s["slug"]
        pending = (PENDING_DIR / f"{slug}.png").is_file()
        approved = (IMAGES_DIR / f"{slug}.png").is_file()
        is_blocked = s.get("status") == "blocked" or s["word"].lower() in blocked
        rows.append({
            "word": s["word"],
            "slug": slug,
            "strategy": s["strategy"],
            "subject": s.get("subject", ""),
            "palette": s.get("palette", ""),
            "safety": s.get("safety", ""),
            "status": s.get("status", ""),
            "skip_image": bool(s.get("skip_image")),
            "pending": pending,
            "approved": approved,
            "needs_revision": s.get("status") == "needs-revision",
            "rejected_count": len(s.get("rejected_prompts") or []),
            # Blocked word that still ships an image = must remove.
            "conflict": bool(is_blocked and approved),
        })
    rows.sort(key=lambda r: (0 if r["pending"] else 1 if r["needs_revision"] else 2, r["word"].lower()))
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "counts": {
            "total": len(rows),
            "pending": sum(1 for r in rows if r["pending"]),
            "approved": sum(1 for r in rows if r["approved"]),
            "skipped": sum(1 for r in rows if r["skip_image"]),
            "conflicts": sum(1 for r in rows if r["conflict"]),
            "needs_revision": sum(1 for r in rows if r["needs_revision"]),
        },
        "entries": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {OUT} ({len(rows)} rows, {payload['counts']['pending']} pending, "
          f"{payload['counts']['conflicts']} conflicts)")
    return len(rows)


if __name__ == "__main__":
    sys.exit(main())
