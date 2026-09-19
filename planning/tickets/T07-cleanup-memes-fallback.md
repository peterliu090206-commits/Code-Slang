# T07 — Typographic fallback + memes retirement

## Objective
Typographic words (never generated, per user scope) look intentional via
the HTML/SVG fallback; the old memes fallback chain is removed so no
scraped pixel can ever render.

## Scope
- Edit: `docs/word.js` (fallback chain), `docs/styles.css` (tile polish
  only), `docs/review.html` (typographic row label — T05).
- No generator changes.

## Steps
1. Polish `placeholderArt()` tile in `docs/word.js` if pilot shows weakness
   at 132/96px: check letter centering, contrast (`#f1ede6` tile / `#6f6a63`
   letter per current CSS), non-Latin first chars. Keep it a styled wordmark
   card — this IS the typographic strategy rendering.
2. Remove the `data/memes/` fallback steps from the `img error` handler
   (`memes-jpg` → `memes-png` stages): chain becomes
   `data/images/<slug>.png` → `placeholderArt()` → remove. Keep `alt`
   text update (`<word> (no illustration yet)`).
3. Leave `docs/data/memes/` files on disk untouched (reference only); confirm
   nothing in `docs/*.js` or `scripts/generate_from_specs.py` reads them.
4. Regression check: typographic word page, approved-image word page,
   blocked word page (censored flow), missing-image word page — all four
   render without broken `<img>`.
5. Update SPEC or ticket notes if `build_data.py` asset-stamping needs the
   new `review.js` (only if T05 added one).

## Verification
- [ ] Grep `docs/word.js` for `memes` → no matches.
- [ ] Grep `scripts/generate_from_specs.py` for `meme|firecrawl|img2img` →
      no matches.
- [ ] Four page states above manually checked on localhost + one remote
      (Pages) load.

## Done when
Project acceptance criteria (SPEC §9) all check; old pipeline fully inert.
