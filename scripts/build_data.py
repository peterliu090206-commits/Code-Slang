#!/usr/bin/env python3
"""Merge slang.json + slang_usage.json + slang_similar.json into docs/data/combined.json.

Usage:
    py -3 scripts/build_data.py
"""
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRAPER = ROOT / "scraper"
OUT = ROOT / "docs" / "data" / "combined.json"


def load(name):
    with open(SCRAPER / name, encoding="utf-8") as f:
        return json.load(f)


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


if __name__ == "__main__":
    main()
