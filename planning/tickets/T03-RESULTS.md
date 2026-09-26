# T03 Results — `generate_from_specs.py` live 2026-09-26

- New `scripts/generate_from_specs.py`: spec-driven txt2img-only runner.
  Selection = `not skip_image and status != blocked and (force or missing
  in images/)`. Flags: `--list-missing --dry-run --batch-size --offset
  --limit --force --preset-override --ckpt --seed --steps --cfg --sampler
  --scheduler --server --timeout`. Prompts via `house_style` (subject +
  palette + sticker suffix); `slang.json`/definitions never loaded.
  Per-word seed = base + index (random base unless `--seed`). Every attempt
  appended to `scraper/image_runs.jsonl` (word/slug/strategy/preset/ckpt/
  seed/prompt_id/outcome/bytes/full prompts).
- `scripts/generate_missing_images.py`: deprecated, not deleted — module
  docstring banner + `DeprecationWarning` + printed WARNING in `main()`.
  Still imports cleanly. Only references are planning docs + itself.
- `scripts/comfyUI.py` step-5 edits: already landed in T01 (safety delta in
  `DEFAULT_NEGATIVE`; ckpt map lives in `house_style.CANDIDATE_CKPTS`).
  No workflow changes.
- `.gitignore`: `docs/data/images_pending/` + `scraper/image_runs.jsonl`
  (staging never committed; confirmed absent from `git status`).
- Ticket verification: `--list-missing` → 155 generatable (156 minus done
  `and_i_oop`); `--dry-run --batch-size 2` → exactly 2 rows with prompt +
  preset (fixed: dry-run previously ignored batch-size); old script warns on
  run; grep confirms new path has no img2img/upload/Firecrawl/memes calls or
  writes (docstring "never" lines only); live `--limit 1` → `ate.png`
  (1.4 MB) staged in `images_pending/` + JSONL `ok` entry. First staged
  image QAs clean (gold-star medal, no text).
- T04 unblocked: `py -3 scripts/generate_from_specs.py --batch-size 5`.
