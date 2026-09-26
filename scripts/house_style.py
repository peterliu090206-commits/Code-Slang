#!/usr/bin/env python3
"""House-style preset lock (T01 output, consumed by T03/T04).

Single source of truth for the taxonomy-driven generation style.
Variance comes from the per-word subject, never from free-styled rendering.

Locked decision (T01):
- Default preset for ALL strategies: "sticker" (flat bold vector sticker).
  Safe-by-default: no photorealism -> no deepfake/photo risk, reads at the
  132px word-art thumbnail, aspect-independent.
- Optional presets "render3d" (persona) and "comic" (situational) are
  DEFINED here but GATED: only use them if a probe run proves they clearly
  beat sticker on those strategies. Otherwise sticker everywhere.
- Baseline checkpoint: dreamshaper_xl_alpha2.safetensors (the repo's current
  default). Candidates B/C (flat-vector/sticker SDXL fine-tunes) to be
  evaluated via scripts/probe_house_style.py when a ComfyUI server is up;
  winner replaces PRESETS["sticker"]["ckpt"] without changing prompts.

Prompt construction (SPEC section 6):
    positive = "<subject>, <palette>, <preset suffix>"
The word's definition text NEVER enters the image prompt (avoids rendering
slurs). Global negative = comfyUI.DEFAULT_NEGATIVE + NEGATIVE_DELTA.
Fixed 1:1, 1024x1024 to match the word-art tile.
"""

STEPS = 25
CFG = 7.0
SAMPLER = "euler"
SCHEDULER = "normal"
WIDTH = 1024
HEIGHT = 1024

# Fixed seed for probe comparability across candidates. Batch runs (T06)
# use random seeds per word, logged to image_runs.jsonl for reproducibility.
PROBE_SEED = 42

# Safety delta recorded per T01 step 6. Also appended to
# comfyUI.DEFAULT_NEGATIVE so ad-hoc comfyUI.py calls inherit it.
NEGATIVE_DELTA = "photorealistic, real person, celebrity likeness"

# Candidate checkpoints for the sticker preset. "baseline" is locked as the
# default; "B"/"C" are slots to fill with locally available flat-vector /
# sticker SDXL fine-tunes and compare via the probe matrix.
CANDIDATE_CKPTS = {
    "baseline": "dreamshaper_xl_alpha2.safetensors",
    "B": None,  # e.g. "<sticker-finetune>.safetensors" — fill in when testing
    "C": None,  # e.g. "<vector-finetune>.safetensors" — fill in when testing
}

PRESETS = {
    "sticker": {
        "ckpt_candidate": "baseline",
        "suffix": (
            "flat bold vector sticker, thick outline, solid background, "
            "no text, no watermark, family-friendly"
        ),
        "negative_extra": "",
        "use_for": "default for all strategies",
    },
    "render3d": {
        # GATED (T01): persona words only, and only if probes prove it beats
        # sticker. Pixar-ish cute 3D is strongest for characters, weakest for
        # abstract words — do not use outside persona without evidence.
        "ckpt_candidate": "baseline",
        "suffix": (
            "cute 3D render, pixar-style character, soft studio lighting, "
            "solid background, no text, no watermark, family-friendly"
        ),
        "negative_extra": "",
        "use_for": "persona strategy only, gated",
    },
    "comic": {
        # GATED (T01): situational words only, and only if probes prove it
        # beats sticker. Single clear subject, minimal context.
        "ckpt_candidate": "baseline",
        "suffix": (
            "single-panel comic illustration, bold ink lines, flat colors, "
            "one clear subject, minimal background, no text, no speech "
            "bubbles, no watermark, family-friendly"
        ),
        "negative_extra": "",
        "use_for": "situational strategy only, gated",
    },
}

# Locked winner summary (T01 done-criteria). Candidate B/C comparison is
# pending a live ComfyUI server; until then baseline is the lock.
LOCKED = {
    "preset": "sticker",
    "ckpt": CANDIDATE_CKPTS["baseline"],
    "suffix": PRESETS["sticker"]["suffix"],
    "steps": STEPS,
    "cfg": CFG,
    "sampler": SAMPLER,
    "scheduler": SCHEDULER,
    "width": WIDTH,
    "height": HEIGHT,
    "seed_policy": "fixed PROBE_SEED=42 for probes; random per word for batch",
    "negative_delta": NEGATIVE_DELTA,
}


def ckpt_for(preset_name="sticker", candidate_override=None):
    """Resolve the checkpoint file for a preset."""
    preset = PRESETS[preset_name]
    candidate = candidate_override or preset["ckpt_candidate"]
    ckpt = CANDIDATE_CKPTS.get(candidate)
    if not ckpt:
        raise ValueError(
            f"ckpt candidate {candidate!r} has no file configured "
            f"(see CANDIDATE_CKPTS in house_style.py)"
        )
    return ckpt


def build_positive(subject, palette, preset_name="sticker"):
    """Build the positive prompt. Definition text must never reach here."""
    return f"{subject}, {palette}, {PRESETS[preset_name]['suffix']}"


def build_negative(base_negative, preset_name="sticker", row_extra=""):
    """Global negative + safety delta + preset/row extras (deduped)."""
    parts = [base_negative]
    if NEGATIVE_DELTA not in (base_negative or ""):
        parts.append(NEGATIVE_DELTA)
    preset_extra = PRESETS[preset_name].get("negative_extra", "")
    if preset_extra:
        parts.append(preset_extra)
    if row_extra:
        parts.append(row_extra)
    return ", ".join(p for p in parts if p)
