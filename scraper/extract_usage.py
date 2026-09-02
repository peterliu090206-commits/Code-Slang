#!/usr/bin/env python3
"""Extract real usage sentences for each slang word, filtering out definitions.

Pipeline (stdlib-only NLP):
  1. Normalize raw example text (strip markdown/URLs/HTML, clean whitespace).
  2. Segment it into sentences  (abbreviation-aware splittng).
  3. Keep only sentences that actually mention the word or one of its forms.
  4. Classify each hit as "definition/explanation" or "real usage" using
     lexical signals: copulas ("means", "refers to", "is a slang term"),
     metalanguage ("used to", "stands for", "originated"), shell questions
     ("what does ... mean"), boilerplate ("more results from", "see all").
  5. Rank real-usage sentences (pronoun test, source domain) and keep the
     best N per word.

Outputs:
  slang_usage.json  - structured: word -> top usage sentences + source url/score
  slang_usage.txt   - plain-text cheat sheet for reading

Usage:
    python extract_usage.py                          # slang.json in -> two files out
    python extract_usage.py --top 5                  # keep 5 sentences per word
    python extract_usage.py --keep-definitions       # keep the word's definition too
    python extract_usage.py --debug rizz             # show all drops forr one word
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

DICT_DOMAINS = (
    "urbandictionary.com",
    "wiktionary.org",
    "merriam-webster.com",
    "dictionary.com",
    "wikihow.com",
    "collinsdictionary.com",
    "cambridge.org",
    "oxfordlearnersdictionaries.com",
    "dictionary.cambridge.org",
)

SOCIAL_DOMAINS = (
    "reddit.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tumblr.com",
    "youtube.com",
    "twitch.tv",
    "discord.com",
)

# Copula / definition-style signals -> the sentence explains the term.
DEFINITION_LEXEMES = (
    r"\bmeans?\b",
    r"\bmeant\b",
    r"\bmeaning\b",
    r"\bmeanings\b",
    r"\battributed\b",
    r"\brepresent\w+\b",
    r"\bis\s+when\b",
    r"\bis\s+a\s+\w+\s+(?:who|that|which)\b",
    r"\bwhats\b",
    r"\bwhat'?s\b",
    r"\bexpress\w*\b",
    r"\bused\s+in\b",
    r"\bis\s+(?:mainly|often|widely|mostly|commonly|usually)\s+used\b",
    r"\bis\s+to\s+(?:be\s+)?\w+\b",
    r"\boutside\s+of\s+(?:these|most)\s+contexts\b",
    r"\balso\s+known\s+as\b",
    r"\baka\b",
    r"\ball\s+(?:of\s+)?these\b",
    r"\bis\s+(?:sometimes|often|called)\b",
    r"\blet'?s\s+(?:say|take)\b",
    r"\bis\s+a\s+term\s+for\b",
    r"\bhas\s+come\s+to\s+mean\b",
    r"\bcome\s+into\s+being\b",
    r"\bin\s+reference\s+to\b",
    r"\bdefinit\w+\b",
    r"\brefers?\s+to\b",
    r"\bdenotes?\b",
    r"\bis\s+(?:used|often\s+used)\b",
    r"\bused\s+to\b",
    r"\busage\b",
    r"\bstand[sd]?\s+for\b",
    r"\bshort\s+for\b",
    r"\babbreviat\w+\b",
    r"\bcalls?\s+(?:it|this|someone|that)\b",
    r"\bdescrib\w+\b",
    r"\bsynonym\b",
    r"\bslang\b",
    r"\bterm\b",
    r"\bphrase\b",
    r"\bexpression\b",
    r"\bcode\s+word\b",
    r"\bare\s+words\b",
    r"\bwords?\s+like\b",
    r"\bword[s]?\s+for\b",
    r"\bshortening\b",
    r"\bshortened\b",
    r"\bis\s+short(?:ening)?\s+for\b",
    r"\bbelieved\s+to\s+be\b",
    r"\bexplains?\b",
    r"\bdescribe\w+\b",
    r"\b(is|are|was|were|being)\s+said\b",
    r"\bdescribed\s+(?:as|by|to)\b",
    r"\boriginat\w+\b",
    r"\bcoined\b",
    r"\bcomes?\s+from\b",
    r"\bderives?\s+from\b",
    r"\bstems?\s+from\b",
    r"\bborrowed\b",
    r"\band comes\b",
    r"\bmeaning\b",
    r"\bwhat\s+does\b",
    r"\bwhat\s+is\b",
    r"\bwhat\s+do\b",
    r"\bhow\s+is\b",
    r"\bhow\s+to\s+use\b",
    r"\bwhere\s+does\b",
    r"\bwhy\s+do\b",
    r"\bdo\s+people\b",
    r"\bdictionary\b",
    r"\bwiktionary\b",
    r"\bglossary\b",
    r"\bpronunciation\b",
    r"\bspelling of\b",
    r"\bpronounc\w+\b",
    r"\bmetaphor\b",
    r"\be\.g\.",
    r"\bexamples?\b",
    r"\borderiv\w+\b",
    r"\bi\.e\.",
    r"\bessentially\b",
    r"\bactually means\b",
    r"\bconverted\w*\b",
    r"\breplaces?\b",
    r"\bsubstitut\w+\b",
    r"\brather than\b",
    r"\binstead of\b",
    r"\bdistinct(?:ive)?ly\b",
    r"\bphenomen\w+\b",
    r"\btrend\b",
    r"\bstereotyp\w+\b",
    r"\bpertains\b",
    r"\breflects\b",
    r"\bcarries?\s+(?:the|a)\s+meaning\b",
)

# Metaremarks, nav links, chat boilerplate that are never real usage.
JUNK_PATTERNS = (
    r"\bmore results from\b",
    r"\bsee all\b",
    r"\bread more\b",
    r"\bsee also\b",
    r"\bvisit this post\b",
    r"\bview on\b",
    r"\bfollow\b",
    r"\breply\b",
    r"\blikes?[,:]",
    r"\bcomments?\b",
    r"\bterms of service\b",
    r"\bprivacy\b",
    r"\bcookies?\b",
    r"\bsubscri\w+\b",
    r"\bnewsletter\b",
    r"\bword of the day\b",
    r"\bgift guides\b",
    r"\b[\w\- ]*?gift guide\b",
    r"\badvertis\w+\b",
    r"\bpromoted\b",
    r"\bfaces?\s+heat\b",
    r"\bviral\s+phrase\b",
    r"\bvideo\s+(?:is\s+)?unavailable\b",
    r"\bskip\s+video\b",
    r"\bthis\s+content\s+isn(?:'|\u2019)t\s+available\b",
    r"\bmore\s+results?\s+(?:from|below)\b",
    r"\bexamples?:\b",
    r"\bsee\s+the\s+full\b",
    r"\blearn\s+more\b",
    r"\bverb\b",
    r"\bnoun\b",
    r"\badjective\b",
    r"\badverb\b",
    r"\binterjection\b",
    r"\bpreposition\b",
    r"\bromantic\s+appeal\b",
    r"^answer\b",
    r"\bour\s+blog\b",
    r"\bofficial\s+(?:site|website)\b",
    r"\blistening\s+to\b",
    r"\bshow full\b",
    r"\bexpand\b",
    r"\bcollapse\b",
    r"\bsearch results?\b",
    r"\bjump to\b",
    r"\bcopyright\b",
    r"\ball rights reserved\b",
    r"\btranslate\b",
    r"\bvisually similar\b",
    r"\bverify\b",
    r"\bprofile photo\b",
    r"\bverified\b",
    r"\([^)]*\([^)]*\(",     # nav lists "AF ( almond mom ( aura ( ... ("
)

ABBREV_RE = re.compile(
    r"\b(?:[A-Za-z]\.){2,}\b"          # U.S., e.g.
    r"|\b(?:Mr|Mrs|Ms|Dr|Prof|St|Jr|Sr|etc|vs|No|Mt)\.\b"
    r"|\b\d+\.\d+\b"                   # 7.5
)

URL_RE = re.compile(r"https?://\S+|www\.\S+")
HTML_TAG_RE = re.compile(r"<[^>]+>")
MARKDOWN_RE = re.compile(
    r"!\[[^\]]*\]\([^)]*\)"                # image
    r"|\[([^\]]*)\]\([^)]*\)"              # link -> keep label
    r"|\*\*([^*]+)\*\*"                    # bold
    r"|\*([^*]+)\*"                        # italic
    r"|^#{1,6}\s*"                         # headers (multiline)
)
BOLD_OR_HEADER_RE = re.compile(r"(^|\s)#+\s*|(\*\*|__)")

NONWORD_RE = re.compile(r"[^\w\s'\-/&.,()+]")

PRONOUN_RE = re.compile(
    r"\b(i|me|my|mine|you|your|yours|we|us|our|ours|"
    r"he|him|his|she|her|hers|it|its|they|them|their|theirs|this|that)\b",
    re.I,
)

PROPER_NOUN_HINT_RE = re.compile(r"\b[A-Z][a-z]{2,}")


def normalize_form(form):
    """Reduce a slang form to the text shape that appears in sentences.

    Drops emoji, surrounding punctuation and trailing tense markers so the
    matcher can find e.g. "yall", "6-9", "you good", "skull emoji" etc.
    """
    form = NONWORD_RE.sub(" ", form)
    form = re.sub(r"\s+", " ", form).strip()
    return form.rstrip("'\"?!.,-;:")


def build_matcher(forms):
    """Return a compiled regex that spots the word (any form) in text."""
    needles = []
    for form in forms:
        needle = normalize_form(form)
        if not needle:
            continue
        # "you good?" -> "you good", then drop a trailing "d ?" nothing special.
        need = re.escape(needle)
        needles.append(r"(?<![a-z0-9])" + need + r"(?![a-z0-9])")
    if not needles:
        return None
    return re.compile("|".join(needles), re.I)


def unprotect(text, stash):
    def repl(m):
        return stash[int(m.group(1))]
    return re.sub(r"\x00(\d+)\x00", repl, text)


def split_sentences(text):
    """Naive but decent sentence splitter (handles abbrevs + lowercase joins).

    Newlines are treated as hard breaks because scraped markdown often puts
    one sentence per line; final punctuation then splits within each line.
    """
    stash = []

    def keep(m):
        stash.append(m.group(0))
        return "\x00%d\x00" % (len(stash) - 1)

    text = ABBREV_RE.sub(keep, text)
    sentences = []
    buf = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for part in re.split(r"(?<=[.!?])\s+", line):
            part = part.strip()
            if not part:
                continue
            restored = unprotect(part, stash)
            if buf:
                if restored and restored[0].islower():
                    buf += " " + restored
                    continue
                sentences.append(buf)
                buf = ""
            buf = restored
    if buf:
        sentences.append(buf)
    return sentences


def clean_text(raw):
    """Strip URLs, markdown, html, hashtags, bullets; collapse whitespace."""
    text = raw or ""
    text = URL_RE.sub(" ", text)
    text = HTML_TAG_RE.sub(" ", text)
    text = MARKDOWN_RE.sub(lambda m: (m.group(1) or m.group(2) or "") or " ", text)
    text = BOLD_OR_HEADER_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", " ").replace("\u201d", " ").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"#\w+", " ", text)
    text = re.sub(r"_([^\W_]+)_", r"\1", text)
    text = re.sub(r"(?<=\w)_|_(?=\w)", "", text)
    text = NONWORD_RE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def clean_sentence(raw):
    s = re.sub(r"^[\s\-*•\u2022#>\d\.)]+", "", raw or "").strip()
    s = re.sub(r"^[A-Z][a-z]?\s*:\s*", "", s)      # dialog labels "A: " / "B:"
    s = re.sub(r"^[A-C]\s+(?=[A-Z])", "", s)        # dialog label left without colon
    s = re.sub(r"^r/?\s*[A-Za-z]+\s*[-–—]\s*", "", s)  # "r/teenagers - " prefix
    s = re.sub(r"\s*[-–—]\s*(?:Wikipedia|Urban Dictionary|Reddit|Answer|More)\s*$", "", s)
    s = re.sub(r"\s*[|]\s*$", "", s)                # trailing table/pipe junk
    s = s.rstrip(";,").strip()                      # stray comma/semicolon ends
    s = re.sub(r"\s+", " ", s).strip()
    return s


def domain_of(url):
    try:
        from urllib.parse import urlparse
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def is_definitional(sentence):
    low = sentence.lower()
    return any(re.search(pattern, low) for pattern in DEFINITION_LEXEMES)


def is_junk(sentence):
    return any(re.search(pattern, sentence.lower()) for pattern in JUNK_PATTERNS)


def classify(sentence, matcher):
    """Return (usable, {reason}) for one candidate sentence."""
    if not matcher or not matcher.search(sentence):
        return False, "no word match"
    if is_junk(sentence):
        return False, "junk/boilerplate"
    if is_definitional(sentence):
        return False, "definitional"
    return True, "used"


def score(use, word):
    low = use["sentence"].lower()
    score = 1.0
    if PRONOUN_RE.search(low):
        score += 0.3
    domain = domain_of(use.get("url", ""))
    base = domain
    for d in DICT_DOMAINS:
        if d in base:
            score -= 0.45
            break
    else:
        for d in SOCIAL_DOMAINS:
            if d in base:
                score += 0.3
                break
    return round(score, 2)


def harvest(entry, top, keep_definitions):
    """Collect ranked usage sentences for one entry."""
    matcher = build_matcher(entry.get("forms") or [entry.get("word", "")])
    word = entry.get("word", "")
    hits = []
    seen = set()

    for example in entry.get("examples") or []:
        url = example.get("url", "")
        title = example.get("title", "")
        description = example.get("description", "")
        bodies = []
        if title:
            bodies.append(title)
        if description:
            bodies.append(description)
        for body in bodies:
            for raw in split_sentences(clean_text(body)):
                sentence = clean_sentence(raw)
                low = sentence.lower()
                if not matcher or not matcher.search(sentence):
                    continue
                if is_junk(sentence) or is_definitional(sentence):
                    continue
                if "?" in sentence or "!" == sentence[:0]:
                    continue
                words = sentence.split()
                min_words = 2 if PRONOUN_RE.search(sentence) else 3
                if not (min_words <= len(words) <= 60):
                    continue
                # Dictionary gloss fragments like "rizz romantic appeal or charm"
                # or "mid of mediocre or disappointing quality" start with the word.
                if len(words) <= 6 and low.startswith(normalize_form(word) + " "):
                    if not PRONOUN_RE.search(low):
                        continue
                key = low.rstrip(".!?")
                if key in seen:
                    continue
                seen.add(key)
                hits.append({"sentence": sentence, "url": url, "raw": raw})

    results = []
    for hit in hits:
        s = score(hit, word)
        if s < 0.4:
            continue
        results.append({"sentence": hit["sentence"], "url": hit["url"], "score": s})

    results.sort(key=lambda h: (-h["score"], len(h["sentence"])))
    top_n = results[:top]
    if keep_definitions and entry.get("definition"):
        top_n.insert(0, {
            "sentence": entry["definition"],
            "url": "",
            "score": 0.0,
            "kind": "definition",
        })
    return top_n


def write_txt(entries, path):
    lines = []
    for entry in entries:
        uses = [u for u in entry["uses"] if u.get("kind") != "definition"]
        lines.append(entry["word"])
        if not uses:
            lines.append("    (no natural usage found)")
        for use in uses:
            domain = domain_of(use.get("url", ""))
            src = f"  [{domain}]" if domain else ""
            lines.append(f'    "{use["sentence"]}"{src}')
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(BASE / "slang.json"))
    parser.add_argument("--json-out", default=str(BASE / "slang_usage.json"))
    parser.add_argument("--txt-out", default=str(BASE / "slang_usage.txt"))
    parser.add_argument("--top", type=int, default=3, help="usage sentences per word")
    parser.add_argument("--keep-definitions", action="store_true")
    parser.add_argument("--word", default=None, help="limit to one word (debug)")
    args = parser.parse_args(argv)

    data_path = Path(args.data)
    records = json.loads(data_path.read_text(encoding="utf-8"))

    out_entries = []
    total = 0
    empty = 0
    for raw in records:
        word = raw.get("word", "")
        if args.word and word.lower() != args.word.lower():
            continue
        uses = harvest(raw, args.top, args.keep_definitions)
        if not uses:
            empty += 1
        total += len(uses)
        out_entries.append({"word": word, "uses": uses})

    payload = {"count": len(out_entries), "entries": out_entries}
    Path(args.json_out).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_txt(out_entries, Path(args.txt_out))

    print(
        f"{len(out_entries)} words processed, {total} usage sentence(s) kept, "
        f"{empty} word(s) with no usage found."
    )
    print(f"Wrote {args.txt_out} and {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())