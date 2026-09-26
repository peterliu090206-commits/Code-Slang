# T01 Results — House-style lock

## Locked winner (T03 hardcodes this)
- **Preset:** `sticker` (single house preset for all strategies)
- **Checkpoint:** `dreamshaper_xl_alpha2.safetensors` (baseline; `CANDIDATE_CKPTS["baseline"]`)
- **Suffix:** `flat bold vector sticker, thick outline, solid background, no text, no watermark, family-friendly`
- **Steps/CFG/sampler:** `25 / 7.0 / euler`, scheduler `normal`
- **Size:** `1024x1024` (1:1, matches `.word-art` tile)
- **Seed policy:** fixed `42` for probes; random per word for batch (T06), logged to `image_runs.jsonl`
- **Negative:** `comfyUI.DEFAULT_NEGATIVE` (now includes `photorealistic, real person, celebrity likeness` per T01 step 6 — see `scripts/comfyUI.py`) + preset/row extras via `house_style.build_negative()` (deduped)
- **Prompt formula:** `{subject}, {palette}, {suffix}` — definition text never enters the prompt

## Gated (not adopted)
- `render3d` / `comic` presets are defined in `scripts/house_style.py` but **gated**: persona/situational probes must clearly beat sticker before use. Runner supports `--preset-override render3d|comic` for that test. Default stays sticker.

## Probe matrix
`scraper/probe_specs.json` — 8 probes, seed 42, all strategies covered, zero blocklisted words (checked against `scraper/blocklist_manual.json`):

| # | Word | Strategy | Safety note |
|---|---|---|---|
| 1 | touch grass | literal | — |
| 2 | caught in 4K | literal | — |
| 3 | sigma | persona | — |
| 4 | baddie | persona | **safety probe** (blocklisted-adjacent): must render family-friendly, non-sexualized; reject anything suggestive |
| 5 | ghost | situational | — |
| 6 | only in Ohio | template-recreation | text description only, never copied pixels |
| 7 | sus | symbolic | — |
| 8 | L | symbolic | — |

## How to run (needs ComfyUI on 127.0.0.1:8188)
```
py -3 scripts/probe_house_style.py --dry-run            # no server needed
py -3 scripts/probe_house_style.py --candidate baseline # 8 probes, seed 42
py -3 scripts/probe_house_style.py --candidate B --ckpt <finetune>.safetensors --force
py -3 scripts/probe_house_style.py --preset-override render3d --limit 2  # gated-preset test
```
Outputs: `docs/data/probes/<slug>__<candidate>.png` (never `docs/data/images/`).

## Status / caveat
- ~~ComfyUI server was down~~ Update 2026-09-26: server found at
  `C:\Users\peter\Documents\comfy\ComfyUI` (.venv Python 3.12.6, RTX 4060
  Laptop 8GB) and started on port 8188. Baseline ckpt
  `dreamshaper_xl_alpha2.safetensors` confirmed present alongside
  `sd_xl_base_1.0.safetensors` (possible future candidate B).

## QA verdict — 8/8 baseline probes generated 2026-09-26 (all seed 42)
`py -3 scripts/probe_house_style.py --candidate baseline` → `done: 8/8 ok`,
all in `docs/data/probes/*__baseline.png` (866–1693 KB each), nothing
written to `docs/data/images/` or `docs/data/memes/`.

| Probe | Strategy | Verdict | Note |
|---|---|---|---|
| touch grass | literal | **pass** | Hand reaching toward lawn; clean absurdist literalization, no text |
| caught in 4K | literal | **pass w/ note** | Drifted from "character in viewfinder" to camera emblem itself — still on-concept and on-palette, but T02 literal subjects should name the single focal object explicitly |
| sigma | persona | **pass** | Lone-wolf mascot, confident stance; strongest of the set |
| baddie | persona | **pass (safety)** | Family-friendly, non-sexualized; safety probe clears — persona women render safely under this preset |
| ghost | situational | **pass** | Cute ghost at retro computer; phone became PC setup but vignette reads; single clear subject |
| only in Ohio | template-recreation | **pass** | Original surreal suburb, no text, no meme copy — text-description-only method works |
| sus | symbolic | **pass** | Hooded side-eye icon in red/white; canonical sticker case |
| L | symbolic | **pass w/ note** | Bold letter emblem, but glyph reads closer to blocky "b/D" than "L" at full size — acceptable at 132px; T02 letter-emblem subjects should add "clearly legible letterform" |

House-style call: **sticker preset confirmed for all strategies.** Rendering
is consistent (thick outline + solid/light background + die-cut edge shows
up unprompted — a bonus brand marker), zero rendered text across all 8,
zero photoreal faces, family-friendly throughout. No evidence yet that
gated `render3d`/`comic` would beat sticker — persona and situational both
pass as sticker, so the gate stays closed unless T06 batches show weakness.
- Ticket verification: second half (judging pixels) now done — see table.

## Files added/changed in T01
- New `scripts/house_style.py` — preset lock, `LOCKED`, `build_positive/build_negative/ckpt_for`
- New `scraper/probe_specs.json` — 8 probes
- New `scripts/probe_house_style.py` — matrix runner (txt2img only)
- Edit `scripts/comfyUI.py` — safety delta in `DEFAULT_NEGATIVE`
