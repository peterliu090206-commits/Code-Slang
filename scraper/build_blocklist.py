#!/usr/bin/env python3
"""Build censored-word blocklist: manual list + optional better-profanity suggestions.

The blocklist is manual by default. better-profanity is used at scrape time
only to *suggest* candidates (printed to stdout) or, with --auto, to merge
its hits into the output.

Usage:
    py -3 scraper/build_blocklist.py            # manual list -> docs/data/blocklist.json
    py -3 scraper/build_blocklist.py --auto     # manual + better-profanity hits
    py -3 scraper/build_blocklist.py --check "some phrase"

Inputs:
    scraper/slang.json                 # list[{word, definition, forms}]
    scraper/blocklist_manual.json      # {"words": [...]} curated via localhost card checkboxes

Output:
    docs/data/blocklist.json           # {"words": [...], generated_at, method, count}
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
SLANG_JSON = BASE / "slang.json"
MANUAL_JSON = BASE / "blocklist_manual.json"
OUT_JSON = ROOT / "docs" / "data" / "blocklist.json"


def get_profanity():
    try:
        from better_profanity import profanity
    except ImportError:
        raise ImportError(
            "better-profanity not installed. Run: py -3 -m pip install better-profanity"
        )
    profanity.load_censor_words()
    return profanity


def is_flagged(profanity, word: str, forms=None) -> bool:
    """Flag if the word or any of its forms contains profanity."""
    candidates = [word or ""]
    for f in forms or []:
        candidates.append(f)
    for c in candidates:
        if c and profanity.contains_profanity(c):
            return True
    return False


def load_manual_words() -> list[str]:
    if not MANUAL_JSON.exists():
        return []
    try:
        data = json.loads(MANUAL_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):
        words = data.get("words", [])
    elif isinstance(data, list):
        words = data
    else:
        words = []
    return [str(w) for w in words if str(w).strip()]


def build(include_auto: bool = False) -> tuple[dict, list[str]]:
    profanity = get_profanity()
    slang = json.loads(SLANG_JSON.read_text(encoding="utf-8"))
    if isinstance(slang, dict) and "entries" in slang:
        slang = slang["entries"]

    auto = []
    for item in slang:
        word = item.get("word", "")
        forms = item.get("forms", [])
        if word and is_flagged(profanity, word, forms):
            auto.append(word)

    manual = load_manual_words()

    # Merge case-insensitively, keeping the slang.json casing for display.
    # Manual list is authoritative; better-profanity hits are only merged with --auto.
    seen_lower = set()
    merged = []
    for w in manual + (auto if include_auto else []):
        key = w.lower()
        if key not in seen_lower:
            seen_lower.add(key)
            merged.append(w)
    merged.sort(key=lambda s: s.lower())

    suggestions = sorted(set(auto) - seen_lower, key=str.lower)

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "method": "manual" + (" + better-profanity --auto" if include_auto else ""),
        "count": len(merged),
        "words": merged,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload, suggestions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=str, default=None, help="Check a single phrase with better-profanity")
    parser.add_argument("--auto", action="store_true", help="Merge better-profanity hits into the output (default: manual only)")
    args = parser.parse_args(argv)

    if args.check is not None:
        profanity = get_profanity()
        flagged = bool(profanity.contains_profanity(args.check))
        print(f"{args.check!r} -> {'FLAGGED' if flagged else 'clean'}")
        return 0

    if not SLANG_JSON.exists():
        print(f"Missing {SLANG_JSON}", file=sys.stderr)
        return 1
    payload, suggestions = build(include_auto=args.auto)
    print(f"wrote {OUT_JSON} ({payload['count']} words)")
    for w in payload["words"]:
        print(f"  - {w}")
    if suggestions:
        print("better-profanity suggestions (not included, add to blocklist_manual.json if wanted):")
        for w in suggestions:
            print(f"  ? {w}")
    if not payload["words"]:
        print("Blocklist is empty. Tick card checkboxes on localhost, then save via the Blacklist button.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
