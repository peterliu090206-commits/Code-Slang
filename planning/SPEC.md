# Image Generation v2 — Spec

## 1. Goal
Replace the scrape-and-img2img pipeline with taxonomy-driven from-scratch
generation. Cultural signal comes from a curated per-word spec, not copied
pixels. Local one-off run, ~179 words (`scraper/slang.json`), speed not
important. Manual human review is the safety gate; no automated NSFW/OCR
filters in this phase.

## 2. Non-goals
- No web scraping of meme images (retire Firecrawl path).
- No img2img restyle of scraped pixels.
- No LLM batch classifier (manual curation per user decision).
- No automated NSFW / OCR / face-detection gates (manual review only).
- No per-word free-style rendering (fixed house preset suffixes).
- No generated images for typographic words (HTML/SVG fallback instead).

## 3. Current state (verified 2026-09-19)
- `scripts/comfyUI.py` — SDXL txt2img/img2img client, default ckpt
  `dreamshaper_xl_alpha2`, default 1024x1024, `DEFAULT_NEGATIVE` covers
  blur/watermark/text/NSFW/gore. Txt2img nodes 1–7, img2img nodes 1,2,3,8,9,5,6,7.
- `scripts/generate_missing_images.py` — TO RETIRE: Firecrawl `{word} meme`
  search → `docs/data/memes/<slug>.*` cache → ComfyUI img2img `denoise=0.65`
  with prompt `<word>, <definition>, <STYLE_SUFFIX>` → fallback txt2img.
  `slugify` = lowercase, spaces→`_`, strip `[^a-z0-9_]`, collapse `_`.
- Outputs: 2/179 exist (`docs/data/images/acoustic.png`, `and_i_oop.png`).
  ~177 missing.
- `docs/word.js` `slugify()` matches the Python slugify. Image chain:
  `data/images/<slug>.png` → `data/memes/<slug>.jpg` →
  `data/memes/<slug>.png` → `placeholderArt()` SVG letter tile.
  `word-art` is 132px square (96px mobile) in `docs/styles.css`.
- `scraper/blocklist_manual.json` (12 words) + `docs/data/blocklist.json` +
  localhost blacklist FAB (`docs/app.js`, `isLocalhost()` gate) = existing
  manual safety path. `acoustic` is both blocklisted AND has an image —
  review flow must handle blocked-with-image.
- `scripts/build_data.py` merges slang+usage+similar → `docs/data/combined.json`;
  untouched by this project.

## 4. Taxonomy (5 generative + 1 skip)
| Strategy | Use when | Example |
|---|---|---|
| `literal` | Phrase literalized as physically real, absurdist | "touch grass" → hand touching lawn |
| `persona` | Word = type of person | "sigma", "doomer" → archetype character |
| `situational` | Word = moment / social dynamic | "FOMO", "ghosting" → one-subject comic vignette |
| `template-recreation` | Word IS a meme template; recreate composition from structured text description only | "distracted boyfriend" layout/poses/caption zones |
| `symbolic` | Abstract concept → emoji/pictogram, flat vector | "sus" → silhouette side-eye, own twist |
| `typographic` | Nothing visual works → SKIP generation, HTML/SVG fallback | — |

No scraped reference pixels feed the generator at any point.
`template-recreation` uses text descriptions of layout only.

## 5. Spec schema (`scraper/image_specs.json`)
One object per word, manual source of truth. Pre-filled by heuristic script,
corrected by human in an editor (no LLM call).
```json
{
  "word": "sus",
  "slug": "sus",
  "strategy": "symbolic",
  "subject": "suspicious hooded silhouette side-eye, single character",
  "style_preset": "sticker",
  "palette": "red/white, high contrast",
  "negative_extra": "",
  "aspect": "1:1",
  "safety": "green",
  "skip_image": false,
  "seed": null,
  "status": "pending"
}
```
Fields:
- `slug` — must equal both slugify implementations.
- `style_preset` — `sticker` default; `render3d` (persona) / `comic`
  (situational) only if T01 approves a 2nd/3rd preset.
- `safety` — `green|yellow|red` (human judgement; `red` → `skip_image:true`
  or `status:blocked`).
- `skip_image` — true for `typographic` and `red` safety. Generator skips.
- `status` — `pending|approved|blocked`. Generator writes `pending→done`
  via sidecar log, never silently overwrites `approved` without `--force`.

## 6. House style
- Default: flat bold vector sticker (safe-by-default: no photorealism →
  no deepfake/photo risk, reads at 132px thumbnail, aspect-independent).
- Variance comes from `subject`, not rendering.
- Optional 2nd preset (`render3d` Pixar-ish for persona, `comic` panel for
  situational) ONLY if T01 prototype proves it beats sticker on those
  strategies. Otherwise one preset for everything.
- Model/settings locked in T01 by prototyping candidate SDXL
  checkpoints/LoRAs. Until then `dreamshaper_xl_alpha2` stays the default.
- Prompt construction: `{subject}, {palette}, {preset_suffix}`.
  Definition text is NOT in the image prompt (avoids rendering slurs).
  Global negative = `DEFAULT_NEGATIVE` + `photorealistic, real person,
  celebrity likeness`. Fixed `1:1`, 1024.
- Per user scope: image-only output. `typographic` rows produce nothing.

## 7. Pipeline
```
scraper/slang.json
 → scripts/draft_specs.py            (new, heuristic pre-fill, T02)
 → scraper/image_specs.json          (human-edited, T02)
 → scripts/generate_from_specs.py    (new, txt2img only, T03/T04)
 → docs/data/images_pending/<slug>.png
 → docs/review.html                  (new, localhost only, T05)
 → approve: move to docs/data/images/<slug>.png
   reject: delete + status=blocked + blocklist entry
 → docs/word.html shows image; typographic/skipped show SVG letter (T05/T07)
```
- Batching/tracking: `--batch-size/--offset/--limit/--force`,
  skip-existing default, resume-safe, `image_runs.jsonl` sidecar log
  (prompt, preset, ckpt, seed, prompt_id, outcome). Only re-runs cheap
  local ComfyUI queue; no paid API.
- Old pipeline: `generate_missing_images.py` deprecated, not deleted
  (kept for reference). `docs/data/memes/` becomes read-only, then
  fallback chain removed in T07.

## 8. Safety (manual gate)
1. Prompt-time: sticker preset + negative prompt + taxonomy steers to
   icons/characters/scenes.
2. NO automated post-gen filters in this phase (explicit scope cut).
3. Human review queue (T05) is the gate. Conservative approve; auto-pass
   n/a. Blocked words go to `scraper/blocklist_manual.json` via existing
   flow. Personal project risk tolerance: minor issues acceptable,
   blacklist catches them.

## 9. Acceptance criteria (project-level)
- [ ] Zero ComfyUI jobs consume scraped pixels (no img2img, no memes/ writes).
- [ ] Every slang word has exactly one disposition: approved PNG in
      `docs/data/images/` OR `skip_image:true` (typographic) OR
      `status:blocked` (+ blocklist entry).
- [ ] Generator is idempotent: re-run skips existing unless `--force`.
- [ ] `word.html` never shows broken image; missing/blocked/typographic
      degrade to SVG letter tile.
- [ ] House preset (ckpt+suffix+steps/cfg/sampler) recorded and reproducible.

## 10. Tickets
`planning/tickets/T01..T07` — one file per step, each with objective,
scope, steps, verification, and done-criteria. Work top to bottom;
T03 unblocks T04; T05 can start in parallel with T03 UI skeleton but
final wiring needs pending images from T04.
