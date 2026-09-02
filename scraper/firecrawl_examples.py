#!/usr/bin/env python3
"""Fetch usage examples for each slang term via the Firecrawl search API.

For every word in slang.json this script searches the web for pages that use
the term, then stores the top results under an "examples" list on each entry.

Usage:
    python firecrawl_examples.py                         # all words
    python firecrawl_examples.py --word rizz            # one word
    python firecrawl_examples.py --limit 8 --content    # 8 results incl. content

The API key is read from the FIRECRAWL_API_KEY environment variable or
passed with --api-key.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.firecrawl.dev"
DATA_FILE = "slang.json"
ENV_KEY = "FIRECRAWL_API_KEY"
SOURCE_URL_MARKERS = ("wikipedia.org/wiki/Glossary_of_20", "wikipedia.org/wiki/Glossary+of+20")


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def firecrawl_search(api_key, query, limit, with_content, timeout=60, max_attempts=4):
    """Search via Firecrawl. Returns list of {url, title, description[, content]}.

    Retries with exponential backoff when the API rate-limits us (HTTP 429).
    """
    body = {"query": query, "limit": limit}
    if with_content:
        body["scrapeOptions"] = {"formats": ["markdown"]}
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    }

    backoff = 15
    attempt = 0
    while True:
        attempt += 1
        rate_limited = None
        for version in ("v2", "v1"):
            url = f"{API_BASE}/{version}/search"
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    result = json.load(resp)
            except urllib.error.HTTPError as exc:
                if exc.code == 404 and version == "v2":
                    continue
                if exc.code == 429:
                    rate_limited = exc
                    break
                raise
            if not result.get("success"):
                raise RuntimeError(result.get("message") or result)
            return normalize_results(result)
        if rate_limited is None:
            continue
        if attempt >= max_attempts:
            raise RuntimeError(
                f"Firecrawl rate-limited (HTTP 429) after {attempt} attempt(s)"
            )
        retry_after = rate_limited.headers.get("Retry-After") if rate_limited.headers else None
        wait = backoff
        if retry_after and retry_after.isdigit():
            wait = max(backoff, int(retry_after))
        print(f"      rate-limited; retrying in {wait}s (attempt {attempt}/{max_attempts})...")
        time.sleep(wait)
        backoff *= 2


def normalize_results(result):
    entries = result.get("data") if isinstance(result, dict) else None
    raw = []
    if isinstance(entries, list):
        raw = entries
    elif isinstance(entries, dict):
        for group in ("web", "news", "results"):
            if isinstance(entries.get(group), list):
                raw.extend(entries[group])
    if not raw and isinstance(result, dict) and isinstance(result.get("results"), list):
        raw = result["results"]

    out = []
    for r in raw:
        item = {
            "url": r.get("url", "").strip(),
            "title": (r.get("title") or "").strip(),
            "description": (r.get("description") or "").strip(),
        }
        content = r.get("markdown") or r.get("content") or ""
        if content:
            item["content"] = content[:2000]
        out.append(item)
    return out


TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "igshid", "mc_eid", "mc_cid",
}


def normalize_url(url: str) -> str:
    """Canonical URL for intra-word dedup — scheme/www/fragment/tracking agnostic.

    Keeps non-tracking query params (sorted) so ?page=1 != ?page=2, but
    collapses https/http, www., default ports, trailing slash, fragment,
    case-insensitive host, and utm_*/fbclid style trackers.
    Returns "" for empty/invalid input.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception:
        return raw.lower().strip()
    # Need netloc; urlparse without scheme puts path in path — handle that
    if not parsed.netloc and parsed.path:
        # Try with dummy scheme for urls like "example.com/foo"
        parsed = urllib.parse.urlparse("https://" + raw)

    netloc = (parsed.netloc or "").lower().strip()
    # strip default ports and www.
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif netloc.endswith(":443"):
        netloc = netloc[:-4]
    # Remove userinfo if any, keep host only
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[-1]
    if not netloc:
        return ""

    path = urllib.parse.unquote(parsed.path or "/")
    # normalize path: collapse //, remove trailing slash (keep root as "")
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    if path == "/":
        path = ""

    # filter/sort query, drop tracking params
    query = ""
    if parsed.query:
        try:
            pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            kept = [(k, v) for k, v in pairs if k.lower() not in TRACKING_PARAMS]
            kept.sort(key=lambda kv: (kv[0].lower(), kv[1]))
            if kept:
                query = urllib.parse.urlencode(kept, doseq=True)
        except Exception:
            query = parsed.query

    # canonical key: netloc + path + ?query (no scheme, no fragment, host lower)
    key = netloc + path
    if query:
        key += "?" + query
    return key


def is_source_page(example):
    url = (example.get("url") or "").lower()
    return any(marker in url for marker in SOURCE_URL_MARKERS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--word", action="append", default=None,
                        help="Only annotate this word (repeatable). Defaults to all words.")
    parser.add_argument("--only-missing", action="store_true",
                        help="Only annotate words that do not already have examples.")
    parser.add_argument("--limit", type=int, default=5,
                        help="Max search results per word (default 5).")
    parser.add_argument("--content", action="store_true",
                        help="Also scrape and store markdown content for each result.")
    parser.add_argument("--data", default=DATA_FILE, help="JSON file to read/write.")
    parser.add_argument("--api-key", default=os.environ.get(ENV_KEY, ""),
                        help=f"Firecrawl API key (or set {ENV_KEY}).")
    parser.add_argument("--sleep", type=float, default=1.0,
                        help="Seconds to wait between API calls (default 1.0).")
    parser.add_argument("--query-template", default='"{word}" slang usage',
                        help="Search query template; {word} is replaced (default: '\"{word}\" slang usage').")
    args = parser.parse_args()

    if not args.api_key:
        parser.error(f"no Firecrawl API key. Set the {ENV_KEY} environment variable or pass --api-key.")

    records = load_json(args.data)
    wanted = set((w or "").strip().lower() for w in (args.word or []))

    targets = []
    for record in records:
        if args.only_missing and record.get("examples"):
            continue
        if not wanted:
            targets.append(record)
            continue
        for key in (record.get("word", ""), *record.get("forms", [])):
            if key.lower() in wanted:
                targets.append(record)
                break

    if not targets:
        print("No matching words found.")
        sys.exit(1)

    print(f"Annotating {len(targets)} of {len(records)} entries with examples...")

    updated = set()
    failures = 0
    for record in targets:
        word = record["word"]
        query = args.query_template.format(word=word)
        try:
            examples = firecrawl_search(args.api_key, query, args.limit, args.content)
        except Exception as exc:
            print(f"[error] {word}: {exc}")
            examples = []
            failures += 1

        filtered = [e for e in examples if not is_source_page(e)]
        seen = set()
        deduped = []
        for e in filtered:
            raw = (e.get("url") or "").strip()
            key = normalize_url(raw)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(e)

        record["examples"] = deduped
        updated.add(id(record))
        print(f"  {word}: {len(deduped)} example(s)")
        time.sleep(args.sleep)

    for record in records:
        if id(record) not in updated:
            record.setdefault("examples", [])

    save_json(args.data, records)
    print(f"Wrote {len(records)} entries to {args.data} "
          f"({sum(1 for r in records if r.get('examples') and isinstance(r.get('examples'), list) and r['examples'])} with examples, "
          f"{failures} failed word(s)).")


if __name__ == "__main__":
    sys.exit(main())