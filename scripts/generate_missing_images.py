#!/usr/bin/env python3
"""Generate images for slang words missing them (meme-seeded img2img).

Scans scraper/slang.json, maps each word to docs/data/images/<slug>.png
(slug = lowercase, spaces -> underscores, other unsafe chars stripped).

For each word this script fetches the first "{word} meme" image result via
the Firecrawl search API (sources=["images"]), caches it under
docs/data/memes/<slug>.<ext> for reuse, uploads it to the ComfyUI input
dir, and queues an SDXL img2img job via comfyUI.py that restyles the meme
with prompt = "<word>, <definition>, <style suffix>" at low denoise.
If the meme search/download/upload fails, it falls back to plain txt2img
so one bad word never blocks the batch.

Usage:
    py -3.12 scripts/generate_missing_images.py --list-missing
    py -3.12 scripts/generate_missing_images.py --dry-run --batch-size 5
    py -3.12 scripts/generate_missing_images.py --batch-size 5
    py -3.12 scripts/generate_missing_images.py --limit 1 --steps 10 --width 512 --height 512
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
from pathlib import Path

from comfyUI import (
    DEFAULT_CKPT,
    DEFAULT_NEGATIVE,
    DEFAULT_SERVER,
    build_img2img_workflow,
    build_txt2img_workflow,
    download_first_image,
    queue_prompt,
    upload_image,
    wait_completed,
)

ROOT = Path(__file__).resolve().parents[1]
SLANG_JSON = ROOT / "scraper" / "slang.json"
IMAGES_DIR = ROOT / "docs" / "data" / "images"
MEMES_DIR = ROOT / "docs" / "data" / "memes"

FIRECRAWL_API_BASE = "https://api.firecrawl.dev"
ENV_KEY = "FIRECRAWL_API_KEY"
MEME_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

STYLE_SUFFIX = "vibrant cartoony illustration, bold colors, playful stylized art, no text, no watermark, family-friendly"


def slugify(word):
    slug = word.lower().replace(" ", "_")
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "untitled"


def load_words():
    with open(SLANG_JSON, encoding="utf-8") as f:
        return json.load(f)


def find_missing(words):
    missing = []
    for item in words:
        word = item.get("word", "")
        slug = slugify(word)
        if not (IMAGES_DIR / f"{slug}.png").exists():
            missing.append((word, slug, item.get("definition", "")))
    return missing


def build_prompt(word, definition):
    base = f"{word}, {definition}".strip().rstrip(".")
    return f"{base}, {STYLE_SUFFIX}"


def firecrawl_image_search(api_key, query, timeout=60, max_attempts=4, limit=10):
    """Search Firecrawl (v2, sources=['images']). Returns raw image result dicts.

    limit is deliberately >1: top hotlinks (e.g. Instagram lookaside) often
    refuse direct download, so callers try candidates in order until one
    yields real image bytes.
    """
    body = {"query": query, "limit": limit, "sources": ["images"]}
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    }
    backoff = 15
    for attempt in range(1, max_attempts + 1):
        req = urllib.request.Request(
            f"{FIRECRAWL_API_BASE}/v2/search", data=payload, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                if attempt >= max_attempts:
                    raise RuntimeError(f"Firecrawl rate-limited (HTTP 429) after {attempt} attempt(s)")
                wait = backoff
                try:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    if retry_after and str(retry_after).isdigit():
                        wait = max(backoff, int(retry_after))
                except Exception:
                    pass
                print(f"      rate-limited; retrying in {wait}s (attempt {attempt}/{max_attempts})...")
                time.sleep(wait)
                backoff *= 2
                continue
            raise
        if not result.get("success"):
            raise RuntimeError(result.get("message") or result)
        data = result.get("data") or {}
        if isinstance(data, dict):
            images = data.get("images") or []
            if isinstance(images, list) and images:
                return images
        return []


def parse_image_result(raw):
    """Extract (direct_image_url, page_url) from a Firecrawl images result.

    Field names vary by version, so accept imageUrl/image_url/src/image
    for the file and url/pageUrl/source for the hosting page. If only a
    page url is present and it already points at an image file, use it.
    """
    if not isinstance(raw, dict):
        return "", ""
    image_url = (
        raw.get("imageUrl") or raw.get("image_url") or raw.get("src") or raw.get("image") or ""
    ).strip()
    page_url = (
        raw.get("url") or raw.get("pageUrl") or raw.get("page_url")
        or raw.get("source") or raw.get("sourceUrl") or ""
    ).strip()
    if not image_url and page_url:
        path = urllib.parse.urlparse(page_url).path.lower()
        if path.endswith(MEME_EXTS):
            image_url = page_url
    return image_url, page_url


def find_cached_meme(slug):
    for ext in MEME_EXTS:
        candidate = MEMES_DIR / f"{slug}{ext}"
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    # Fallback: any file with this stem (covers odd extensions saved earlier)
    try:
        for candidate in MEMES_DIR.glob(f"{slug}.*"):
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
    except Exception:
        pass
    return None


def ext_for_image(image_url, content_type):
    path = urllib.parse.urlparse(image_url).path.lower()
    for ext in MEME_EXTS:
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    if content_type:
        ctype = content_type.split(";")[0].strip().lower()
        if ctype in CONTENT_TYPE_EXT:
            return CONTENT_TYPE_EXT[ctype]
    return ".jpg"


def download_meme_image(image_url, slug, timeout=60):
    """Download an image URL into MEMES_DIR. Returns the saved Path."""
    req = urllib.request.Request(
        image_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SlangMemeFetcher/1.0",
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type", "") if resp.headers else ""
        if content_type and not content_type.split(";")[0].strip().lower().startswith("image/"):
            raise RuntimeError(f"not an image (Content-Type: {content_type})")
        data = resp.read()
    if len(data) < 5 * 1024:
        raise RuntimeError(f"image too small ({len(data)} bytes), likely a placeholder")
    ext = ext_for_image(image_url, content_type)
    MEMES_DIR.mkdir(parents=True, exist_ok=True)
    dest = MEMES_DIR / f"{slug}{ext}"
    dest.write_bytes(data)
    return dest


def get_meme_image(word, slug, api_key, query_template, allow_fetch=True, search_sleep=1.0, use_cache=True):
    """Return cached meme Path, fetching '{word} meme' first result if needed."""
    if use_cache:
        cached = find_cached_meme(slug)
        if cached:
            return cached, "cached"
    if not allow_fetch:
        raise RuntimeError("no cached meme and fetching disabled")
    if not api_key:
        raise RuntimeError(f"no {ENV_KEY}; set it or pass --firecrawl-key")
    query = query_template.format(word=word)
    results = firecrawl_image_search(api_key, query)
    if search_sleep:
        time.sleep(search_sleep)
    if not results:
        raise RuntimeError(f"no image results for query {query!r}")
    errors = []
    for idx, raw in enumerate(results, 1):
        image_url, _page_url = parse_image_result(raw)
        if not image_url:
            errors.append(f"#{idx}: no direct image URL")
            continue
        try:
            dest = download_meme_image(image_url, slug)
            return dest, f"fetched {query!r} (result #{idx})"
        except Exception as e:
            errors.append(f"#{idx} {image_url[:90]}: {e}")
            continue
    raise RuntimeError(f"all {len(results)} image results failed for {query!r}: {'; '.join(errors)[:400]}")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Generate images for slang words missing them.")
    p.add_argument("--list-missing", action="store_true", help="Print missing words and exit.")
    p.add_argument("--dry-run", action="store_true", help="Print what would be generated and exit.")
    p.add_argument("--batch-size", type=int, default=5, help="Max words per run.")
    p.add_argument("--offset", type=int, default=0, help="Skip first N missing words.")
    p.add_argument("--limit", type=int, default=None, help="Cap words this run (overrides batch-size if smaller).")
    p.add_argument("--force", action="store_true", help="Regenerate even if image exists.")
    p.add_argument("--server", default=DEFAULT_SERVER)
    p.add_argument("--ckpt", default=DEFAULT_CKPT)
    p.add_argument("--negative", default=DEFAULT_NEGATIVE)
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--height", type=int, default=1024)
    p.add_argument("--steps", type=int, default=25)
    p.add_argument("--cfg", type=float, default=7.0)
    p.add_argument("--sampler", default="euler")
    p.add_argument("--scheduler", default="normal")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--denoise", type=float, default=0.65, help="img2img transform strength in (0, 1] (default 0.65 strong restyle).")
    p.add_argument("--firecrawl-key", default=os.environ.get(ENV_KEY, ""), help=f"Firecrawl API key (or set {ENV_KEY}).")
    p.add_argument("--meme-query-template", default="{word} meme", help='Meme search query template; {word} is replaced (default "{word} meme").')
    p.add_argument("--no-meme-cache", action="store_true", help="Always re-download the meme instead of reusing docs/data/memes/<slug>.*.")
    p.add_argument("--no-meme-fetch", action="store_true", help="Never hit the search API; use cached memes only, else fall back to txt2img.")
    p.add_argument("--search-sleep", type=float, default=1.0, help="Seconds to wait after each Firecrawl image search (default 1.0).")
    return p.parse_args(argv)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = parse_args(argv)
    words = load_words()
    print(f"{len(words)} words in slang.json, {IMAGES_DIR} as image dir")

    if args.force:
        targets = [(i.get("word", ""), slugify(i.get("word", "")), i.get("definition", "")) for i in words]
    else:
        targets = find_missing(words)
    print(f"{len(targets)} missing images")

    if args.list_missing or args.dry_run:
        for word, slug, _ in targets[args.offset :]:
            cached = find_cached_meme(slug)
            meme = cached.name if cached else "fetch-needed"
            print(f"  {word} -> {slug}.png (meme: {meme}, denoise={args.denoise})")
        return 0

    batch = targets[args.offset :]
    n = args.batch_size
    if args.limit is not None:
        n = min(n, args.limit)
    batch = batch[:n]
    if not batch:
        print("nothing to do")
        return 0

    failed = []
    for i, (word, slug, definition) in enumerate(batch, 1):
        dest = IMAGES_DIR / f"{slug}.png"
        prompt = build_prompt(word, definition)
        print(f"[{i}/{len(batch)}] {word} -> {dest.name}")
        print(f"  prompt: {prompt[:160]}")
        # 1. Meme starter image (cached reuse by default).
        meme_path = None
        meme_status = ""
        try:
            if args.no_meme_fetch and find_cached_meme(slug) is None:
                raise RuntimeError("no cached meme and --no-meme-fetch given")
            meme_path, meme_status = get_meme_image(
                word, slug, args.firecrawl_key, args.meme_query_template,
                allow_fetch=not args.no_meme_fetch, search_sleep=args.search_sleep,
                use_cache=not args.no_meme_cache,
            )
            print(f"  meme: {meme_path.name} ({meme_status}, {meme_path.stat().st_size} bytes)")
        except Exception as e:
            print(f"  meme miss ({e}); will fall back to txt2img if img2img fails")
            meme_path = None
        # 2. Queue ComfyUI job: img2img when we have a meme, else txt2img.
        try:
            if meme_path is not None:
                try:
                    server_name = upload_image(meme_path, args.server)
                    print(f"  uploaded {meme_path.name} -> {server_name}")
                    workflow = build_img2img_workflow(
                        positive=prompt,
                        init_image=server_name,
                        negative=args.negative,
                        denoise=args.denoise,
                        filename_prefix=slug,
                        ckpt_name=args.ckpt,
                        seed=args.seed,
                        steps=args.steps,
                        cfg=args.cfg,
                        sampler_name=args.sampler,
                        scheduler=args.scheduler,
                    )
                    mode = f"img2img denoise={args.denoise}"
                except Exception as e:
                    print(f"  img2img setup failed ({e}); falling back to txt2img")
                    workflow = build_txt2img_workflow(
                        positive=prompt,
                        negative=args.negative,
                        width=args.width,
                        height=args.height,
                        filename_prefix=slug,
                        ckpt_name=args.ckpt,
                        seed=args.seed,
                        steps=args.steps,
                        cfg=args.cfg,
                        sampler_name=args.sampler,
                        scheduler=args.scheduler,
                    )
                    mode = "txt2img (fallback)"
            else:
                workflow = build_txt2img_workflow(
                    positive=prompt,
                    negative=args.negative,
                    width=args.width,
                    height=args.height,
                    filename_prefix=slug,
                    ckpt_name=args.ckpt,
                    seed=args.seed,
                    steps=args.steps,
                    cfg=args.cfg,
                    sampler_name=args.sampler,
                    scheduler=args.scheduler,
                )
                mode = "txt2img (no meme)"
            seed = workflow["5"]["inputs"]["seed"]
            res = queue_prompt(workflow, args.server)
            prompt_id = res["prompt_id"]
            print(f"  queued {prompt_id} seed={seed} mode={mode}")
            entry = wait_completed(prompt_id, args.server, args.timeout)
            img = download_first_image(entry, args.server, dest)
            print(f"  OK {dest.name} ({dest.stat().st_size} bytes) from {img['filename']}")
        except Exception as e:
            print(f"  FAILED {word}: {e}")
            failed.append(word)

    print(f"done: {len(batch) - len(failed)}/{len(batch)} ok")
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
