# T04 — Pilot batch (dry-run + first real images)

## Objective
Prove the T03 runner end-to-end on a tiny pilot before the full ~177-image
run. Local one-off; speed irrelevant; resume-safety matters.

## Scope
- Inputs: T01 locked preset, T02 reviewed specs, T03 runner, local ComfyUI
  on `http://127.0.0.1:8188`.
- Outputs land ONLY in `docs/data/images_pending/`.

## Steps
1. `py -3 scripts/generate_from_specs.py --dry-run --batch-size 5` — inspect
   prompts; confirm typographic/blocked excluded, definition text absent.
2. `... --limit 1` — one real image; check 1024×1024 PNG, no text/watermark,
   style matches T01 winner.
3. `... --batch-size 5` — five-image pilot across strategies (pick via
   `--offset` to cover literal/persona/situational/symbolic/template).
4. Confirm resume: re-run same command → `0 queued, all skipped` (unless
   `--force`). Confirm `--force` re-queues exactly the requested rows.
5. Log check: `scraper/image_runs.jsonl` has one entry per attempt with
   seed + prompt_id; re-running the logged seed reproduces the image.

## Verification
- [ ] 1 + 5 pilot PNGs in `images_pending/`, none in `images/`.
- [ ] Re-run without `--force` queues nothing.
- [ ] No `docs/data/memes/` writes during pilot (`git status` clean there).
- [ ] Pilot images eyeballed at 132px — readable, no slur text, no real faces.

## Done when
Pilot approved by human; T05 review UI has real pending images to work with;
T06 full run unblocked.
