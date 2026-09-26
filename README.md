# Code Slang — 2020s Slang Dictionary

Static dictionary website (GitHub Pages, served from `docs/`) for 2020s slang:
definitions, real-usage quotations, similar terms, sources, similarity clusters,
a manual censor gate, and one AI illustration per word in a locked sticker house
style. All data is prebuilt JSON; the site itself has no backend.

State as of 2026-09-26: 179 words; 14 approved images; ~86 staged; 2 words
awaiting prompt revision (`ate`, `blud`); 12 blocklisted words. Counts drift —
see "Common recipes" for live counts.

Audience: future-me. Everything runnable is documented with exact commands.
For any script, `py -3 <script> --help` is authoritative if this file disagrees.

## Contents

- [Prerequisites](#prerequisites)
- [E2E flow A — word to website (text data)](#e2e-flow-a--word-to-website-text-data)
- [E2E flow B — word to illustration (image pipeline)](#e2e-flow-b--word-to-illustration-image-pipeline)
- [Review loop (read this before touching images)](#review-loop-read-this-before-touching-images)
- [Prompt revision loop (rejected images)](#prompt-revision-loop-rejected-images)
- [Viewing the site locally](#viewing-the-site-locally)
- [Directory reference](#directory-reference)
- [Data file reference](#data-file-reference)
- [Script reference: scripts/](#script-reference-scripts)
- [Script reference: scraper/](#script-reference-scraper)
- [Frontend reference (docs/ root)](#frontend-reference-docs-root)
- [Safety and censorship model](#safety-and-censorship-model)
- [Planning docs (untracked)](#planning-docs-untracked)
- [Common recipes](#common-recipes)
- [Gotchas](#gotchas)

## Prerequisites

- Python via `py -3` (repo scripts; 3.14 seen in the wild). ComfyUI has its own
  venv Python 3.12 — do not mix them up.
- Local ComfyUI at `C:\Users\peter\Documents\comfy\ComfyUI`, venv at
  `.venv\Scripts\python.exe`, served on `http://127.0.0.1:8188`
  (`python main.py --port 8188` with working dir = the ComfyUI folder).
  Checkpoints in `models/checkpoints/`: `dreamshaper_xl_alpha2.safetensors`
  (house-style lock) + `sd_xl_base_1.0.safetensors` (spare candidate).
  GPU seen: RTX 4060 Laptop 8GB — SDXL 1024px works, minutes per image.
- `FIRECRAWL_API_KEY` in `scraper/.env` (gitignored) only for the
  Firecrawl-based text steps. Not needed for image generation.
- Embedding steps (`find_similar.py`, parts of `extract_usage.py`) pull
  `all-MiniLM-L6-v2` (cached under `scraper/.cache/`).

## E2E flow A — word to website (text data)

Each step's output is the next step's input. All commands run from repo root
unless noted.

1. **Scrape the word list** — `py -3 scraper/scrape_slang.py` (run from root;
   it has NO `--help` and RUNS on invocation). Fetches Wikipedia's
   "Glossary of 2020s slang" via the API into `scraper/slang.json`
   (list of `{word, definition, forms}`). WARNING: it overwrites
   `slang.json` with raw entries and drops the `examples` Firecrawl adds
   later — back up first; the committed copy has examples.
2. **Fetch usage examples** — `py -3 scraper/firecrawl_examples.py`
   (`--word rizz` for one word, `--limit 8 --content`, `--only-missing`,
   `--query-template`, `--sleep`, `--api-key` or env, `--merge/--no-merge`,
   `--replace`, `--data`). Searches the web per word, stores top results as
   `examples[]` on each `slang.json` entry.
3. **Extract real usage sentences** — `py -3 scraper/extract_usage.py`
   (`--data`, `--json-out`, `--txt-out`, `--top`, `--keep-definitions`,
   `--word`, `--no-filter`, `--threshold`, `--filter-debug`, `--replace`).
   Stdlib-only NLP: normalize → segment → keep sentences mentioning the word →
   drop definitions via lexical signals → rank. Uses `slang_filter.py`
   (`is_natural_usage` etc.) unless `--no-filter`. Writes
   `scraper/slang_usage.json` (+ `slang_usage.txt` cheat-sheet).
4. **Similar terms + clusters** — `py -3 scraper/find_similar.py`
   (`--data`, `--usage`, `--out`, `--model`, `--distance-threshold`, `--top`,
   `--min-score`, `--english`, `--english-top`, `--english-threshold`,
   `--english-vocab-size`, `--use-usage/--no-usage`, `--linkage`,
   `--batch-size`). Encodes `{word}: {definition}` with MiniLM, HAC clustering
   (average linkage, cosine). Writes `scraper/slang_similar.json`.
5. **Censor list** — `py -3 scraper/build_blocklist.py`
   (`--auto` to merge better-profanity hits, `--check "phrase"` to test).
   Default is manual-only: `scraper/blocklist_manual.json` (curated via the
   localhost card checkboxes) → `docs/data/blocklist.json`
   (`{words, generated_at, method, count}`).
6. **Build the site payload** — `py -3 scripts/build_data.py` (no flags).
   Merges `slang.json` + `slang_usage.json` + `slang_similar.json` into
   `docs/data/combined.json` (sorted, examples ≤5, uses ≤3, similar ≤5) and
   re-stamps `?v=` cache-busters + `window.__V` in `index.html`, `word.html`,
   `review.html`. Run after ANY data change.

## E2E flow B — word to illustration (image pipeline)

House style (locked, T01): flat bold vector sticker, `dreamshaper_xl_alpha2`,
25 steps / 7.0 / euler, 1024x1:1. Prompt formula
`{subject}, {palette}, {suffix}` — definition text NEVER enters a prompt.
Variance comes from the subject, never the rendering.

1. **Draft + curate specs** — `py -3 scripts/draft_specs.py` writes
   `scraper/image_specs.json` (179 rows, SPEC schema: word/slug/strategy/
   subject/style_preset/palette/negative_extra/aspect/safety/skip_image/seed/
   status/rejected_prompts). Rows are hand-curated (no LLM): every word has a
   strategy (`literal|persona|situational|template-recreation|symbolic|
   typographic`), a visual paraphrase subject, a palette, and a safety
   (`green|yellow|red`). `py -3 scripts/draft_specs.py --check` validates:
   counts, unique slugs, `skip ⟺ typographic/red/blocked/needs-revision`,
   blocklist disposition, non-empty subjects, sticker-only preset, and that no
   pending row repeats its own rejected prompt. Regenerations preserve human
   status/seeds/history (censor wins on new blocklist entries).
2. **(Optional) probe new checkpoints** — `py -3 scripts/probe_house_style.py
   --dry-run`, then `--candidate baseline` (or `--ckpt file` for challengers,
   `--preset-override` for the gated render3d/comic presets, `--limit`,
   `--force`, `--seed` default 42). Throwaway output to `docs/data/probes/`,
   never `images/`.
3. **Generate** — `py -3 scripts/generate_from_specs.py --batch-size 5`
   (also `--list-missing`, `--dry-run`, `--offset`, `--limit`, `--force`,
   `--slugs a,b,c`, `--preset-override`, `--ckpt`, `--seed` base + index,
   `--steps/--cfg/--sampler/--scheduler/--server/--timeout`). Skips
   typographic/blocked/needs-revision, approved (`images/`) and staged
   (`images_pending/`) rows — so nothing is ever generated twice — and stages
   new PNGs in `docs/data/images_pending/`. Every attempt appends to
   `scraper/image_runs.jsonl` (word/slug/strategy/preset/ckpt/seed/prompt_id/
   outcome/bytes/full prompts). Seeds reproduce images bit-for-bit.
4. **Review** — see next section. Nothing reaches `images/` except through it.
5. Old pipeline `scripts/generate_missing_images.py` (Firecrawl meme scrape +
   img2img restyle) is DEPRECATED, kept for reference; it warns on run.

## Review loop (read this before touching images)

Static hosting can't write files, so the page renders decisions and a script
executes them. Censorship-style: checkboxes + floating button.

1. `py -3 scripts/build_review.py` → `docs/data/review_queue.json`
   (gitignored staging manifest: 179 rows, pending/approved/skipped/conflict/
   needs_revision counts).
2. Serve `docs/` locally, open `review.html` (localhost-gated; off-localhost
   shows "local only", no commands). Pending cards: **unchecked = approve**,
   check **reject** to delete the staged image and queue the word for prompt
   revision (reject NEVER censors). Conflict cards (blocked word with an
   image): check **remove image**.
3. Floating bottom-right button shows live counts; click downloads
   `review_decisions.json` (`{approved[], rejected[], remove_image[]}`).
4. `py -3 scripts/review_move.py apply-batch <file>` executes it (approvals →
   rejects → removals, one manifest rebuild, per-row failures reported).
   Single actions: `approve|reject|remove-image <slug>`; `status` is a
   read-only overview. Refusals: won't approve blocked rows or blocklisted
   words; unknown slugs error cleanly.

## Prompt revision loop (rejected images)

Rejected prompts are saved, never silently reused:

1. On reject, the judged generation (positive/seed/ckpt/prompt_id from
   `image_runs.jsonl`) is appended to the row's `rejected_prompts` (inline in
   `image_specs.json`). Review page lists these under "Needs prompt revision".
2. `py -3 scripts/review_move.py export-revision <slug> [--out DIR]` writes
   `scraper/revision_<slug>.json` (machine packet) + `.md` (paste-ready brief:
   strategy, house suffix, current subject/palette, numbered negative
   examples, reply format). Paste the `.md` to a strong LLM manually.
3. `py -3 scripts/review_move.py revise <slug> --subject "…" --palette "…"`
   applies the replacement: refuses red words and prompts identical to a
   rejected one, flips status→pending/unskipped, requeues. Next generator run
   picks it up as missing.

## Viewing the site locally

```
Set-Location docs; py -3 -m http.server 8123
# index.html = grid + censor toggle + blacklist FAB (localhost only)
# word.html?w=rizz = detail page; word-art chain: images/<slug>.png
#   -> memes/<slug>.jpg -> memes/<slug>.png -> SVG letter tile
# review.html = review queue (localhost only, needs build_review.py first)
```

`?v=` stamps + `window.__V` come from `build_data.py`; never hand-edit them.

## Directory reference

- `docs/` — the site (GitHub Pages root). `.nojekyll` disables Jekyll.
- `docs/data/` — generated payloads: `combined.json`, `blocklist.json`,
  `review_queue.json` (gitignored staging manifest).
- `docs/data/images/` — APPROVED word art, tracked. `<slug>.png`, 1024px.
- `docs/data/images_pending/` — STAGED word art awaiting review, GITIGNORED.
- `docs/data/memes/` — FROZEN reference: 2 legacy jpgs (`acoustic`,
  `and_i_oop`). Fallback chain only; nothing writes here anymore.
- `docs/data/probes/` — throwaway T01 style probes (`<slug>__<candidate>.png`),
  untracked. Safe to delete.
- `scraper/` — text-pipeline inputs/outputs + image spec sources.
- `scraper/.cache/` — MiniLM vocab/embedding cache (regenerable, keep).
- `scraper/__pycache__/`, `scripts/__pycache__/` — bytecode, ignored.
- `scripts/` — site build + image pipeline runners.
- `planning/` + `planning/tickets/` — UNTRACKED local notes: SPEC, per-step
  tickets T01–T07, T01–T05 RESULTS. Design memory; not part of the site.
- `.idea/` — PyCharm project files. Ignore.
- `.git/` — vcs. Note: `acoustic.png`/`and_i_oop.png` deletions are staged;
  `slang.json` worktree must keep its `examples` (see Gotchas).

Slug rule (everywhere): lowercase, spaces→`_`, strip `[^a-z0-9_]`, collapse
`_` (`"and I oop"` → `and_i_oop`). Python and JS implementations match.

## Data file reference

| File | Producer | Consumer | Commit? |
|---|---|---|---|
| `scraper/slang.json` | `scrape_slang.py` + `firecrawl_examples.py` | usage/similar/blocklist/specs | yes (WITH examples) |
| `scraper/slang_usage.json` (+`.txt`, `.bak`) | `extract_usage.py` | `build_data.py`, `find_similar.py` | yes |
| `scraper/slang_similar.json` | `find_similar.py` | `build_data.py` | yes |
| `scraper/image_specs.json` | `draft_specs.py` + hand curation | generator, review | no (untracked, back it up) |
| `scraper/probe_specs.json` | hand (T01 matrix) | `probe_house_style.py` | no |
| `scraper/image_runs.jsonl` | generator + review moves | reject snapshots, audits | no (gitignored) |
| `scraper/blocklist_manual.json` | hand curation | `build_blocklist.py` | yes |
| `scraper/.env` | hand | Firecrawl scripts | no (gitignored, secret) |
| `scraper/revision_<slug>.json/.md` | `export-revision` + LLM | `revise` | no (delete after apply) |
| `docs/data/combined.json` | `build_data.py` | `app.js`, `word.js` | yes |
| `docs/data/blocklist.json` | `build_blocklist.py` | `app.js`, `word.js` | yes |
| `docs/data/review_queue.json` | `build_review.py` | `review.js` | no (gitignored) |
| `review_decisions.json` | review FAB (→ Downloads) | `apply-batch` | no (throwaway) |

Spec row statuses: `pending` (queued to generate) · `approved` (shipped) ·
`blocked` (censored, never generates) · `needs-revision` (bad image, word
fine, out of queue until `revise`). Safety: `green` benign · `yellow`
pejorative-adjacent, keep family-friendly · `red` never generate.

## Script reference: scripts/

- `build_data.py` (no flags) — merge slang+usage+similar → `combined.json`;
  stamp `?v=`/`window.__V` in index/word/review HTML. Run after any data change.
- `comfyUI.py` — ComfyUI HTTP client (stdlib only). `--positive` (required),
  `--negative`, `--width/--height` (txt2img), `--init-image`, `--denoise`,
  `--ckpt` (default `dreamshaper_xl_alpha2`), `--prefix`, `--output`,
  `--server`, `--seed`, `--steps`, `--cfg`, `--sampler`, `--scheduler`,
  `--batch`, `--timeout`, `--background`, `--print-workflow`. Negative already
  includes `photorealistic, real person, celebrity likeness`.
- `house_style.py` — NOT a runner: the T01 preset lock (`PRESETS`, `LOCKED`,
  `CANDIDATE_CKPTS`, `build_positive/build_negative/ckpt_for`). Import target.
- `draft_specs.py` — `--check` validates `image_specs.json` (counts, slugs,
  skip invariants, blocklist disposition, no repeated rejected prompts);
  bare run regenerates it preserving human status/seeds/history.
- `probe_house_style.py` — T01 matrix runner → `docs/data/probes/`.
  `--dry-run`, `--candidate`, `--ckpt`, `--preset-override`, `--limit`,
  `--force`, `--seed` (42), `--server/--timeout/--steps/--cfg/--sampler/
  --scheduler`.
- `generate_from_specs.py` — the batch runner → `images_pending/` + JSONL.
  See E2E flow B for all 15 flags. Key guards: skips done/staged/blocked/
  typographic/needs-revision; `--slugs` for targeted retries; `--force`
  overrides skips.
- `generate_missing_images.py` — DEPRECATED (Firecrawl+img2img). Warns on run.
  Kept for reference; `comfyUI.py` img2img helpers exist only for it.
- `build_review.py` (no flags) — rebuild `review_queue.json`. Run after every
  generate/review mutation (auto-called by `review_move.py`).
- `review_move.py` — `status` (read-only) · `approve/reject/remove-image
  <slug>` · `apply-batch <json>` · `export-revision <slug> [--out]` ·
  `revise <slug> --subject S [--palette P]` · `reject --reason`.

## Script reference: scraper/

- `scrape_slang.py` — Wikipedia glossary → `slang.json`. NO ARGS, RUNS
  IMMEDIATELY, OVERWRITES (see Gotchas).
- `firecrawl_examples.py` — web examples → `examples[]` per entry.
  `--word`, `--only-missing`, `--limit`, `--content`, `--data`, `--api-key`,
  `--sleep`, `--query-template`, `--merge/--no-merge`, `--replace`.
- `extract_usage.py` — sentences → `slang_usage.json`/`.txt`. `--data`,
  `--json-out`, `--txt-out`, `--top`, `--keep-definitions`, `--word`,
  `--no-filter`, `--threshold`, `--filter-debug`, `--replace`.
- `slang_filter.py` — library (no CLI): `is_metalanguage`,
  `is_correct_sense`, `is_natural_usage`, `clean_json`, `filter_usages`.
  Regex + MiniLM two-stage usage filter.
- `find_similar.py` — embeddings + HAC → `slang_similar.json`. `--data`,
  `--usage`, `--out`, `--model`, `--distance-threshold`, `--top`,
  `--min-score`, `--english*`, `--use-usage/--no-usage`, `--linkage`,
  `--batch-size`.
- `build_blocklist.py` — manual (+optional auto) → `docs/data/blocklist.json`.
  Bare run = manual; `--auto` merges better-profanity; `--check "phrase"`.

## Frontend reference (docs/ root)

- `index.html` / `app.js` — card grid, search, cluster + A–Z filters, word of
  the day, random, result counts, censor toggle (session-only, never
  persisted), localhost card checkboxes + floating blacklist-FAB exporting
  `blocklist_manual.json`, back-to-top.
- `word.html` / `word.js` — detail page (`?w=`): art with
  images→memes→SVG-letter fallback, forms, definition, real-usage quotes with
  sources, similar terms + plain-English neighbours, cluster mates, sources,
  prev/next pager, censored-word gate with session-only reveal.
- `review.html` / `review.js` — localhost-only queue: conflicts, pending cards
  with reject checkboxes (unchecked = approve), needs-revision section with
  export commands, approved links, skipped chips, floating export FAB
  (`review_decisions.json`). Single GET fetch; writes nothing.
- `styles.css` — tokens (`--bg/--ink/--accent…`), header/controls, grid/cards,
  chips, detail, pager, to-top + blacklist FABs. Review page adds a small
  inline `<style>` for its grid/cards.
- `.nojekyll` — empty; disables Jekyll on Pages.

## Safety and censorship model

1. Prompt-time: sticker house style (no photorealism → no deepfake risk),
   curated negative prompt, taxonomy steers to icons/characters/scenes.
2. Human review gate: nothing ships without approve; rejects loop through
   revision, never silently regenerate (check-enforced).
3. Censor: `blocklist_manual.json` (hand) → `blocklist.json` (generated) →
   hidden on index + gated word pages; session-only reveal. `better-profanity`
   only ever *suggests* (`--auto` to merge). No automated NSFW/OCR/face
   filters by design (small scale, personal project, manual queue instead).

## Planning docs (untracked)

- `planning/SPEC.md` — the v2 image-generation design (§1–10): goals,
  taxonomy, spec schema, house style, pipeline, acceptance criteria.
- `planning/tickets/T01-house-style-prototype.md` + `T01-RESULTS.md` — preset
  lock (sticker + dreamshaper, 25/7.0/euler) and 8-probe QA verdict.
- `T02*.md` — spec curation rules (single focal subject, no text, no
  definition leakage, body-mockery dodges, red-skip categories).
- `T03*.md` — runner build + old-pipeline retirement.
- `T04*.md` — pilot + no-double-generation proofs (staged-skip, seed repro).
- `T05*.md` — review UI + revision loop.
- `T06-full-run.md`, `T07-cleanup-memes-fallback.md` — remaining work: bulk
  approve-as-you-go run, then remove the memes fallback chain.

## Common recipes

- Live counts: `review_move.py status`; generatable left:
  `generate_from_specs.py --list-missing`.
- Resume a batch: re-run the same command — done/staged rows skip; use
  `--force` (or `--slugs`) only for deliberate redos.
- Redo one word: `--slugs <slug>` (add `--force` if approved/staged).
- After any data/spec change: `build_data.py` (text) / `build_review.py`
  (images) before reloading the page.
- Unblocklist a word: edit `blocklist_manual.json`, rerun `build_blocklist.py`
  + `build_data.py`.
- Full text rebuild (order matters): scrape → firecrawl → extract_usage →
  find_similar → build_blocklist → build_data.

## Gotchas

- `scraper/scrape_slang.py` runs on invocation and OVERWRITES `slang.json`,
  dropping `examples` (168 raw vs 179 enriched). Restore with
  `git checkout -- scraper/slang.json` if run by accident — the committed copy
  has examples. Never run it casually.
- `docs/data/images_pending/`, `scraper/image_runs.jsonl`,
  `docs/data/review_queue.json` are gitignored — they live only on this
  machine. `image_specs.json`/`probe_specs.json`/`planning/` are untracked but
  NOT ignored: back them up, and don't `git add` blindly.
- `image_specs.json` is the human source of truth; `draft_specs.py` bare runs
  preserve review state, but prefer `--check` for validation.
- Rejected words never requeue until `revise`d; approved words never
  regenerate without `--force`.
- `review.html` needs a local http server (fetch fails over `file://` for JSON
  in some browsers); ComfyUI and the site server are two different servers on
  different ports — don't confuse :8188 and your static port.
