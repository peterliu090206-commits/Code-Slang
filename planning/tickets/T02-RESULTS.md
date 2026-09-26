# T02 Results — `image_specs.json` curated 2026-09-26

- `scripts/draft_specs.py` (new): CURATED table + heuristic fallback + `--check`.
  Re-run any time: `py -3 scripts/draft_specs.py` / `--check`.
- `scraper/image_specs.json` (new): **179/179 rows, all hand-curated, zero
  heuristic fallback**. Sorted by word, indent 2, per SPEC §5 schema.
- Disposition: **156 generatable** (pending) + **23 skipped** (22 red/blocked,
  1 green typographic `-h`).
- Strategies: symbolic 76, literal 37, persona 28, situational 14,
  template-recreation 1 (`only in Ohio`), typographic 23.
- Safety: green 117, yellow 40, red 22 (12 blocklisted + grape, hawk tuah,
  Kirkifying, big yahu, lowkirkenuinely, spiritually Israeli, KMS, KYS,
  yart, zaza).
- Ticket verification all green: `--check` OK; count 179; every typographic
  has `skip_image:true`; every blocklisted word is red/blocked/skipped;
  `and I oop` → `and_i_oop`; subject-field slur grep clean (no definition
  text leaked into prompts).
- Curation rules applied: single focal subject, no text in image, T01
  learnings (explicit focal object for literal; "clearly legible
  letterform/numeral" for L/W/P/67/el-cinco emblems); body-mockery words
  (`big back`, `chopped`, `bop`, `snatched`) steer to objects/emblems, never
  depicted people; real-person/political words red-skipped.
- T03 consumes this file; `style_preset` is `sticker` on all rows (T01 lock).
