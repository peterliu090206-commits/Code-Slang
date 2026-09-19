#!/usr/bin/env python3
"""Merge slang.json + slang_usage.json + slang_similar.json into docs/data/combined.json.

Also bumps cache-busting versions: stamps ?v=VERSION onto local CSS/JS
references in docs/index.html + docs/word.html and injects window.__V,
which app.js/word.js append to data/image fetches.

Usage:
    py -3 scripts/build_data.py
"""
import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRAPER = ROOT / "scraper"
DOCS = ROOT / "docs"
OUT = DOCS / "data" / "combined.json"

# (html file, [(tag, file)]) — local asset references to version.
VERSIONED_ASSETS = {
    "index.html": [("link", "styles.css"), ("script", "app.js")],
    "word.html": [("link", "styles.css"), ("script", "word.js")],
}

VERSION_TAG_RE = re.compile(r"\?v=[\w.\-]+", re.IGNORECASE)
WINDOW_V_RE = re.compile(r'<script>window\.__V="[^"]*";</script>\n?')


def load(name):
    with open(SCRAPER / name, encoding="utf-8") as f:
        return json.load(f)


def stamp_versions(version: str) -> None:
    """Rewrite ?v= params + window.__V in docs HTML files (idempotent)."""
    for html_name, assets in VERSIONED_ASSETS.items():
        path = DOCS / html_name
        text = path.read_text(encoding="utf-8")
        for tag, asset in assets:
            if tag == "link":
                pat = re.compile(
                    r'(<link\b[^>]*href=")' + re.escape(asset) + r"(\?v=[\w.\-]+)?(" + '")',
                    re.IGNORECASE,
                )
            else:
                pat = re.compile(
                    r'(<script\b[^>]*src=")' + re.escape(asset) + r"(\?v=[\w.\-]+)?(" + '")',
                    re.IGNORECASE,
                )
            text, n = pat.subn(r"\g<1>" + asset + "?v=" + version + r"\g<3>", text)
            if not n:
                print(f"  warning: no {tag} {asset} reference found in {html_name}")
        # Refresh (or insert) window.__V just before the page's own script tag.
        page_js = assets[-1][1]
        text = WINDOW_V_RE.sub("", text)
        marker = f'<script src="{page_js}'
        if marker in text:
            text = text.replace(
                marker, f'<script>window.__V="{version}";</script>\n' + marker, 1
            )
        else:
            print(f"  warning: no script {page_js} tag found in {html_name}")
        path.write_text(text, encoding="utf-8")
        print(f"  stamped {html_name} (?v={version})")


def main():
    base = load("slang.json")  # list[{word, definition, forms, examples}]
    usage = load("slang_usage.json")  # {entries: [{word, uses}]}
    similar = load("slang_similar.json")  # {clusters, entries}

    uses_by_word = {e["word"]: e.get("uses", []) for e in usage.get("entries", [])}
    sim_by_word = {e["word"]: e for e in similar.get("entries", [])}

    entries = []
    for item in base:
        word = item["word"]
        sim = sim_by_word.get(word, {})
        entries.append(
            {
                "word": word,
                "definition": item.get("definition", ""),
                "forms": item.get("forms", []),
                "cluster": sim.get("cluster"),
                "examples": item.get("examples", [])[:5],
                "uses": uses_by_word.get(word, [])[:3],
                "similar": (sim.get("similar", []) or [])[:5],
                "similar_english": (sim.get("similar_english", []) or [])[:5],
            }
        )
    entries.sort(key=lambda e: e["word"].lower())

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "count": len(entries),
        "clusters": similar.get("clusters", []),
        "entries": entries,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"wrote {OUT} ({len(entries)} entries, {len(payload['clusters'])} clusters)")

    version = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    stamp_versions(version)


if __name__ == "__main__":
    main()
