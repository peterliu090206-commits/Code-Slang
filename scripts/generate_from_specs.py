#!/usr/bin/env python3
"""Generate images from scraper/image_specs.json (T03, taxonomy pipeline).

Txt2img ONLY — never img2img, never scraped pixels, never writes to
docs/data/memes/. Prompts come exclusively from the curated spec rows
(subject + palette + house-style preset suffix); definition text is never
loaded and can never leak into a prompt.

Outputs stage in docs/data/images_pending/<slug>.png for human review
(T05); nothing is written directly to docs/data/images/.

Usage:
    py -3 scripts/generate_from_specs.py --list-missing
    py -3 scripts/generate_from_specs.py --dry-run --batch-size 5
    py -3 scripts/generate_from_specs.py --limit 1
    py -3 scripts/generate_from_specs.py --batch-size 5
    py -3 scripts/generate_from_specs.py --batch-size 10 --offset 5 --force
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from comfyUI import (  # noqa: E402
    DEFAULT_NEGATIVE,
    DEFAULT_SERVER,
    build_txt2img_workflow,
    download_first_image,
    queue_prompt,
    wait_completed,
)
from house_style import (  # noqa: E402
    CFG,
    SAMPLER,
    SCHEDULER,
    STEPS,
    build_negative,
    build_positive,
    ckpt_for,
)

SPECS_JSON = ROOT / "scraper" / "image_specs.json"
IMAGES_DIR = ROOT / "docs" / "data" / "images"
PENDING_DIR = ROOT / "docs" / "data" / "images_pending"
RUNS_LOG = ROOT / "scraper" / "image_runs.jsonl"


def load_specs():
    with open(SPECS_JSON, encoding="utf-8") as f:
        return json.load(f)


def is_done(slug):
    dest = IMAGES_DIR / f"{slug}.png"
    return dest.is_file() and dest.stat().st_size > 0


def is_staged(slug):
    """Already generated and awaiting review — regenerating would burn a
    run and orphan the staged file's JSONL seed record."""
    dest = PENDING_DIR / f"{slug}.png"
    return dest.is_file() and dest.stat().st_size > 0


def select_targets(specs, force, slugs=None):
    """Generatable rows only: typographic/skipped and blocked never queue.
    Without --force, words with an approved image OR a staged pending image
    are skipped, so no term is ever generated twice (stats explain why)."""
    wanted = None
    if slugs:
        wanted = {s.strip().lower() for s in slugs.split(",") if s.strip()}
    targets, stats = [], {"blocked_skip": 0, "done_skip": 0, "staged_skip": 0}
    for s in specs:
        if s.get("skip_image") or s.get("status") == "blocked":
            stats["blocked_skip"] += 1
            continue
        if wanted is not None and s["slug"].lower() not in wanted:
            continue
        if not force:
            if is_done(s["slug"]):
                stats["done_skip"] += 1
                continue
            if is_staged(s["slug"]):
                stats["staged_skip"] += 1
                continue
        targets.append(s)
    if wanted is not None:
        generatable = {s["slug"].lower() for s in specs if not s.get("skip_image")}
        missing = sorted(w for w in wanted if w not in generatable)
        if missing:
            print(f"warning: --slugs with no generatable spec row: {', '.join(missing)}")
    return targets, stats


def log_run(entry):
    RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Generate images from image_specs.json.")
    p.add_argument("--list-missing", action="store_true", help="Print generatable targets and exit.")
    p.add_argument("--dry-run", action="store_true", help="Print prompts, queue nothing (no server needed).")
    p.add_argument("--batch-size", type=int, default=5, help="Max words per run.")
    p.add_argument("--offset", type=int, default=0, help="Skip first N targets.")
    p.add_argument("--limit", type=int, default=None, help="Cap words this run (overrides batch-size if smaller).")
    p.add_argument("--force", action="store_true", help="Regenerate even if image exists or is staged.")
    p.add_argument("--slugs", default=None, help="Comma-separated slugs to target (e.g. aura,ghost); still honors skip/blocked/staged guards.")
    p.add_argument("--preset-override", default=None, help="Force one preset (sticker/render3d/comic).")
    p.add_argument("--ckpt", default=None, help="Explicit checkpoint file, overrides the preset candidate.")
    p.add_argument("--seed", type=int, default=None, help="Base seed; per-word seed = base + index (random if omitted).")
    p.add_argument("--steps", type=int, default=STEPS)
    p.add_argument("--cfg", type=float, default=CFG)
    p.add_argument("--sampler", default=SAMPLER)
    p.add_argument("--scheduler", default=SCHEDULER)
    p.add_argument("--server", default=DEFAULT_SERVER)
    p.add_argument("--timeout", type=int, default=600)
    return p.parse_args(argv)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = parse_args(argv)
    specs = load_specs()
    print(f"{len(specs)} spec rows, {IMAGES_DIR} as image dir, {PENDING_DIR} as staging dir")

    targets, stats = select_targets(specs, args.force, args.slugs)
    print(f"{len(targets)} generatable targets (typographic/blocked/done excluded; "
          f"skipped blocked/typographic={stats['blocked_skip']}, "
          f"done={stats['done_skip']}, staged={stats['staged_skip']})")

    if args.list_missing or args.dry_run:
        preview = targets[args.offset:]
        if args.dry_run:
            n = args.batch_size
            if args.limit is not None:
                n = min(n, args.limit)
            preview = preview[:n]
        for s in preview:
            preset = args.preset_override or s["style_preset"]
            if args.dry_run:
                positive = build_positive(s["subject"], s["palette"], preset)
                print(f"  {s['word']} [{s['strategy']}/{preset}] -> {s['slug']}.png")
                print(f"    +: {positive[:160]}")
            else:
                print(f"  {s['word']} -> {s['slug']}.png")
        return 0

    batch = targets[args.offset:]
    n = args.batch_size
    if args.limit is not None:
        n = min(n, args.limit)
    batch = batch[:n]
    if not batch:
        print("nothing to do")
        return 0

    base_seed = args.seed if args.seed is not None else random.randint(1, 2**31 - 1)
    print(f"base_seed={base_seed}")

    failed = []
    for i, s in enumerate(batch, 1):
        preset = args.preset_override or s["style_preset"]
        ckpt = args.ckpt or ckpt_for(preset)
        positive = build_positive(s["subject"], s["palette"], preset)
        negative = build_negative(DEFAULT_NEGATIVE, preset, s.get("negative_extra", ""))
        seed = base_seed + (args.offset + i - 1)
        dest = PENDING_DIR / f"{s['slug']}.png"
        print(f"[{i}/{len(batch)}] {s['word']} [{s['strategy']}/{preset}] -> {dest.name}")
        print(f"  prompt: {positive[:160]}")
        try:
            workflow = build_txt2img_workflow(
                positive=positive, negative=negative,
                width=1024, height=1024,
                filename_prefix=s["slug"],
                ckpt_name=ckpt, seed=seed, steps=args.steps,
                cfg=args.cfg, sampler_name=args.sampler,
                scheduler=args.scheduler,
            )
            res = queue_prompt(workflow, args.server)
            prompt_id = res["prompt_id"]
            print(f"  queued {prompt_id} seed={seed} ckpt={ckpt}")
            entry = wait_completed(prompt_id, args.server, args.timeout)
            img = download_first_image(entry, args.server, dest)
            size = dest.stat().st_size
            print(f"  OK {dest.name} ({size} bytes) from {img['filename']}")
            log_run({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "word": s["word"],
                     "slug": s["slug"], "strategy": s["strategy"], "preset": preset,
                     "ckpt": ckpt, "seed": seed, "prompt_id": prompt_id,
                     "outcome": "ok", "bytes": size,
                     "positive": positive, "negative": negative})
        except Exception as e:
            print(f"  FAILED {s['word']}: {e}")
            log_run({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "word": s["word"],
                     "slug": s["slug"], "strategy": s["strategy"], "preset": preset,
                     "ckpt": ckpt, "seed": seed, "prompt_id": None,
                     "outcome": f"failed: {e}", "bytes": 0})
            failed.append(s["word"])

    print(f"done: {len(batch) - len(failed)}/{len(batch)} ok")
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
