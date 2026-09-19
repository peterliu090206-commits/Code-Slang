# T01 — House-style prototype & model lock

## Objective
Pick the generation checkpoint + fixed prompt suffix + sampler settings that
nail the house style BEFORE any batch run. Per user decision: evaluate a new
checkpoint (don't blindly keep `dreamshaper_xl_alpha2`).

## Scope
- Files touched: none yet (experiments via existing `scripts/comfyUI.py`
  `--positive/--ckpt/--steps/--cfg/--sampler/--prefix/--output` flags).
- Output: locked preset(s) recorded for T03.

## Steps
1. Pick 8 probe words from `scraper/slang.json` covering all 5 generative
   strategies: e.g. 2× literal, 2× persona, 1× situational, 1×
   template-recreation, 2× symbolic. Include one blocklisted-adjacent but
   safe word to test safety behavior (do NOT publish bad outputs).
2. Candidate A (baseline): current `dreamshaper_xl_alpha2` + sticker suffix:
   `flat bold vector sticker, thick outline, solid background, no text,
   no watermark, family-friendly`.
3. Candidate B/C: 1–2 flat-vector/sticker SDXL checkpoints or LoRAs
   available locally. Same 8 probes, same seeds if possible (`--seed` fixed)
   for comparability.
4. Optionally test 2nd preset ONLY on persona/situational probes:
   `render3d` (Pixar-ish cute 3D) and/or `comic` (single-panel comic).
   Criterion: adopt 2nd preset only if it clearly beats sticker on those
   strategies; else single preset for everything.
5. Judge at real display size: 132px (`docs/styles.css` `.word-art`) AND
   full 1024. Criteria: reads at thumbnail, no garbled text, no photoreal
   faces, on-palette, family-friendly, consistent across probes.
6. Record winner: ckpt filename, preset suffix string(s), steps/cfg/sampler,
   seed policy (fixed vs random), negative prompt delta
   (`photorealistic, real person, celebrity likeness` addition).

## Verification
- [ ] 8 probes × 2–3 candidates exist as files outside `docs/data/images/`
      (e.g. `docs/data/probes/` — delete or gitignore after; do NOT pollute
      the real image dir).
- [ ] Winner documented (ckpt + suffix + steps/cfg/sampler) — paste into
      T03 ticket when implementing.

## Done when
House preset(s) locked in writing; T03 can hardcode them. No batch
generation starts before this.
