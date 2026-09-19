# T05 — Human review queue (localhost web UI)

## Objective
Manual approve/reject gate per user decision ("extend web UI review").
Staged images wait in `images_pending/`; nothing reaches `docs/data/images/`
without a click. Reuses existing localhost + blacklist patterns.

## Scope
- New: `docs/review.html` (+ small inline script or `docs/review.js`,
  versioned like `app.js`/`word.js` via `build_data.py` stamping if cheap,
  else `?v=` manual).
- Read: `docs/data/images_pending/`, `docs/data/images/`,
  `scraper/image_specs.json` disposition.
- Write path: approve = filesystem move pending→images; reject = delete +
  spec `status:blocked` + append to `scraper/blocklist_manual.json`.
  (Static hosting can't do this — localhost helper: document a tiny
  local-only move script, e.g. `scripts/review_move.py approve|reject
  <slug>`, wired as copy-paste command per card OR minimal local server
  endpoint. Do NOT ship a remote-writable endpoint.)

## Steps
1. `review.html`: grid of pending cards — pending PNG, word, strategy,
   subject, palette, existing `images/` state (missing/overwrite), and
   per-card `approve` / `reject` control rendering the exact
   `review_move.py` command (or button if local endpoint chosen).
2. Gate everything behind the existing `isLocalhost()` pattern from
   `docs/app.js` (hide on GitHub Pages). Session-only censor default stays.
3. `scripts/review_move.py`: `approve <slug>` moves
   `images_pending/<slug>.png` → `images/<slug>.png` and sets spec
   `status:approved`; `reject <slug>` deletes pending, sets
   `status:blocked`, appends word to `blocklist_manual.json` (dedupe,
   sorted). Both append to `image_runs.jsonl`.
4. Handle edge: `acoustic` (blocklisted + has image) — review UI must show
   the conflict and offer reject/remove-image explicitly.
5. `typographic` rows show as "HTML fallback, no image expected" — never
   appear as missing.

## Verification
- [ ] On localhost, pending pilot images from T04 visible with word+strategy.
- [ ] Approve moves file to `images/`; `word.html?w=<word>` shows it.
- [ ] Reject deletes pending, updates spec + blocklist; word stays censored
      per existing `word.js` blocked flow.
- [ ] On non-localhost (Pages), review page shows "local only" message,
      no move commands leak.

## Done when
T04 pilot fully dispositioned through this UI; T06 can run approve-as-you-go.
