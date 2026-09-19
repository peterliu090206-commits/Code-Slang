# T06 — Full run (~177 images) + tracking

## Objective
Generate everything missing, in small resumable batches, approving
as-you-go. Local one-off; batching exists for tracking, not speed.

## Scope
- Run: `scripts/generate_from_specs.py` with `--batch-size 5..10`.
- Track: `scraper/image_runs.jsonl` + spec `status` fields.
- Out: `docs/data/images/<slug>.png` only via T05 approve path.

## Steps
1. Baseline: `--list-missing` → expect ~177 (179 minus 2 existing minus
   typographic/blocked from T02). Record the number.
2. Loop: run batch → review batch in `review.html` (T05) → approve/reject →
   next `--offset`. Small batches so a bad preset drift is caught early
   (fix spec row, `--force` single word, re-review).
3. Mid-run check after ~20: style consistency across strategies at 132px;
   if drift, adjust spec `subject`s (NOT the global suffix — house style is
   locked from T01).
4. Keep `git status` clean of accidents: only `images/*.png` additions via
   approve, `image_specs.json` status updates, `blocklist_manual.json`
   appends. `images_pending/` and `image_runs.jsonl` stay untracked/local.
5. Final: `--list-missing` → 0 generatable remaining. Cross-check every slang
   word has a disposition: approved PNG / `skip_image:true` / `blocked`.

## Verification
- [ ] `--list-missing` empty (excluding skipped/blocked by design).
- [ ] File count: `images/*.png` == approved count in specs.
- [ ] Random sample of 20 `word.html?w=` pages load images, no broken tiles.
- [ ] Failed words have JSONL error entries; rerun list is explicit.

## Done when
All generatable words approved into `images/`; all other words explicitly
skipped/blocked with reason. T07 cleanup unblocked.
