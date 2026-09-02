#!/usr/bin/env python3
"""Natural slang usage filter — detects definitional vs wrong-sense usages.

Uses:
  - Regex metalanguage detection (Category A)
  - all-MiniLM-L6-v2 embeddings for word-sense check (Category B)

Public API:
  is_metalanguage(sentence, word, forms) -> (bool, reason)
  is_correct_sense(sentence, word, definition) -> (bool, reason, score)
  is_natural_usage(sentence, word, definition, forms) -> (bool, reason, debug)
  clean_json(in_path, out_path) -> stats
  filter_usages(candidates, word, definition, forms) -> filtered list
"""

import json
import re
import sys
import argparse
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Re-use patterns from extract_usage but extended for metalanguage
try:
    from extract_usage import DEFINITION_LEXEMES, JUNK_PATTERNS, is_junk as _is_junk_base
except ImportError:
    DEFINITION_LEXEMES = ()
    JUNK_PATTERNS = ()
    _is_junk_base = None

# Additional metalanguage patterns not in extract_usage (Category A)
METALANGUAGE_EXTRA = (
    r"\bis\s+a\s+word\b",
    r"\bis\s+a\s+word\s+that\b",
    r"\bis\s+defined\s+as\b",
    r"\bis\s+known\s+as\b",
    r"\bthe\s+word\s+\w+\s+means\b",
    r"\bthe\s+term\s+\w+\s+means\b",
    r"\bis\s+a\s+term\s+that\b",
    r"\bis\s+a\s+phrase\s+that\b",
    r"\bwhat\s+does\s+\w+\s+mean\b",
    r"\bmeaning\s+of\s+\w+\b",
    r"\bdefinition\s+of\b",
)

# Combined definitional check
_ALL_DEFINITIONAL = tuple(DEFINITION_LEXEMES) + METALANGUAGE_EXTRA

THRESHOLD = 0.08  # global cosine threshold (very low to keep short slang)
DISTRACTOR_THRESHOLD = 0.50  # kept for reference, but distractors now immediate reject

# Minimal literal distractor map for highly polysemous words (no overcomplication)
LITERAL_DISTRACTORS = {
    "chopped": ["salad", "onion", "garlic", "vegetable", "lettuce", "tomato", "cheese", "wood", "tree", "axe", "arm", "leg", "hand", "finger", "chopped off", "cut", "knife", "board"],
    "bar": ["bartender", "mixology", "drink", "alcohol", "pub", "counter", "tapas", "saloon"],
    "ate": ["lunch", "dinner", "breakfast", "food", "meal", "ate a ", "ate an ", "ate the ", "ate some"],
    "cook": ["kitchen", "recipe", "oven", "stove", "cook the", "cooked the"],
    "ghost": ["haunted", "halloween", "spirit", "paranormal"],
    "washed": ["laundry", "clothes", "dishes", "washed clothes"],
}

# Lazy model singleton
_model = None
_model_name = "all-MiniLM-L6-v2"


def get_model():
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers not installed. Run: pip install sentence-transformers"
        )
    _model = SentenceTransformer(_model_name)
    return _model


def _cosine(a, b):
    import numpy as np
    # a, b are 1D arrays
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def is_metalanguage(sentence: str, word: str = "", forms=None) -> tuple[bool, str]:
    """Detect definitional / explanatory usage. Returns (is_meta, reason)."""
    low = sentence.lower()

    # 1. Quoted-term + copula pattern: "rizz is ..." / 'chopped is ...'
    if word:
        w = re.escape(word.lower())
        if re.search(rf"""(^|[\s"'`]){w}\s+is\b""", low):
            # if sentence contains metalanguage noun nearby, it's meta
            if re.search(r"\b(word|term|phrase|slang|meaning|defined|acronym|abbreviation)\b", low):
                return True, "quoted-term is word/term"
            # Also catch "word is a ..." without extra noun but definitional verb
            if re.search(rf"\b{w}\s+is\s+a\b", low):
                # avoid false positive on natural "he is chopped" - check metalanguage lexeme anywhere
                if any(re.search(p, low) for p in _ALL_DEFINITIONAL):
                    return True, "quoted-term is a + definitional lexeme"

    # 2. Generic definitional lexemes (from extract_usage)
    for pat in _ALL_DEFINITIONAL:
        if re.search(pat, low):
            return True, f"definitional: {pat}"

    # 3. Question form always meta
    if "?" in sentence and re.search(r"\bwhat\s+does\b|\bwhat\s+is\b|\bhow\s+to\s+use\b", low):
        return True, "question definitional"

    return False, ""


def is_junk(sentence: str) -> tuple[bool, str]:
    if _is_junk_base is not None:
        # reuse existing
        from extract_usage import is_junk as ej
        if ej(sentence):
            return True, "junk"
    else:
        for pat in JUNK_PATTERNS:
            if re.search(pat, sentence.lower()):
                return True, f"junk: {pat}"
    return False, ""


def is_correct_sense(sentence: str, word: str, definition: str, threshold: float = THRESHOLD) -> tuple[bool, str, float]:
    """Embedding sense check. Returns (ok, reason, cosine_score). Empty definition => True."""
    if not definition or not definition.strip():
        return True, "no definition -> skip", 1.0
    try:
        model = get_model()
    except ImportError as e:
        # Fallback: if model unavailable, don't block - treat as correct
        return True, f"model not available: {e}", 1.0

    # Anchor definition with word for better slang grounding: "chopped means ugly..."
    def_text = f"{word} means {definition}" if word else definition
    def_emb = model.encode(def_text, convert_to_numpy=True, normalize_embeddings=False)
    sent_emb = model.encode(sentence, convert_to_numpy=True, normalize_embeddings=False)
    score = _cosine(def_emb, sent_emb)

    # Literal collocate shortcut: if sentence contains cooking/pub etc., it's almost certainly wrong sense
    low = sentence.lower()
    distractors = LITERAL_DISTRACTORS.get(word.lower(), []) if word else []
    for d in distractors:
        if d in low:
            # double-check with embedding: if cosine is extremely high (>0.70) trust embedding (rare)
            if score > 0.70:
                return True, f"correct_sense cosine {score:.3f} (distractor {d!r} but high cosine)", score
            return False, f"wrong_sense literal collocate {d!r} cosine {score:.3f}", score

    if score < threshold:
        return False, f"wrong_sense cosine {score:.3f} < {threshold}", score
    return True, f"correct_sense cosine {score:.3f}", score


def is_natural_usage(sentence: str, word: str, definition: str, forms=None, threshold: float = THRESHOLD) -> tuple[bool, str, dict]:
    """Combined gate. Returns (ok, reason, debug_dict)."""
    debug = {}
    # 1. Junk
    junk, j_reason = is_junk(sentence)
    if junk:
        debug["junk"] = j_reason
        return False, f"junk: {j_reason}", debug
    # 2. Metalanguage
    meta, m_reason = is_metalanguage(sentence, word, forms)
    if meta:
        debug["metalanguage"] = m_reason
        return False, f"metalanguage: {m_reason}", debug
    # 3. Sense
    ok, s_reason, score = is_correct_sense(sentence, word, definition, threshold)
    debug["cosine"] = round(score, 3)
    debug["sense_reason"] = s_reason
    if not ok:
        return False, s_reason, debug
    return True, "natural", debug


def filter_usages(candidates, word: str, definition: str, forms=None, threshold: float = THRESHOLD):
    """Filter a list of {sentence, url, score} dicts. Returns filtered list."""
    out = []
    for c in candidates:
        sent = c.get("sentence", "")
        ok, reason, debug = is_natural_usage(sent, word, definition, forms, threshold)
        if ok:
            # attach debug for transparency
            c = dict(c)
            c["_sense_score"] = debug.get("cosine")
            out.append(c)
    return out


def clean_json(in_path: str | Path, out_path: str | Path | None = None, threshold: float = THRESHOLD,
               slang_json_path: str | Path | None = None) -> dict:
    """
    Clean slang_usage.json of incorrect usages.
    If slang_json_path provided, loads definitions from there for accurate sense check;
    otherwise uses empty definition (only metalanguage/junk filtering).
    Returns stats dict.
    """
    in_path = Path(in_path)
    data = json.loads(in_path.read_text(encoding="utf-8"))

    # Build word -> definition map if available
    def_map = {}
    if slang_json_path:
        slang_data = json.loads(Path(slang_json_path).read_text(encoding="utf-8"))
        # slang.json is list, slang_usage.json is {entries: [...]}
        if isinstance(slang_data, list):
            for r in slang_data:
                def_map[r.get("word","").lower()] = r.get("definition","")
                for f in r.get("forms", []):
                    def_map[f.lower()] = r.get("definition","")
        elif isinstance(slang_data, dict) and "entries" in slang_data:
            for r in slang_data["entries"]:
                def_map[r.get("word","").lower()] = r.get("definition","") if "definition" in r else ""

    # Also if input is slang_usage style, extract definitions if present
    if isinstance(data, dict) and "entries" in data:
        entries = data["entries"]
        is_usage_file = True
    elif isinstance(data, list):
        entries = data
        is_usage_file = False
    else:
        raise ValueError("Unknown JSON shape")

    stats = {"total": 0, "kept": 0, "removed": 0, "by_reason": {}, "by_word": {}}

    for entry in entries:
        word = entry.get("word","")
        definition = def_map.get(word.lower(), entry.get("definition","") or "")
        forms = entry.get("forms", [word])
        uses = entry.get("uses", entry.get("examples", []))
        if not isinstance(uses, list):
            continue
        filtered = []
        for u in uses:
            # uses in slang_usage.json have "sentence", examples in slang.json have title/description
            # For cleaning slang_usage.json we check "sentence"
            sent = u.get("sentence") or u.get("description") or u.get("title") or ""
            if not sent:
                continue
            stats["total"] += 1
            ok, reason, debug = is_natural_usage(sent, word, definition, forms, threshold)
            if ok:
                filtered.append(u)
                stats["kept"] += 1
            else:
                stats["removed"] += 1
                key = reason.split(":")[0] if ":" in reason else reason
                # normalize
                if "metalanguage" in reason or "definitional" in reason:
                    key = "metalanguage"
                elif "wrong_sense" in reason:
                    key = "wrong_sense"
                elif "junk" in reason:
                    key = "junk"
                stats["by_reason"][key] = stats["by_reason"].get(key, 0) + 1
                stats["by_word"][word] = stats["by_word"].get(word, 0) + 1

        # write back
        if is_usage_file:
            entry["uses"] = filtered
        else:
            entry["examples"] = filtered

    # update count if usage file
    if is_usage_file and "count" in data:
        # keep original count of words, not uses
        pass

    out = Path(out_path) if out_path else in_path
    # backup if overwriting
    if out == in_path:
        backup = in_path.with_suffix(in_path.suffix + ".bak")
        backup.write_text(in_path.read_text(encoding="utf-8"), encoding="utf-8")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # also regenerate txt if cleaning slang_usage.json
    if is_usage_file:
        # try to also write txt alongside
        try:
            from extract_usage import write_txt, domain_of  # noqa
            txt_path = out.with_suffix(".txt") if out.suffix == ".json" else BASE / "slang_usage.txt"
            # need to convert to entries for write_txt
            # data already filtered
            if out == in_path:
                txt_path = BASE / "slang_usage.txt"
            else:
                txt_path = Path(str(out).replace(".json", ".txt"))
            # Rebuild entries for txt
            # write_txt expects list of {word, uses}
            write_txt(entries, txt_path)
        except Exception:
            pass

    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=str, help="Sentence to check")
    parser.add_argument("--word", type=str, default="", help="Slang word")
    parser.add_argument("--definition", type=str, default="", help="Definition for sense check")
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    parser.add_argument("--clean", type=str, help="Path to slang_usage.json to clean")
    parser.add_argument("--out", type=str, default=None, help="Output path for cleaned json")
    parser.add_argument("--slang-json", type=str, default=str(BASE / "slang.json"), help="Path to slang.json for definitions")
    args = parser.parse_args(argv)

    if args.check is not None:
        ok, reason, debug = is_natural_usage(args.check, args.word, args.definition, [args.word], args.threshold)
        print(f"Sentence: {args.check!r}")
        print(f"Word: {args.word!r} Definition: {args.definition!r}")
        print(f"Result: {'NATURAL' if ok else 'REJECTED'} — {reason}")
        print(f"Debug: {debug}")
        return 0

    if args.clean:
        stats = clean_json(args.clean, args.out, args.threshold, args.slang_json)
        print(f"Cleaned {args.clean} -> {args.out or args.clean}")
        print(json.dumps(stats, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
