#!/usr/bin/env python3
"""Run the T01 house-style probe matrix (txt2img only, never img2img).

Reads scraper/probe_specs.json, builds prompts via scripts/house_style.py,
and queues one ComfyUI job per (probe x candidate) with a fixed seed so
candidates are comparable. Outputs go to docs/data/probes/ — NEVER to
docs/data/images/ (ticket verification requirement).

Usage:
    py -3 scripts/probe_house_style.py --dry-run
    py -3 scripts/probe_house_style.py --candidate baseline --limit 1
    py -3 scripts/probe_house_style.py --candidate baseline
    py -3 scripts/probe_house_style.py --candidate B --ckpt some_finetune.safetensors --force
"""

import argparse
import json
import sys
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
    PROBE_SEED,
    SAMPLER,
    SCHEDULER,
    STEPS,
    build_negative,
    build_positive,
    ckpt_for,
)

PROBES_JSON = ROOT / "scraper" / "probe_specs.json"
PROBES_DIR = ROOT / "docs" / "data" / "probes"


def load_probes():
    with open(PROBES_JSON, encoding="utf-8") as f:
        return json.load(f)


def probe_filename(slug, candidate):
    return f"{slug}__{candidate}.png"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Run the T01 probe matrix.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print prompts/workflows, queue nothing (no server needed).")
    p.add_argument("--candidate", default="baseline",
                   help="Ckpt candidate key from house_style.CANDIDATE_CKPTS (default baseline).")
    p.add_argument("--ckpt", default=None,
                   help="Explicit checkpoint file, overrides the candidate key.")
    p.add_argument("--preset-override", default=None,
                   help="Force one preset for all probes (e.g. render3d, comic) to test gated presets.")
    p.add_argument("--limit", type=int, default=None, help="Only run first N probes.")
    p.add_argument("--force", action="store_true", help="Regenerate even if probe PNG exists.")
    p.add_argument("--seed", type=int, default=PROBE_SEED, help="Fixed seed (default 42).")
    p.add_argument("--server", default=DEFAULT_SERVER)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--steps", type=int, default=STEPS)
    p.add_argument("--cfg", type=float, default=CFG)
    p.add_argument("--sampler", default=SAMPLER)
    p.add_argument("--scheduler", default=SCHEDULER)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    spec = load_probes()
    probes = spec["probes"]
    if args.limit is not None:
        probes = probes[: args.limit]

    ckpt = args.ckpt or ckpt_for("sticker", args.candidate)
    print(f"candidate={args.candidate} ckpt={ckpt} seed={args.seed} probes={len(probes)}")

    jobs = []
    for probe in probes:
        preset = args.preset_override or probe["style_preset"]
        positive = build_positive(probe["subject"], probe["palette"], preset)
        negative = build_negative(DEFAULT_NEGATIVE, preset,
                                  probe.get("negative_extra", ""))
        dest = PROBES_DIR / probe_filename(probe["slug"], args.candidate)
        jobs.append((probe, preset, positive, negative, dest))

    if args.dry_run:
        for probe, preset, positive, negative, dest in jobs:
            exists = "exists" if dest.exists() else "missing"
            print(f"--- {probe['word']} [{probe['strategy']}/{preset}] -> {dest.name} ({exists})")
            print(f"  +: {positive}")
            print(f"  -: {negative[:160]}")
        # Show one full workflow JSON to prove the pipeline builds offline.
        probe, preset, positive, negative, _dest = jobs[0]
        wf = build_txt2img_workflow(
            positive=positive, negative=negative,
            width=1024, height=1024, filename_prefix="probe",
            ckpt_name=ckpt, seed=args.seed, steps=args.steps,
            cfg=args.cfg, sampler_name=args.sampler,
            scheduler=args.scheduler,
        )
        print("--- sample workflow (first probe):")
        print(json.dumps(wf, indent=2))
        return 0

    failed = []
    for i, (probe, preset, positive, negative, dest) in enumerate(jobs, 1):
        if dest.exists() and not args.force:
            print(f"[{i}/{len(jobs)}] skip {dest.name} (exists, use --force)")
            continue
        print(f"[{i}/{len(jobs)}] {probe['word']} [{probe['strategy']}/{preset}]")
        print(f"  +: {positive[:160]}")
        try:
            workflow = build_txt2img_workflow(
                positive=positive, negative=negative,
                width=1024, height=1024,
                filename_prefix=f"probe_{probe['slug']}",
                ckpt_name=ckpt, seed=args.seed, steps=args.steps,
                cfg=args.cfg, sampler_name=args.sampler,
                scheduler=args.scheduler,
            )
            res = queue_prompt(workflow, args.server)
            prompt_id = res["prompt_id"]
            print(f"  queued {prompt_id} seed={args.seed}")
            entry = wait_completed(prompt_id, args.server, args.timeout)
            img = download_first_image(entry, args.server, dest)
            print(f"  OK {dest.name} ({dest.stat().st_size} bytes) from {img['filename']}")
        except Exception as e:
            print(f"  FAILED {probe['word']}: {e}")
            failed.append(probe["word"])
    print(f"done: {len(jobs) - len(failed)}/{len(jobs)} ok")
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
