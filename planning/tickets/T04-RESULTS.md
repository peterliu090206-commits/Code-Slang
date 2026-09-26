# T04 Results — pilot batch live 2026-09-26

## No-double-generation guard (new, this ticket)
`scripts/generate_from_specs.py` now skips words that are approved (`images/`)
OR staged (`images_pending/`) unless `--force`; selection prints a breakdown
(`blocked/typographic=X, done=Y, staged=Z`). New `--slugs a,b,c` filter targets
exact words (still honors all guards) — also useful for T06 single-word retries.

## Dedup audit (before generating)
- `draft_specs.py --check`: 179 rows, slugs unique.
- `images_pending/`: only `ate.png` (T03). JSONL: 1 ok entry, no dupes.

## Pilot: 5 words × 5 strategies (+ `ate` from T03 = 6 staged)
`--slugs aura,baddie,ball_knowledge,ghost,only_in_ohio` → `done: 5/5 ok`,
base seed 2126704337 (+0..4 per word), all staged in `images_pending/`.
Dry-run beforehand confirmed exact 5-row slice, no definition text, no
typographic/blocked rows.

## Double-generation proofs
- Re-ran identical command → `0 generatable targets (staged=5)`, `nothing to
  do`. No wasted runs, no overwrites.
- `--force --seed 2126704337 --slugs aura` → re-queued exactly 1 row, output
  SHA256 **identical** (`9909F37F…7310B1`, same byte size). Seed
  reproducibility proven bit-for-bit; force path proven scoped.
- JSONL final: 7 attempts / 7 ok / 6 unique slugs — the single duplicate-slug
  pair is the intentional aura repro (same seed, identical bytes), not an
  accidental double-generate. Every ok entry carries seed + prompt_id.

## QA (all 6 eyeballed full-size)
| Image | Verdict |
|---|---|
| ate (T03) | pass — gold-star medal, no text |
| aura | pass — regal glowing bust, on-palette |
| baddie | pass (+safety) — stylish, family-friendly, non-sexualized |
| ball_knowledge | pass — brain-basketball mascot, fun |
| ghost | pass — cute ghost + phone, closest to brief yet |
| only_in_ohio | pass — surreal eerie street, signpost blank, no text, no meme copy |

No slur text, no watermarks, no photoreal faces in any of the 6.

## Ticket verification
- [x] 1 + 5 PNGs in `images_pending/`, none added to `images/` (only
      pre-existing `acoustic.png`, `and_i_oop.png` there).
- [x] Re-run without `--force` queues nothing.
- [x] `docs/data/memes/` + `docs/data/images/` clean in `git status`.
- [x] Pilot eyeballed — readable at full size, sticker-consistent, safe.

T05 (review UI) has 6 real pending images to work with; T06 full run unblocked.
Remaining generatable after pilot: 150 (155 − 5 staged this ticket; `ate` was
already staged in T03).
