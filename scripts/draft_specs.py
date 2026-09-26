#!/usr/bin/env python3
"""Draft + validate scraper/image_specs.json (T02).

Manual-curation source of truth for the taxonomy-driven pipeline. No LLM,
no network: a CURATED table (human-authored from scraper/slang.json
definitions) plus heuristic fallback for any word missing from the table.

- Draft subjects are visual paraphrases: single character/scene/object,
  no text in image, NEVER copied from the raw definition (may contain slurs).
- T01 QA learnings baked in: literal subjects name one explicit focal
  object; letter/number emblems demand a clearly legible letterform.
- safety "red" always forces skip_image=True + status="blocked"
  (blocklisted words, self-harm terms, real-person/political words,
  drug-paraphernalia words). Those render via the HTML/SVG fallback.
- "typographic" strategy always forces skip_image=True (never generated).

Usage:
    py -3 scripts/draft_specs.py            # (re)generate image_specs.json
    py -3 scripts/draft_specs.py --check    # validate only
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLANG_JSON = ROOT / "scraper" / "slang.json"
BLOCKLIST_JSON = ROOT / "scraper" / "blocklist_manual.json"
SPECS_JSON = ROOT / "scraper" / "image_specs.json"

STRATEGIES = {
    "literal", "persona", "situational", "template-recreation",
    "symbolic", "typographic",
}

# Tuple fields: (strategy, subject, palette, safety).
# safety: green = benign; yellow = pejorative/profane-adjacent, keep
# family-friendly at review; red = never generate (blocklist, self-harm,
# real person/politics, drugs, explicit sexual content).
CURATED = {
    "-h": ("typographic", "", "", "green"),
    "and i oop": ("situational", "startled cartoon figure dropping an iced coffee cup, single shock vignette", "pink/white/brown, bright contrast", "green"),
    "aura": ("symbolic", "glowing head-and-shoulders silhouette with radiant rings, sticker emblem", "gold/violet glow on dark, luminous contrast", "green"),
    "ate": ("symbolic", "gold star medal with a single bite taken out, sticker emblem", "gold/red, bold contrast", "green"),
    "baddie": ("persona", "confident stylish cartoon woman with sunglasses, fashion mascot pose, single character", "pink/black/gold, glam contrast", "yellow"),
    "ball knowledge": ("literal", "cartoon brain mascot proudly holding a basketball, single clear object", "orange/grey, sporty contrast", "green"),
    "based": ("symbolic", "bold thumbs-up hand emblem, sticker icon", "green/white, clean contrast", "green"),
    "basic": ("persona", "plain cartoon figure in beige outfit holding a plain cup, single character", "beige/cream, muted contrast", "yellow"),
    "bar": ("literal", "cartoon microphone dropping shiny gold ingots, single clear object", "gold/black, stage contrast", "green"),
    "bean soup theory": ("literal", "steaming soup bowl with one bean wearing a tiny crown, single clear object", "warm orange/cream, cozy contrast", "green"),
    "beige flag": ("symbolic", "plain beige pennant flag emblem, flat icon", "beige/grey, neutral contrast", "green"),
    "bet": ("symbolic", "rounded green checkmark badge emblem, flat icon", "green/white, clean contrast", "green"),
    "big back": ("literal", "glowing open fridge with a feast inside, no people, single scene", "warm yellow/blue night-glow contrast", "yellow"),
    "big yikes": ("situational", "cringing cartoon figure covering face with hands, single vignette", "purple/grey, awkward contrast", "green"),
    "big yahu": ("typographic", "", "", "red"),
    "blud": ("persona", "friendly cartoon mate waving hello, single character", "blue/white, cheery contrast", "green"),
    "bop": ("symbolic", "vinyl record with music sparkles emblem, flat icon", "black/pink, retro contrast", "yellow"),
    "brain rot": ("literal", "cartoon brain lounging inside a phone glow with static fuzz, single scene", "grey/static-green, hazy contrast", "yellow"),
    "brat": ("persona", "messy-glam cartoon party figure with smudged style, single character", "lime-green/black, club contrast", "green"),
    "bruh": ("persona", "laid-back cartoon dude with a shrug, single character", "teal/grey, chill contrast", "green"),
    "buns": ("literal", "tray of comically burnt bread buns, single clear object", "char-black/gold, bakery contrast", "green"),
    "bussin'": ("literal", "steaming delicious food bowl with sparkles, single clear object", "warm red/orange, tasty contrast", "green"),
    "cap": ("symbolic", "baseball cap with a long crooked shadow-nose emblem, flat icon", "red/white, sporty contrast", "green"),
    "caught in 4k": ("literal", "retro video camera as the single focal object, bold emblem style", "black/yellow, bold contrast", "green"),
    "chopped": ("symbolic", "cracked hand-mirror emblem, flat icon", "silver/blue, sharp contrast", "yellow"),
    "chud": ("persona", "grumpy cartoon troll archetype with crossed arms, single character", "muddy green/grey, gruff contrast", "yellow"),
    "clanker": ("symbolic", "cute round robot head emblem, flat icon", "silver/blue, clean contrast", "yellow"),
    "clapback": ("literal", "boomerang with lightning streaks, single clear object", "yellow/blue, snappy contrast", "green"),
    "cook": ("persona", "cartoon chef striking a confident pose, single character", "white/red, kitchen contrast", "green"),
    "cooked": ("literal", "burnt cartoon cooking pot with smoke, single clear object", "char-black/orange, smoky contrast", "green"),
    "crash out": ("situational", "cartoon figure with steam bursting from ears, single vignette", "red/grey, heated contrast", "yellow"),
    "crine": ("situational", "laughing cartoon face with joy tears, single vignette", "blue/yellow, happy contrast", "green"),
    "dead": ("symbolic", "laughing cartoon ghost face emblem, flat icon", "white/mint, playful contrast", "green"),
    "delulu": ("situational", "daydreaming cartoon figure gazing at a castle-in-clouds thought bubble, single vignette", "pink/sky-blue, dreamy contrast", "green"),
    "delusionship": ("situational", "couple silhouette with one gazing at a fantasy castle cloud, single vignette", "rose/lavender, wistful contrast", "green"),
    "demure": ("persona", "modest cartoon figure with a teacup in a mindful pose, single character", "sage/cream, calm contrast", "green"),
    "drip": ("literal", "glossy designer jacket with shine drops on a hanger, single clear object", "black/gold, luxe contrast", "green"),
    "el cinco": ("symbolic", "retro game controller with a clearly legible numeral 5, sticker emblem", "blue/white, console contrast", "green"),
    "face card": ("symbolic", "ace-style playing card with a glam face motif, flat icon", "black/pink, card contrast", "green"),
    "fanum tax": ("literal", "cookie with a bite taken out and a crumb trail, single clear object", "brown/cream, snack contrast", "green"),
    "fine shyt": ("symbolic", "double-sparkle glam emblem, flat icon", "pink/gold, glitzy contrast", "yellow"),
    "finna": ("symbolic", "rocket on a launch pad emblem, flat icon", "red/white, launch contrast", "green"),
    "fire": ("literal", "cheerful cartoon flame mascot, single character", "orange/red, hot contrast", "green"),
    "fit": ("literal", "stylish outfit floating on a hanger with sparkles, single clear object", "varied brights, closet contrast", "green"),
    "flop era": ("situational", "beached cartoon fish under a spotlight, single vignette", "blue/pink, stage contrast", "green"),
    "flow state": ("symbolic", "flowing ocean wave emblem, flat icon", "teal/white, fluid contrast", "green"),
    "fuh": ("symbolic", "cartoon palm-out hand emblem, flat icon", "skin-tone/blue, plain contrast", "yellow"),
    "function": ("symbolic", "mirror-ball disco emblem, flat icon", "silver/purple, party contrast", "green"),
    "gagged": ("situational", "wide-eyed cartoon figure with hand over mouth, single vignette", "purple/yellow, shock contrast", "green"),
    "gas": ("literal", "cartoon fuel nozzle pouring rainbow sparkles, single clear object", "rainbow/chrome, fun contrast", "green"),
    "geeked": ("persona", "buzzing excited cartoon figure with static hair, single character", "yellow/blue, electric contrast", "yellow"),
    "gem": ("symbolic", "sparkling gemstone emblem, flat icon", "cyan/white, jewel contrast", "green"),
    "ghost": ("situational", "small cartoon ghost figure drifting away from an unanswered phone, single vignette", "pale blue/grey, soft contrast", "green"),
    "glaze": ("literal", "donut drowning in an over-the-top icing pour, single clear object", "pink/cream, sweet contrast", "green"),
    "glizzy": ("literal", "smiling cartoon hot dog with a mustard squiggle, single clear object", "brown/yellow, snack contrast", "green"),
    "glow-up": ("symbolic", "butterfly with sparkles emblem, flat icon", "orange/purple, radiant contrast", "green"),
    "goat": ("literal", "cartoon goat with a tiny crown, single character", "white/gold, pasture contrast", "green"),
    "gng": ("symbolic", "three-figure group-huddle icon, flat emblem", "green/white, crew contrast", "green"),
    "good boy": ("literal", "happy cartoon dog with a gold star, single character", "brown/gold, wholesome contrast", "green"),
    "goofy ahh": ("persona", "goofy cross-eyed cartoon goofball, single character", "green/purple, silly contrast", "green"),
    "grape": ("typographic", "", "", "red"),
    "green flag": ("symbolic", "green pennant flag emblem, flat icon", "green/white, fresh contrast", "green"),
    "gucci": ("symbolic", "glossy shopping bag with sparkles emblem, flat icon", "black/gold, luxe contrast", "green"),
    "hawk tuah": ("typographic", "", "", "red"),
    "hb": ("symbolic", "two buddy-silhouette duo icon, flat emblem", "blue/white, mate contrast", "green"),
    "hit different": ("symbolic", "star impact-burst emblem, flat icon", "yellow/red, punchy contrast", "green"),
    "ick": ("symbolic", "queasy cartoon face icon, flat emblem", "green/yellow, woozy contrast", "green"),
    "icl": ("symbolic", "speech bubble with a heart emblem, flat icon, no text", "pink/white, honest contrast", "green"),
    "ijbol": ("situational", "cartoon figure clutching belly in laughter, single vignette", "orange/teal, joyful contrast", "green"),
    "ipad kid": ("persona", "cartoon kid mesmerized by a glowing tablet, single character", "blue/grey, screen-glow contrast", "yellow"),
    "it's giving": ("literal", "gift box bursting with sparkles, single clear object", "purple/gold, festive contrast", "green"),
    "it's joever": ("symbolic", "setting-sun emblem, flat icon", "orange/purple, dusk contrast", "yellow"),
    "iykyk": ("symbolic", "winking face emblem, flat icon", "yellow/black, cheeky contrast", "green"),
    "jit": ("persona", "young rookie cartoon with a backwards cap, single character", "red/white, fresh contrast", "green"),
    "jestermaxxing": ("persona", "goofy cartoon jester archetype, single character", "purple/gold, court contrast", "yellow"),
    "karen": ("persona", "entitled cartoon archetype with a bob cut and crossed arms holding coffee, single character", "blonde/red, suburban contrast", "yellow"),
    "khia": ("symbolic", "empty spotlight circle emblem, flat icon", "grey/yellow, vacant contrast", "green"),
    "kirkifying": ("typographic", "", "", "red"),
    "kms": ("typographic", "", "", "red"),
    "kys": ("typographic", "", "", "red"),
    "l": ("symbolic", "giant clearly legible block letter L emblem, flat icon", "red/dark grey, hard contrast", "green"),
    "l+ratio": ("symbolic", "bold clearly legible letter L fused with a tipped balance scale, sticker emblem", "red/blue, clash contrast", "yellow"),
    "larp": ("persona", "cartoon poser in cardboard knight armor, single character", "brown/silver, craft contrast", "green"),
    "lit": ("literal", "lit match with confetti sparks, single clear object", "orange/teal, party contrast", "green"),
    "locked in": ("symbolic", "padlock with a focus ring emblem, flat icon", "black/cyan, target contrast", "green"),
    "looksmaxxing": ("persona", "cartoon figure flexing before a mirror with a measuring tape, single character", "blue/silver, gym contrast", "yellow"),
    "lowkenuinely": ("symbolic", "shushing face icon with a tiny heart, flat emblem", "pink/grey, soft contrast", "green"),
    "lowkirkenuinely": ("typographic", "", "", "red"),
    "main character": ("persona", "cartoon star basking in a spotlight, single character", "gold/black, stage contrast", "green"),
    "mew": ("symbolic", "chiseled side-profile jawline icon, flat emblem", "grey/blue, sculpted contrast", "yellow"),
    "mid": ("symbolic", "gauge needle pointing at middle emblem, flat icon", "yellow/grey, meter contrast", "green"),
    "mog": ("persona", "tall confident cartoon figure casting a long shadow, single character", "dark blue/white, looming contrast", "yellow"),
    "moot": ("symbolic", "two overlapping profile circles emblem, flat icon", "teal/white, mutual contrast", "green"),
    "moving": ("persona", "strutting cartoon figure with a suitcase, single character", "green/black, street contrast", "green"),
    "nepo baby": ("persona", "cartoon baby with tiny sunglasses and a gold chain, single character", "pink/gold, luxe contrast", "yellow"),
    "nostalgia-baiting": ("literal", "toy fishing hook lifting a retro TV, single clear object", "brown/grey, retro contrast", "green"),
    "nothing ever happens": ("symbolic", "calm flat-line chart emblem, flat icon", "grey/green, dull contrast", "yellow"),
    "nugu": ("symbolic", "giant question-mark emblem, flat icon", "purple/white, curious contrast", "green"),
    "ohio": ("literal", "mini surreal cornfield with a floating traffic light, single scene", "green/eerie-yellow, weird contrast", "green"),
    "only in ohio": ("template-recreation", "absurd surreal downtown street with floating traffic light and tilted houses, ominous humor, composition described from text only", "murky green/grey with red accent, eerie contrast", "green"),
    "ok boomer": ("symbolic", "retro rotary phone emblem, flat icon", "cream/brown, vintage contrast", "yellow"),
    "oof": ("symbolic", "star impact-burst emblem, flat icon", "orange/black, thud contrast", "green"),
    "oh that's not": ("symbolic", "cartoon finger-wagging hand emblem, flat icon", "skin-tone/red, stern contrast", "green"),
    "oomf": ("symbolic", "single follower badge silhouette icon, flat emblem", "blue/white, social contrast", "green"),
    "opp": ("symbolic", "split versus emblem with two halves, flat icon", "red/blue, rivalry contrast", "yellow"),
    "out of pocket": ("literal", "turned-inside-out jeans pocket with stars bursting out, single clear object", "denim-blue/yellow, wild contrast", "green"),
    "owned": ("symbolic", "gold trophy emblem, flat icon", "gold/black, victory contrast", "green"),
    "pick-me": ("persona", "gender-neutral cartoon figure with a raised hand seeking attention, single character", "pink/grey, eager contrast", "yellow"),
    "pmo": ("symbolic", "steaming grumpy puff emblem, flat icon", "red/grey, annoyed contrast", "yellow"),
    "polyester": ("symbolic", "shiny fabric swatch zigzag emblem, flat icon", "purple/silver, cheap-shine contrast", "green"),
    "pookie": ("symbolic", "heart with cute ears emblem, flat icon", "pink/cream, sweet contrast", "green"),
    "pushing p": ("symbolic", "giant clearly legible block letter P emblem, flat icon", "green/gold, smooth contrast", "green"),
    "ratio": ("literal", "giant cartoon balance scale tipping to one side, single clear object", "blue/red, debate contrast", "green"),
    "rage-bait": ("literal", "toy fishing rod dangling a grumpy cartoon face, single clear object", "red/grey, hooked contrast", "yellow"),
    "red flag": ("symbolic", "red pennant flag emblem, flat icon", "red/white, alert contrast", "green"),
    "rizz": ("persona", "smooth cartoon charmer with a wink and a rose, single character", "red/black, suave contrast", "green"),
    "roman empire": ("symbolic", "tiny cartoon colosseum emblem, flat icon", "sandstone/blue, ancient contrast", "green"),
    "salty": ("literal", "grumpy cartoon salt shaker, single character", "white/blue, shaker contrast", "green"),
    "sdiybt": ("literal", "tiny cartoon character with a toy shovel, single vignette", "brown/yellow, sandbox contrast", "yellow"),
    "sheesh": ("persona", "cartoon basketball player tapping arm in an icy-veins pose, single character", "frosty blue/black, court contrast", "green"),
    "shook": ("situational", "trembling cartoon figure with motion lines, single vignette", "teal/grey, shaky contrast", "green"),
    "sigma": ("persona", "lone wolf archetype character, confident stance, stylized cartoon mascot, single character", "dark grey/electric blue, moody contrast", "green"),
    "simp": ("persona", "lovesick cartoon knight offering a heart, single character", "pink/silver, earnest contrast", "yellow"),
    "situationship": ("situational", "two cartoon figures linked by a dotted line, single vignette", "rose/grey, ambiguous contrast", "yellow"),
    "six-seven": ("symbolic", "giant clearly legible numerals 67 emblem, flat icon", "green/white, scoreboard contrast", "green"),
    "skibidi": ("symbolic", "goofy cartoon toilet with a face, original twist, single character", "white/blue, bathroom contrast", "yellow"),
    "skill issue": ("symbolic", "game controller with a tiny crack emblem, flat icon", "black/green, gamer contrast", "green"),
    "sksksk": ("literal", "cartoon keyboard with keys bouncing off laughing, single clear object", "rainbow/grey, keysmash contrast", "green"),
    "slaps": ("symbolic", "vinyl record with an impact star emblem, flat icon", "black/gold, hit contrast", "green"),
    "slay": ("symbolic", "shining sword emblem, flat icon", "silver/pink, fierce contrast", "green"),
    "slop": ("literal", "cartoon bucket spilling grey pixel soup, single clear object", "grey/green, mush contrast", "green"),
    "snatched": ("symbolic", "sparkling lightning-bolt glam emblem, flat icon", "gold/pink, fierce contrast", "yellow"),
    "spiritually israeli": ("typographic", "", "", "red"),
    "stan": ("persona", "cartoon superfan with a giant foam finger, single character", "team colors, rally contrast", "green"),
    "sus": ("symbolic", "suspicious hooded silhouette side-eye, single icon character, original twist", "red/white, high contrast", "green"),
    "sussy baka": ("symbolic", "suspicious side-eye face with a tiny fool cap emblem, flat icon", "red/yellow, cheeky contrast", "green"),
    "sybau": ("symbolic", "mouth with a zipper emblem, flat icon", "grey/red, shut contrast", "yellow"),
    "syfm": ("symbolic", "mouth with a zipper and a small padlock emblem, flat icon", "grey/black, shut contrast", "yellow"),
    "tea": ("literal", "tipping teapot with sparkle wisps, single clear object", "mint/gold, gossip contrast", "green"),
    "touch grass": ("literal", "giant hand gently touching a small patch of green lawn, single surreal scene", "green/sky-blue, fresh high contrast", "green"),
    "truth nuke": ("symbolic", "megaphone with impact lines emblem, flat icon", "yellow/black, loud contrast", "green"),
    "ts": ("symbolic", "double overlapping speech bubbles emblem, flat icon, no text", "blue/white, chat contrast", "yellow"),
    "ts frying me": ("literal", "cartoon frying pan with sizzling stars, single clear object", "black/yellow, sizzle contrast", "yellow"),
    "ts pmo": ("symbolic", "speech bubble with a lightning crack emblem, flat icon, no text", "red/grey, frayed contrast", "yellow"),
    "tuff": ("symbolic", "flexed bicep emblem, flat icon", "skin-tone/red, strong contrast", "green"),
    "tweaking": ("situational", "jittery cartoon figure with zigzag lines, single vignette", "neon-green/grey, wired contrast", "yellow"),
    "twin": ("symbolic", "two matching peas in a pod emblem, flat icon", "green/cream, pair contrast", "green"),
    "unalive": ("symbolic", "gentle cartoon ghost holding a small daisy emblem, flat icon", "white/yellow, soft contrast", "yellow"),
    "unc": ("persona", "friendly cartoon elder with glasses and a cardigan, single character", "grey/brown, cozy contrast", "yellow"),
    "understood the assignment": ("symbolic", "checklist with a gold star emblem, flat icon", "green/gold, task contrast", "green"),
    "uwu": ("symbolic", "cute blushing face emblem in kaomoji spirit, flat icon, no text", "pink/white, cute contrast", "green"),
    "vaguepost": ("symbolic", "foggy speech bubble emblem, flat icon, no text", "grey/lavender, hazy contrast", "green"),
    "vibe check": ("literal", "cartoon radar scanner console, single clear object", "green/black, scan contrast", "green"),
    "vro": ("symbolic", "handshake emblem, flat icon", "skin-tone/blue, mate contrast", "green"),
    "w": ("symbolic", "golden trophy letter W emblem, clearly legible letterform, flat icon", "gold/black, win contrast", "green"),
    "washed": ("literal", "faded cartoon star in soap suds, single clear object", "grey/blue, rinse contrast", "green"),
    "who is this diva?": ("persona", "glamorous cartoon diva in a spotlight, single character", "purple/gold, stage contrast", "green"),
    "yap": ("literal", "tiny yappy cartoon dog with bark lines, single character", "brown/yellow, noisy contrast", "green"),
    "yart": ("typographic", "", "", "red"),
    "yassify": ("literal", "cartoon portrait with glam filter sparkles, single clear object", "pink/white, filter contrast", "green"),
    "you good?": ("situational", "two cartoon figures with one checking on the other, single vignette", "blue/cream, caring contrast", "green"),
    "zaza": ("typographic", "", "", "red"),
    "skull emoji": ("symbolic", "giant glossy skull emoji-style face emblem, original twist, flat icon", "white/grey, bone contrast", "green"),
    "loudly crying face emoji": ("symbolic", "giant laughing-crying face emblem with tear streams, original twist, flat icon", "yellow/blue, tearful contrast", "green"),
    "broken heart emoji": ("symbolic", "giant cracked heart emblem, original twist, flat icon", "red/pink, split contrast", "green"),
    "wilted flower emoji": ("symbolic", "giant drooping rose emblem, original twist, flat icon", "red/green, faded contrast", "green"),
    "face with bags under eyes emoji": ("symbolic", "giant weary face with heavy eye bags emblem, original twist, flat icon", "skin-tone/grey, tired contrast", "green"),
}

# Known meme-template names get template-recreation ONLY when the word IS the
# template. (Only-in-Ohio is curated above; nothing else in this dataset is.)
TEMPLATE_WORDS = set()

# Heuristic fallback for words missing from CURATED (safety net only —
# every current word is curated; --check reports fallback usage).
PERSONA_HINTS = ("person", "guy", "girl", "woman", "man", "bro", "dude",
                 "character", "archetype", "individual", "someone who",
                 "people who", "friend", "child", "baby", "kid")
SITUATIONAL_HINTS = ("moment", "when ", "feeling", "relationship",
                     "reaction", "situation", "vibe", "dynamic", "gathering",
                     "party", "event")


def slugify(word):
    slug = word.lower().replace(" ", "_")
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "untitled"


def load_words():
    with open(SLANG_JSON, encoding="utf-8") as f:
        return json.load(f)


def load_blocklist():
    try:
        with open(BLOCKLIST_JSON, encoding="utf-8") as f:
            data = json.load(f)
        return {str(w).lower() for w in data.get("words", [])}
    except FileNotFoundError:
        return set()


def heuristic(word, definition):
    """Fallback guess. Returns (strategy, subject, palette, safety)."""
    d = (definition or "").lower()
    if any(h in d for h in PERSONA_HINTS):
        return ("persona",
                f"cartoon archetype character embodying {word}, single mascot figure, family-friendly",
                "varied brights, clean contrast", "yellow")
    if any(h in d for h in SITUATIONAL_HINTS):
        return ("situational",
                f"single-scene cartoon vignette of a {word} moment, one clear subject",
                "varied brights, clean contrast", "green")
    if len(word.split()) == 1 and len(word) <= 4:
        return ("symbolic",
                f"bold graphic emblem capturing {word}, flat icon, simple shapes",
                "varied brights, clean contrast", "green")
    return ("literal",
            f"{word} depicted as physically real, single focal object, surreal scene",
            "varied brights, clean contrast", "green")


def lookup_curated(key):
    """Exact match first, then emoji/punctuation-tolerant match
    (e.g. 'skull emoji' covers the 'skull emoji <emoji>' word)."""
    if key in CURATED:
        return CURATED[key]
    norm = re.sub(r"[^a-z0-9+ ]", "", key).strip()
    if norm in CURATED:
        return CURATED[norm]
    return None


def build_specs():
    words = load_words()
    blocked = load_blocklist()
    # Preserve human review decisions across regenerations: a re-run must
    # never silently reset an approved/blocked row back to pending.
    existing = {}
    try:
        with open(SPECS_JSON, encoding="utf-8") as f:
            for s in json.load(f):
                existing[str(s.get("word", "")).lower()] = s
    except FileNotFoundError:
        pass
    specs = []
    fallback_used = []
    for item in words:
        word = item.get("word", "")
        key = word.lower()
        if key in blocked:
            # Blocklisted: forced red regardless of curation.
            curated = ("typographic", "", "", "red")
        else:
            curated = lookup_curated(key)
        if curated is None:
            strategy, subject, palette, safety = heuristic(word, item.get("definition", ""))
            fallback_used.append(word)
        else:
            strategy, subject, palette, safety = curated
        if strategy not in STRATEGIES:
            raise ValueError(f"{word!r}: unknown strategy {strategy!r}")
        # Red safety (incl. all blocklisted words) forces skip+blocked.
        # Typographic strategy always skips (HTML/SVG fallback instead).
        if key in blocked:
            safety = "red"
        if safety == "red":
            skip_image = True
            status = "blocked"
            strategy = "typographic"
            subject = ""
            palette = ""
        elif strategy == "typographic":
            skip_image = True
            status = "pending"
        else:
            skip_image = False
            status = "pending"
        prev = existing.get(key)
        seed = None
        rejected_prompts = []
        if prev is not None:
            if prev.get("seed") is not None:
                seed = prev.get("seed")
            if isinstance(prev.get("rejected_prompts"), list):
                rejected_prompts = prev["rejected_prompts"]
            # Censor wins over prior approval, but a prior human decision
            # otherwise survives regeneration. needs-revision (bad image,
            # word itself fine) also survives and stays out of the queue.
            if safety != "red" and prev.get("status") == "approved":
                status = "approved"
            elif prev.get("status") in ("blocked", "needs-revision"):
                if prev.get("status") == "needs-revision" and safety != "red":
                    status = "needs-revision"
                else:
                    status = "blocked"
                skip_image = True
        specs.append({
            "word": word,
            "slug": slugify(word),
            "strategy": strategy,
            "subject": subject,
            "style_preset": "sticker",
            "palette": palette,
            "negative_extra": "",
            "aspect": "1:1",
            "safety": safety,
            "skip_image": skip_image,
            "seed": seed,
            "status": status,
            "rejected_prompts": rejected_prompts,
        })
    specs.sort(key=lambda s: s["word"].lower())
    return specs, len(words), fallback_used


def check(specs=None):
    """Validate specs. Returns (errors, warnings) lists."""
    errors, warnings = [], []
    if specs is None:
        with open(SPECS_JSON, encoding="utf-8") as f:
            specs = json.load(f)
    words = load_words()
    blocked = load_blocklist()
    if len(specs) != len(words):
        errors.append(f"row count {len(specs)} != slang.json count {len(words)}")
    seen_slugs, seen_words = set(), set()
    for s in specs:
        w, slug = s.get("word", ""), s.get("slug", "")
        if w.lower() in seen_words:
            errors.append(f"duplicate word {w!r}")
        seen_words.add(w.lower())
        if slug in seen_slugs:
            errors.append(f"duplicate slug {slug!r} ({w!r})")
        seen_slugs.add(slug)
        if slug != slugify(w):
            errors.append(f"bad slug {slug!r} for {w!r} (want {slugify(w)!r})")
        if s.get("strategy") not in STRATEGIES:
            errors.append(f"{w!r}: bad strategy {s.get('strategy')!r}")
        if s.get("safety") not in ("green", "yellow", "red"):
            errors.append(f"{w!r}: bad safety {s.get('safety')!r}")
        if s.get("status") not in ("pending", "approved", "blocked", "needs-revision"):
            errors.append(f"{w!r}: bad status {s.get('status')!r}")
        want_skip = (s["strategy"] == "typographic" or s["safety"] == "red"
                     or s.get("status") in ("blocked", "needs-revision"))
        if bool(s.get("skip_image")) != want_skip:
            errors.append(f"{w!r}: skip_image={s.get('skip_image')} but strategy={s.get('strategy')} safety={s.get('safety')}")
        if w.lower() in blocked:
            # Blocklisted: must be fully out of the generation pool. Curated
            # reds carry safety=red; human-rejected words keep their curated
            # safety but are blocked+skipped all the same.
            if not (s.get("status") == "blocked" and s.get("skip_image")):
                errors.append(f"{w!r}: blocklisted but not blocked/skipped")
        if not s.get("skip_image") and not (s.get("subject") or "").strip():
            errors.append(f"{w!r}: generatable row has empty subject")
        if s.get("style_preset") != "sticker":
            errors.append(f"{w!r}: style_preset={s.get('style_preset')!r} (T01 locked sticker only)")
        rej = s.get("rejected_prompts", [])
        if not isinstance(rej, list):
            errors.append(f"{w!r}: rejected_prompts is not a list")
            rej = []
        else:
            for r in rej:
                if not isinstance(r, dict) or not (r.get("positive") or "").strip():
                    errors.append(f"{w!r}: malformed rejected_prompts entry")
                    break
        # A pending row must never recycle a rejected prompt: unblocking
        # without a new subject would regenerate the exact failed image.
        if s.get("status") == "pending" and not s.get("skip_image"):
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
                from house_style import build_positive
                current = build_positive(s.get("subject", ""), s.get("palette", ""),
                                         s.get("style_preset") or "sticker")
            except Exception:
                current = None
            if current and any(current == (r.get("positive") or "") for r in rej if isinstance(r, dict)):
                errors.append(f"{w!r}: current prompt repeats a rejected prompt (revise subject first)")
    # Spot-check from the ticket.
    slugs = {s["word"].lower(): s["slug"] for s in specs}
    if slugs.get("and i oop") != "and_i_oop":
        errors.append("spot-check failed: 'and I oop' slug != and_i_oop")
    return errors, warnings


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Draft/validate image_specs.json.")
    p.add_argument("--check", action="store_true", help="Validate existing file only.")
    return p.parse_args(argv)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = parse_args(argv)
    if args.check:
        errors, _warnings = check()
        if errors:
            print(f"CHECK FAILED ({len(errors)}):")
            for e in errors:
                print(f"  - {e}")
            return 1
        with open(SPECS_JSON, encoding="utf-8") as f:
            specs = json.load(f)
        n_skip = sum(1 for s in specs if s["skip_image"])
        n_gen = len(specs) - n_skip
        print(f"CHECK OK: {len(specs)} rows, {n_gen} generatable, {n_skip} skipped/blocked")
        return 0
    specs, n_words, fallback_used = build_specs()
    with open(SPECS_JSON, "w", encoding="utf-8") as f:
        json.dump(specs, f, ensure_ascii=False, indent=2)
        f.write("\n")
    n_skip = sum(1 for s in specs if s["skip_image"])
    print(f"wrote {SPECS_JSON} ({len(specs)} rows from {n_words} words, "
          f"{len(specs) - n_skip} generatable, {n_skip} skipped/blocked)")
    if fallback_used:
        print(f"heuristic fallback used for {len(fallback_used)}: {', '.join(fallback_used)}")
    else:
        print("no heuristic fallback: all rows curated")
    errors, _warnings = check(specs)
    if errors:
        print(f"CHECK FAILED ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("CHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
