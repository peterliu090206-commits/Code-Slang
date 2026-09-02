#!/usr/bin/env python3
"""Scrape the Wikipedia "Glossary of 2020s slang" article into JSON."""

import html
import json
import re
import sys
import urllib.parse
import urllib.request

API_URL = "https://en.wikipedia.org/w/api.php"
PAGE = "Glossary_of_2020s_slang"
OUTPUT = "slang.json"

USER_AGENT = "SlangScraper/1.0 (educational use)"


def fetch_wikitext(page):
    params = {
        "action": "parse",
        "page": page,
        "prop": "wikitext",
        "format": "json",
        "formatversion": "2",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    return data["parse"]["wikitext"]


def split_nested(text):
    """Split a MediaWiki line on the given separator, ignoring nested groups."""
    return text


TEMPLATE_KEEP_FIRST = ("vanchor", "visible anchor")


def strip_templates(text):
    """Remove {{...}} templates. Keeps the first param of anchor templates."""
    previous = None
    while previous != text:
        previous = text
        text = re.sub(
            r"\{\{\s*([^{}\n]+?)\s*\|([^{}\n]{1,4000}?)\s*\}\}"
            r"|\{\{\s*([^{}\n]{1,4000}?)\s*\}\}",
            lambda m: _template_repl(m),
            text,
        )
    return text


def _template_repl(m):
    name = (m.group(1) or m.group(3) or "").strip().lower()
    if name in TEMPLATE_KEEP_FIRST:
        params = [p.strip() for p in m.group(2).split("|")]
        return params[0] if params else ""
    return ""


def strip_wikilinks(text):
    def link(m):
        target = m.group(1)
        label = m.group(2)
        if target.lower().startswith(("file:", "image:", "category:", "wikt:")):
            return label if label else ""
        return label if label else target

    return re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", link, text)


def clean_section(text):
    """Generic cleanup removing markup, refs and templates from wikitext."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<ref[^>]*/>", " ", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]*?>", " ", text)
    text = strip_templates(text)
    text = strip_wikilinks(text)
    text = text.replace("'''", "").replace("''", "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


POS_MARKERS = ["verb", "adjective", "noun", "adverb", "pronoun", "suffix"]


def extract_forms(cleaned_term):
    """Return (primary_word, [forms]) from a cleaned term string.

    Forms capture tense and spelling variations of the main word, e.g.
    "bruh/bru", "dead/ded", "brain rot (or brainrot)", "six-seven (6-7)",
    "moot(s)", "zaza, za".
    """
    text = cleaned_term

    text = re.sub(r"\(\s*/\s*[^)]*?/\s*\)", " ", text)
    text = re.sub(r"\(\s*\)", " ", text)

    alternates = []
    m = re.search(r"\(\s*(?:or|sometimes)\s+([^)]+?)\s*\)", text)
    if m:
        alternates.append(m.group(1).strip())
        text = text.replace(m.group(0), " ")

    def paren_eval(mm):
        inner = mm.group(1).strip()
        if inner.lower() in {"s", "es"}:
            return mm.group(0)
        low = inner.lower()
        if any(marker in low for marker in POS_MARKERS):
            return " "
        if " " in low:
            return " "
        alternates.append(inner)
        return " "

    text = re.sub(r"\(([^)]+)\)", paren_eval, text)

    text = re.sub(r"\s+", " ", text).strip()

    parts = [p.strip() for p in re.split(r"[/,]+", text) if p.strip()]

    suffixes = []
    text_suffix = " ".join(parts)
    m = re.search(r"\(\s*(s|es)\s*\)\s*$", text_suffix)
    if m:
        suffixes.append(m.group(1))
        parts = [re.sub(r"\(\s*(?:s|es)\s*\)\s*$", "", p).strip() for p in parts]

    forms = []
    for p in parts:
        if not p:
            continue
        forms.append(p)
        if suffixes:
            for suffix in suffixes:
                forms.append(p + suffix)

    for alt in alternates:
        for a in re.split(r"[/,]+", alt):
            a = a.strip()
            if a:
                forms.append(a)

    seen = []
    for f in forms:
        if f not in seen:
            seen.append(f)

    if not seen:
        return cleaned_term, [cleaned_term]

    return seen[0], seen


SPELLING_PATTERNS = [
    r"(?:also|sometimes|occasionally)?\s*(?:sometimes\s+)?spelt\s+[\"\u201c\u201d]([^\"\u201c\u201d]+)[\"\u201c\u201d]",
    r"(?:also|sometimes|occasionally)?\s*(?:sometimes\s+)?spelled\s+[\"\u201c\u201d]([^\"\u201c\u201d]+)[\"\u201c\u201d]",
    r"pronunciation\s+spelling\s+of\s+[\"\u201c\u201d]([^\"\u201c\u201d]+)[\"\u201c\u201d]",
    r"eye\s+dialect\s+spelling\s+of\s+[\"\u201c\u201d]([^\"\u201c\u201d]+)[\"\u201c\u201d]",
    r"variant\s+pronunciation/spelling\s+of\s+[\"\u201c\u201d]([^\"\u201c\u201d]+)[\"\u201c\u201d]",
    r"variant\s+spelling\s+of\s+[\"\u201c\u201d]([^\"\u201c\u201d]+)[\"\u201c\u201d]",
]


def definition_forms(base, definition):
    extra = []
    for pattern in SPELLING_PATTERNS:
        for m in re.finditer(pattern, definition, flags=re.I):
            candidate = m.group(1).strip().strip(".,;:!?")
            if candidate and candidate not in extra:
                extra.append(candidate)
    merged = list(base)
    for e in extra:
        if e not in merged:
            merged.append(e)
    return merged


def parse_entries(lines):
    entries = []
    section = None
    current = None

    allowed = re.compile(r"^[A-Z]$|^Emoji$")

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue

        header = re.match(r"^==\s*(.+?)\s*==$", stripped)
        if header:
            name = header.group(1).strip()
            if allowed.match(name):
                section = name
                if current:
                    entries.append(current)
                current = None
                continue
            if section is not None:
                break
            continue

        if section is None:
            continue

        if stripped.startswith(";"):
            if current:
                entries.append(current)
            term = stripped[1:].strip()
            current = {
                "section": section,
                "term_raw": term,
                "def_lines": [],
            }
        elif stripped.startswith(":") and current is not None:
            current["def_lines"].append(stripped[1:].strip())

    if current:
        entries.append(current)
    return entries


def build(entries):
    records = []
    for entry in entries:
        term = clean_section(entry["term_raw"])
        definition = clean_section(" ".join(entry["def_lines"]))
        if not term or not definition:
            continue
        word, forms = extract_forms(term)
        forms = definition_forms(forms, definition)
        records.append(
            {
                "word": word,
                "definition": definition,
                "forms": forms,
            }
        )
    return records


def main():
    print(f"Fetching {PAGE} ...")
    wikitext = fetch_wikitext(PAGE)
    lines = wikitext.split("\n")
    print("Parsing entries ...")
    entries = parse_entries(lines)
    print(f"Found {len(entries)} raw entries")
    records = build(entries)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)
    print(f"Wrote {len(records)} entries to {OUTPUT}")


if __name__ == "__main__":
    sys.exit(main())