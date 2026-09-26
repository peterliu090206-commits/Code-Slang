#!/usr/bin/env python3
"""Localhost review helper (T05). Moves staged images after human review.

Static hosting cannot write files, so docs/review.html renders copy-paste
commands and the human runs them here. NEVER expose this as a web endpoint.

Usage:
    py -3 scripts/review_move.py approve <slug>       # pending -> images/, spec approved
    py -3 scripts/review_move.py reject <slug>        # delete pending, spec needs-revision (never censors)
    py -3 scripts/review_move.py remove-image <slug>  # delete images/<slug>.png (e.g. blocked word with image)
    py -3 scripts/review_move.py status               # read-only overview (safe to run anytime)
    py -3 scripts/review_move.py apply-batch review_decisions.json  # execute a FAB export
    py -3 scripts/review_move.py export-revision <slug> [--out DIR]  # JSON+MD packet for manual LLM revision
    py -3 scripts/review_move.py revise <slug> --subject S --palette P  # apply new prompt, requeue
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS_JSON = ROOT / "scraper" / "image_specs.json"
BLOCKLIST_JSON = ROOT / "scraper" / "blocklist_manual.json"
IMAGES_DIR = ROOT / "docs" / "data" / "images"
PENDING_DIR = ROOT / "docs" / "data" / "images_pending"
RUNS_LOG = ROOT / "scraper" / "image_runs.jsonl"


def load_specs():
    with open(SPECS_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_specs(specs):
    with open(SPECS_JSON, "w", encoding="utf-8") as f:
        json.dump(specs, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_blocklist():
    with open(BLOCKLIST_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_blocklist(words):
    with open(BLOCKLIST_JSON, "w", encoding="utf-8") as f:
        json.dump({"words": words}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def log_run(entry):
    RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def find_spec(specs, slug):
    slug = slug.lower()
    for s in specs:
        if s["slug"].lower() == slug:
            return s
    return None


def rebuild_manifest():
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_review
    return build_review.main()


def cmd_status():
    specs = load_specs()
    pending = sorted(p.stem for p in PENDING_DIR.glob("*.png") if p.stat().st_size > 0)
    approved = sorted(IMAGES_DIR.glob("*.png"), key=lambda p: p.name)
    print(f"specs={len(specs)} pending={len(pending)} approved={len(approved)}")
    for s in specs:
        if s.get("status") == "needs-revision":
            n = len(s.get("rejected_prompts") or [])
            print(f"  {s['word']} [{s['strategy']}/needs-revision] -> revise ({n} negative examples)")
            continue
        if s.get("skip_image") or s.get("status") == "blocked":
            continue
        slug = s["slug"]
        state = "approved" if (IMAGES_DIR / f"{slug}.png").exists() else \
                "staged" if (PENDING_DIR / f"{slug}.png").exists() else "missing"
        print(f"  {s['word']} [{s['strategy']}/{s['status']}] -> {state}")
    return 0


def cmd_approve(slug, rebuild=True):
    specs = load_specs()
    spec = find_spec(specs, slug)
    if spec is None:
        print(f"no spec row for slug {slug!r}")
        return 1
    if spec.get("skip_image") or spec.get("status") == "blocked":
        print(f"refusing to approve {spec['word']!r}: status={spec['status']} skip={spec['skip_image']} (unblock first)")
        return 1
    src = PENDING_DIR / f"{spec['slug']}.png"
    if not (src.is_file() and src.stat().st_size > 0):
        print(f"no staged image for {spec['word']!r} ({src.name} missing)")
        return 1
    blocked = {str(w).lower() for w in load_blocklist().get("words", [])}
    if spec["word"].lower() in blocked:
        print(f"refusing to approve {spec['word']!r}: on the manual blocklist (remove it there first)")
        return 1
    dest = IMAGES_DIR / f"{spec['slug']}.png"
    if dest.exists():
        print(f"overwriting existing {dest.name}")
    size = src.stat().st_size
    src.replace(dest)
    spec["status"] = "approved"
    save_specs(specs)
    log_run({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "word": spec["word"],
             "slug": spec["slug"], "strategy": spec["strategy"],
             "outcome": "approved", "bytes": dest.stat().st_size})
    if rebuild:
        manifest = rebuild_manifest()
        print(f"approved {spec['word']!r} ({size} bytes -> {dest.name}); manifest rebuilt ({manifest} rows)")
    else:
        print(f"approved {spec['word']!r} ({size} bytes -> {dest.name})")
    return 0


def last_ok_run(slug):
    """Most recent successful generation for a slug (the pixels just judged)."""
    try:
        with open(RUNS_LOG, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return None
    slug = slug.lower()
    for r in reversed(rows):
        if str(r.get("slug", "")).lower() == slug and r.get("outcome") == "ok":
            return r
    return None


def snapshot_rejected(spec, reason):
    """Append the failed generation as a negative example on the spec row."""
    run = last_ok_run(spec["slug"])
    hist = spec.get("rejected_prompts")
    if not isinstance(hist, list):
        hist = []
        spec["rejected_prompts"] = hist
    if run is None:
        print(f"warning: no logged generation for {spec['word']!r}; history left empty")
        return False
    entry = {"positive": run.get("positive", ""), "seed": run.get("seed"),
             "ckpt": run.get("ckpt"), "preset": run.get("preset"),
             "prompt_id": run.get("prompt_id"), "ts": run.get("ts"),
             "reason": reason}
    if any(isinstance(h, dict) and h.get("prompt_id") == entry["prompt_id"] for h in hist):
        print(f"history already holds prompt {entry['prompt_id']} for {spec['word']!r}")
        return True
    hist.append(entry)
    return True


def cmd_reject(slug, reason="manual review", rebuild=True):
    specs = load_specs()
    spec = find_spec(specs, slug)
    if spec is None:
        print(f"no spec row for slug {slug!r}")
        return 1
    src = PENDING_DIR / f"{spec['slug']}.png"
    if src.exists():
        size = src.stat().st_size
        src.unlink()
        print(f"deleted staged {src.name} ({size} bytes)")
    else:
        print(f"no staged image for {spec['word']!r} (spec history still updated)")
    snapshot_rejected(spec, reason)
    # Bad image, fine word: needs-revision stays out of the queue without
    # censoring the word page. Reject NEVER touches the blocklist.
    spec["status"] = "needs-revision"
    spec["skip_image"] = True
    save_specs(specs)
    log_run({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "word": spec["word"],
             "slug": spec["slug"], "strategy": spec["strategy"],
             "outcome": f"rejected: {reason}", "bytes": 0})
    if rebuild:
        manifest = rebuild_manifest()
        print(f"rejected {spec['word']!r} (needs-revision); manifest rebuilt ({manifest} rows)")
    else:
        print(f"rejected {spec['word']!r} (needs-revision)")
    return 0


def cmd_remove_image(slug, rebuild=True):
    """Delete an approved image (conflict case: blocked word with image)."""
    specs = load_specs()
    spec = find_spec(specs, slug)
    name = f"{spec['slug']}.png" if spec else f"{slug.lower()}.png"
    removed = []
    for d in (IMAGES_DIR, PENDING_DIR):
        p = d / name
        if p.exists():
            size = p.stat().st_size
            p.unlink()
            removed.append(f"{d.name}/{name} ({size} bytes)")
    if not removed:
        print(f"no image found for {slug!r}")
        return 1
    word = spec["word"] if spec else slug
    log_run({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "word": word,
             "slug": name[:-4], "strategy": spec["strategy"] if spec else "",
             "outcome": "image removed (conflict cleanup)", "bytes": 0})
    if rebuild:
        rebuild_manifest()
    print(f"removed: {', '.join(removed)}")
    return 0


def cmd_apply_batch(path):
    """Execute a FAB-exported decisions file: {"approved": [...], "rejected": [...], "remove_image": [...]}."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    approved = list(data.get("approved", []))
    rejected = list(data.get("rejected", []))
    removed = list(data.get("remove_image", []))
    print(f"batch: {len(approved)} approve, {len(rejected)} reject, {len(removed)} remove")
    failed = []
    for slug in approved:
        if cmd_approve(slug, rebuild=False) != 0:
            failed.append(f"approve:{slug}")
    for slug in rejected:
        if cmd_reject(slug, reason="batch review", rebuild=False) != 0:
            failed.append(f"reject:{slug}")
    for slug in removed:
        if cmd_remove_image(slug, rebuild=False) != 0:
            failed.append(f"remove-image:{slug}")
    manifest = rebuild_manifest()
    print(f"batch done: {len(approved) + len(rejected) + len(removed) - len(failed)}/"
          f"{len(approved) + len(rejected) + len(removed)} ok; manifest rebuilt ({manifest} rows)")
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    return 0


def cmd_export_revision(slug, out_dir=None):
    """Write the manual-LLM revision packet: JSON + paste-ready Markdown."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from house_style import PRESETS
    specs = load_specs()
    spec = find_spec(specs, slug)
    if spec is None:
        print(f"no spec row for slug {slug!r}")
        return 1
    hist = spec.get("rejected_prompts") or []
    if not hist:
        run = last_ok_run(spec["slug"])
        if run is not None:
            hist = [{"positive": run.get("positive", ""), "seed": run.get("seed"),
                     "ckpt": run.get("ckpt"), "preset": run.get("preset"),
                     "prompt_id": run.get("prompt_id"), "ts": run.get("ts"),
                     "reason": "exported without recorded rejection"}]
    out = Path(out_dir) if out_dir else ROOT / "scraper"
    out.mkdir(parents=True, exist_ok=True)
    packet = {
        "word": spec["word"],
        "strategy": spec["strategy"],
        "house_suffix": PRESETS.get(spec.get("style_preset") or "sticker", {}).get("suffix", ""),
        "current_subject": spec.get("subject", ""),
        "current_palette": spec.get("palette", ""),
        "negative_examples": hist,
        "brief": ("Propose a NEW subject and palette for this slang word's dictionary illustration. "
                  "Keep the same strategy and house style. One clear focal subject, no text in the image, "
                  "family-friendly. The negative examples are rejected prompts — do not repeat them."),
    }
    json_path = out / f"revision_{spec['slug']}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(packet, f, ensure_ascii=False, indent=2)
        f.write("\n")
    md = [f"# Revision brief: {spec['word']}",
          "",
          f"Strategy: {spec['strategy']} — same strategy, new prompt.",
          f"House style (append verbatim): {packet['house_suffix']}",
          "",
          "## Current (failed) subject",
          spec.get("subject", "") or "(empty)",
          "",
          "## Current palette",
          spec.get("palette", "") or "(empty)",
          "",
          "## Negative examples — do NOT repeat these prompts",
          ""]
    if hist:
        for i, h in enumerate(hist, 1):
            md.append(f"{i}. `{h.get('positive', '')}` (seed {h.get('seed')}, {h.get('reason', '')})")
    else:
        md.append("(none recorded)")
    md += ["",
           "## Task",
           packet["brief"],
           "",
           "Reply with two lines: `subject: ...` and `palette: ...`, then apply via:",
           f"`py -3 scripts/review_move.py revise {spec['slug']} --subject \"...\" --palette \"...\"`",
           ""]
    md_path = out / f"revision_{spec['slug']}.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {json_path} + {md_path} ({len(hist)} negative examples)")
    return 0


def cmd_revise(slug, subject, palette):
    """Apply a new prompt to a needs-revision row and requeue it."""
    specs = load_specs()
    spec = find_spec(specs, slug)
    if spec is None:
        print(f"no spec row for slug {slug!r}")
        return 1
    if spec.get("safety") == "red":
        print(f"refusing to revise {spec['word']!r}: safety=red (censored words stay out)")
        return 1
    if spec.get("status") not in ("needs-revision", "pending"):
        print(f"refusing to revise {spec['word']!r}: status={spec.get('status')} (only needs-revision/pending rows)")
        return 1
    if not (subject or "").strip():
        print("refusing to revise: empty subject")
        return 1
    sys.path.insert(0, str(ROOT / "scripts"))
    from house_style import build_positive
    candidate = build_positive(subject.strip(), (palette or "").strip(),
                               spec.get("style_preset") or "sticker")
    for h in spec.get("rejected_prompts") or []:
        if isinstance(h, dict) and candidate == (h.get("positive") or ""):
            print(f"refusing to revise {spec['word']!r}: identical to rejected prompt {h.get('prompt_id')}")
            return 1
    spec["subject"] = subject.strip()
    spec["palette"] = (palette or "").strip()
    spec["status"] = "pending"
    spec["skip_image"] = False
    save_specs(specs)
    log_run({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "word": spec["word"],
             "slug": spec["slug"], "strategy": spec["strategy"],
             "outcome": "revised", "bytes": 0, "positive": candidate})
    rebuild_manifest()
    print(f"revised {spec['word']!r}; requeued (missing image regenerates on next run)")
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Approve/reject staged images (localhost only).")
    p.add_argument("command", choices=["approve", "reject", "remove-image", "status", "apply-batch",
                                         "export-revision", "revise"])
    p.add_argument("slug", nargs="?", default=None)
    p.add_argument("--reason", default="manual review")
    p.add_argument("--subject", default=None, help="revise: new subject text.")
    p.add_argument("--palette", default="", help="revise: new palette text.")
    p.add_argument("--out", default=None, help="export-revision: output dir (default scraper/).")
    return p.parse_args(argv)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = parse_args(argv)
    if args.command == "status":
        return cmd_status()
    if not args.slug:
        print(f"{args.command} requires a slug")
        return 1
    if args.command == "approve":
        return cmd_approve(args.slug)
    if args.command == "reject":
        return cmd_reject(args.slug, args.reason)
    if args.command == "remove-image":
        return cmd_remove_image(args.slug)
    if args.command == "apply-batch":
        if not args.slug:
            print("apply-batch requires a decisions JSON path")
            return 1
        return cmd_apply_batch(args.slug)
    if args.command == "export-revision":
        return cmd_export_revision(args.slug, args.out)
    if args.command == "revise":
        if not args.slug or not args.subject:
            print("revise requires a slug and --subject")
            return 1
        return cmd_revise(args.slug, args.subject, args.palette)
    return 1


if __name__ == "__main__":
    sys.exit(main())
