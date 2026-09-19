# T02 — Draft + manually curate `image_specs.json`

## Objective
Create the manual source of truth for all ~179 words WITHOUT any LLM call
(per user decision). A heuristic script pre-fills drafts; a human corrects
every row in an editor.

## Scope
- New: `scripts/draft_specs.py`, `scraper/image_specs.json`.
- Read-only inputs: `scraper/slang.json`, `scraper/blocklist_manual.json`
  (12 words — pre-mark `safety:red` / `status:blocked` candidates).

## Steps
1. `draft_specs.py`: for each word in `scraper/slang.json`, emit spec row
   per SPEC §5 schema. Heuristic strategy suggestion only, e.g.:
   - person-type keywords in definition (person, guy, girl, bro, Karen-like,
     -er/-or archetype) → `persona`
   - moment/dynamic keywords (moment, when, feeling, relationship, social)
     → `situational`
   - word matches known template names list (small hardcoded list:
     distracted boyfriend, drake, etc.) → `template-recreation`
   - abstract/single-token concept → `symbolic`, else `literal`.
   - empty/weak subject → `typographic` + `skip_image:true`.
   - word in `blocklist_manual.json` → `safety:red`, `status:blocked`.
   `slug` MUST reuse the exact slugify from
   `scripts/generate_missing_images.py` (lowercase, spaces→`_`,
   strip `[^a-z0-9_]`, collapse `_`).
2. Write human-editable `scraper/image_specs.json` (sorted by word, indent 2).
   Draft `subject` as `<word>-neutral visual paraphrase` — NEVER copy the
   raw definition (may contain slurs) into `subject`.
3. Human pass over all rows: fix `strategy`, write concrete `subject`
   (single character/scene, no text in image), set `palette`,
   `style_preset` (`sticker` unless T01 approved more), `safety`
   (`green|yellow|red`), `skip_image` (true for all `typographic` + `red`),
   leave `seed:null`, `status:pending` (or `blocked`).
4. Validate: script `--check` mode asserts unique slugs, strategy in
   taxonomy, `skip_image` ⟺ `typographic`, blocked words have disposition.

## Verification
- [ ] `py -3 scripts/draft_specs.py --check` passes.
- [ ] Row count == `scraper/slang.json` count (179).
- [ ] Every `typographic` row has `skip_image:true`; every blocklisted word
      has `safety:red` + (`skip_image:true` or `status:blocked`).
- [ ] Spot-check: `slug` for "and I oop" == `and_i_oop`.

## Done when
`image_specs.json` fully hand-reviewed; T04 may consume it. No generator
changes in this ticket.
