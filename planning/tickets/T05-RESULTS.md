# T05 Results — review queue live 2026-09-26

## Built
- `docs/review.html` + `docs/review.js` (new): localhost-gated queue grid
  (copies the `isLocalhost()` pattern from `app.js`; non-localhost gets a
  "local only" message and no commands). Sections: conflicts, pending cards
  (132px staged image, word, strategy/safety/status chips, subject, palette,
  images/-state line, copy-paste Approve/Reject commands with click-to-copy),
  approved word-links, skipped letter-fallback chips. Single GET fetch of the
  manifest; zero write capability in the page (no POST/XHR endpoint anywhere).
- `scripts/build_review.py` (new): writes `docs/data/review_queue.json`
  (179 rows, counts, `conflict` = blocked word with approved image).
  Served-200 verified over local http together with review.html/js and a
  pending PNG.
- `scripts/review_move.py` (new): `approve` (pending→images, spec approved,
  refuses blocked/skip rows and blocklisted words), `reject` (delete pending,
  spec blocked+skipped, blocklist append deduped/sorted), `remove-image`
  (conflict cleanup), `status` (read-only). Every mutation logs to
  `image_runs.jsonl` and rebuilds the manifest.
- `scripts/build_data.py`: `review.html` added to `VERSIONED_ASSETS`; verified
  stamping (`?v=` + `window.__V`) on a real run.
- `scripts/draft_specs.py`: regenerations now preserve human `approved`/
  `blocked` status + seeds (censor still wins on new blocklist entries);
  `--check` accepts `status=blocked` skips. Reject-path exposed a too-strict
  blocklist assertion — fixed to require blocked+skipped (red safety only for
  curated reds).
- `.gitignore`: `docs/data/review_queue.json`.

## Rework (censorship-style flow)
Per request, per-card Approve/Reject buttons replaced with checkboxes +
floating export, mirroring `app.js`: each pending card has a **reject**
checkbox (unchecked = approve), conflict cards have a **remove image**
checkbox (unchecked = keep), and a floating `.blacklist-fab`-styled button
bottom-right shows live counts (`Export: N approve · M reject`) and downloads
`review_decisions.json`. New `review_move.py apply-batch <file>` executes the
export (approvals → rejects → removals, one manifest rebuild, per-row failures
reported with exit 1). Batch-tested on `ate` + bogus slug (1/2 ok, graceful
failure), state restored after.

## Revision loop (no-rerun guarantee + manual LLM step)
- Spec rows carry `rejected_prompts` (inline history). `reject` snapshots the
  judged generation from JSONL, sets `needs-revision`+skip, and **never
  touches the blocklist** — bad image, fine word. `ate`/`blud` migrated:
  unblocklisted (12 words again), history backfilled from their `ok` runs.
- `export-revision <slug>` writes `scraper/revision_<slug>.json` + `.md`
  (strategy, house suffix, current subject/palette, negative examples, brief).
- `revise <slug> --subject --palette` applies the LLM output: refuses red
  words and prompts identical to a rejected one, flips to pending/unskipped.
- `--check` enforces: valid statuses, history shape, and no pending row
  repeating its own rejected positive. `draft_specs.py` regens preserve
  history + needs-revision state. Verified: identical-subject refused,
  `grape` refused, export excludes rejected words from `--list-missing`,
  review page shows the needs-revision section with export commands.

## Cycle test (on `ate`, fully restored after)
Reject → pending deleted, spec blocked+skipped, blocklist 13, manifest 15
pending. Approve → `images/ate.png`, spec approved, manifest rebuilt. Refusals
verified (`approve acoustic` → blocked; `remove-image` of missing slug → clean
error). Final state restored byte-for-byte (pending/ate.png, specs, 12-word
blocklist); `git status` clean on those paths. **No pilot image was approved
or rejected for real — all 16 pending decisions are yours.**

## Current queue state
16 pending (T03 pilot `ate` + T04 five + 5 more from a later batch run:
`bar, based, basic, bean_soup_theory, beige_flag, bet, big_back, big_yikes,
blud, bop`), 1 conflict (`acoustic`: blocklisted + `images/acoustic.png` —
use `remove-image acoustic` if you want it gone), 23 skipped (HTML fallback).

## Ticket verification
- [x] Localhost shows all pending with word+strategy (+subject/palette/safety).
- [x] Approve moves to `images/` (proven on `ate`, then restored).
- [x] Reject deletes + updates spec/blocklist (proven, then restored).
- [x] Non-localhost: gate message, no commands (code path mirrors `app.js`).

Open `review.html` over localhost, run `build_review.py` first if you generate
more, and disposition the queue — T06 runs approve-as-you-go from here.
