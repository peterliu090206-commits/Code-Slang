# T03 — Build `generate_from_specs.py`, retire old pipeline

## Objective
New txt2img-only batch runner driven by `image_specs.json`. Old
scrape-and-img2img path deprecated but not deleted.

## Scope
- New: `scripts/generate_from_specs.py`, `docs/data/images_pending/`,
  `scraper/image_runs.jsonl` (sidecar log, gitignored or untracked).
- Edit: `scripts/comfyUI.py` minimal deltas only (preset ckpt map, stronger
  global negative). NO workflow restructure (reuse `build_txt2img_workflow`).
- Touch-but-keep: `scripts/generate_missing_images.py` — add deprecation
  header + `print("deprecated…")` guard; remove from any docs/runbooks.

## Steps
1. Implement `generate_from_specs.py` flags:
   `--list-missing --dry-run --batch-size N --offset N --limit N --force
   --preset-override X --steps --cfg --seed --timeout --server`.
2. Selection logic: load specs; target =
   `not skip_image and status != blocked and (force or missing in
   docs/data/images/)`. `typographic`/blocked never queue.
3. Prompt build: `{subject}, {palette}, {PRESET_SUFFIX[style_preset]}`.
   Definition text NEVER enters the prompt. `negative =
   DEFAULT_NEGATIVE + preset negative_extra + row negative_extra`.
   Fixed 1024×1024 (`aspect 1:1`).
4. Queue via `comfyUI.build_txt2img_workflow / queue_prompt /
   wait_completed / download_first_image` → save to
   `docs/data/images_pending/<slug>.png` (NOT `images/` directly).
   Append JSONL per attempt: word, slug, strategy, preset, ckpt, seed,
   prompt_id, outcome, bytes.
5. `comfyUI.py` edits: `PRESET_CKPT` map from T01 winner, global negative +=
   `photorealistic, real person, celebrity likeness`. Keep default ckpt name
   working when flag omitted.
6. Deprecate old script: docstring banner + runtime warning; ensure nothing
   in the new path imports its Firecrawl/meme helpers or writes
   `docs/data/memes/`.

## Verification
- [ ] `--list-missing` lists only generatable rows (excludes typographic/blocked).
- [ ] `--dry-run` prints prompt + preset + ckpt per word, queues nothing.
- [ ] Old script still imports (no breakage) but warns deprecated.
- [ ] New script never calls `build_img2img_workflow` / `upload_image`
      (grep to confirm).

## Done when
T04 can run `--limit 1` end-to-end into `images_pending/` with the locked
T01 preset. No bulk run in this ticket.
