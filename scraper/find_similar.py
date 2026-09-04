#!/usr/bin/env python3
"""Find similar slang words via HAC clustering over sentence embeddings.

Reads slang.json, encodes each word as "{word}: {definition}" with
all-MiniLM-L6-v2, runs Agglomerative Hierarchical Clustering (average
linkage, cosine metric), and writes slang_similar.json with cluster
membership and per-word ranked similar neighbours within the same cluster.

Usage:
    python find_similar.py
    python find_similar.py --distance-threshold 0.6 --top 5
    python find_similar.py --data slang.json --out slang_similar.json
    python find_similar.py --no-usage  # don't enrich with usage sentences
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DEFAULT_DATA = BASE / "slang.json"
DEFAULT_USAGE = BASE / "slang_usage.json"
DEFAULT_OUT = BASE / "slang_similar.json"

# Lazy model singleton (reuse slang_filter logic)
_model = None
_model_name = "all-MiniLM-L6-v2"


def get_model(name=_model_name):
    global _model
    if _model is not None:
        # reuse if same name, else reload
        if getattr(_model, "_model_name", None) == name:
            return _model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers not installed. Run: pip install sentence-transformers"
        )
    _model = SentenceTransformer(name)
    _model._model_name = name
    return _model


NONWORD_RE = re.compile(r"[^\w\s'\-/&.,()+]")


def normalize_form(form: str) -> str:
    form = NONWORD_RE.sub(" ", form or "")
    form = re.sub(r"\s+", " ", form).strip()
    return form.rstrip("'\"?!.,-;:").lower()


def build_encode_text(entry, use_usage_text=False, usage_map=None):
    """Build the text to embed for a slang entry."""
    word = entry.get("word", "").strip()
    definition = entry.get("definition", "").strip()
    # Primary anchor: "word: definition" gives phrase grounding
    if word and definition:
        text = f"{word}: {definition}"
    elif word:
        text = word
    else:
        text = definition

    # Optionally enrich with first usage sentence for context
    if use_usage_text and usage_map is not None:
        key = word.lower()
        uses = usage_map.get(key, [])
        if uses:
            # take best scored usage sentence
            best = sorted(uses, key=lambda u: u.get("score", 0), reverse=True)[0]
            sent = best.get("sentence", "").strip()
            if sent and len(sent) > 10:
                text = f"{text} Example: {sent}"
    return text


def load_usage_map(usage_path: Path):
    """Return {word_lower: [uses]} from slang_usage.json."""
    if not usage_path.exists():
        return {}
    try:
        data = json.loads(usage_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    entries = []
    if isinstance(data, dict) and "entries" in data:
        entries = data["entries"]
    elif isinstance(data, list):
        entries = data
    mp = {}
    for e in entries:
        w = (e.get("word") or "").lower()
        if not w:
            continue
        uses = e.get("uses") or e.get("examples") or []
        if isinstance(uses, list):
            mp[w] = uses
    return mp


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="Path to slang.json")
    parser.add_argument("--usage", default=str(DEFAULT_USAGE), help="Path to slang_usage.json (used if --use-usage)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output slang_similar.json path")
    parser.add_argument("--model", default=_model_name, help="SentenceTransformer model name")
    parser.add_argument("--distance-threshold", type=float, default=0.60,
                        help="HAC distance_threshold for cosine metric (0-2, lower=more clusters). Default 0.60")
    parser.add_argument("--top", type=int, default=5, help="Max similar neighbours per word within cluster")
    parser.add_argument("--min-score", type=float, default=0.55,
                        help="Minimum cosine similarity to keep a neighbour (default 0.55)")
    parser.add_argument("--use-usage", action="store_true",
                        help="Enrich embed text with best usage sentence from slang_usage.json")
    parser.add_argument("--no-usage", dest="use_usage", action="store_false",
                        help="Disable usage enrichment (default)")
    parser.set_defaults(use_usage=False)
    parser.add_argument("--linkage", default="average", choices=["average", "complete", "single"],
                        help="HAC linkage (default average, required for cosine)")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding batch size")
    args = parser.parse_args(argv)

    data_path = Path(args.data)
    out_path = Path(args.out)
    usage_path = Path(args.usage)

    if not data_path.exists():
        parser.error(f"data file not found: {data_path}")

    records = json.loads(data_path.read_text(encoding="utf-8"))
    if isinstance(records, dict) and "entries" in records:
        records = records["entries"]
    if not isinstance(records, list):
        parser.error("slang.json must be a list or {entries: [...]}")

    # Filter to entries with word
    entries = [r for r in records if r.get("word")]
    print(f"Loaded {len(entries)} slang entries from {data_path}")

    usage_map = {}
    if args.use_usage:
        usage_map = load_usage_map(usage_path)
        print(f"Loaded usage map for {len(usage_map)} words from {usage_path} (enrichment ON)")
    else:
        print("Usage enrichment OFF (embed word: definition only)")

    # Build encode texts
    texts = []
    words = []
    for e in entries:
        words.append(e["word"])
        texts.append(build_encode_text(e, use_usage_text=args.use_usage, usage_map=usage_map))

    # Encode
    print(f"Encoding {len(texts)} texts with {args.model} ...")
    model = get_model(args.model)
    import numpy as np

    embeddings = model.encode(
        texts,
        batch_size=args.batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    # embeddings already L2 normalized
    print(f"Embeddings shape: {embeddings.shape}")

    # HAC clustering
    from sklearn.cluster import AgglomerativeClustering

    print(f"Clustering HAC linkage={args.linkage} metric=cosine distance_threshold={args.distance_threshold} ...")
    # sklearn AgglomerativeClustering with cosine requires linkage average/complete/single
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=args.distance_threshold,
        metric="cosine",
        linkage=args.linkage,
        compute_distances=True,
    )
    labels = clustering.fit_predict(embeddings)
    n_clusters = int(labels.max()) + 1 if len(labels) > 0 else 0
    print(f"Found {n_clusters} clusters")

    # Silhouette (cosine) if more than 1 cluster and not all singletons
    silhouette = None
    if n_clusters > 1 and n_clusters < len(labels):
        try:
            from sklearn.metrics import silhouette_score
            # silhouette with cosine needs not precomputed; use embeddings
            silhouette = float(silhouette_score(embeddings, labels, metric="cosine"))
            print(f"Silhouette (cosine): {silhouette:.3f}")
        except Exception as exc:
            print(f"Silhouette failed: {exc}")
            silhouette = None
    else:
        print("Silhouette skipped (k=1 or k=n)")

    # Build cluster -> indices
    from collections import defaultdict
    cluster_to_indices = defaultdict(list)
    for idx, lab in enumerate(labels):
        cluster_to_indices[int(lab)].append(idx)

    # Pairwise cosine similarity matrix (dot since normalized)
    # For efficiency, compute full matrix: embeddings @ embeddings.T
    print("Computing cosine similarities within clusters ...")
    # Use float32 to save memory; 179x179 is tiny but keep pattern
    sim_matrix = embeddings @ embeddings.T  # cosine since normalized
    # Clip for numerical stability
    sim_matrix = sim_matrix.astype(float)

    # Build entries with similar lists
    # Normalize map for form exclusion
    enriched_entries = []
    for idx, entry in enumerate(entries):
        word = entry["word"]
        lab = int(labels[idx])
        member_indices = cluster_to_indices[lab]
        # Collect neighbours in same cluster
        neighbours = []
        for j in member_indices:
            if j == idx:
                continue
            sim = float(sim_matrix[idx, j])
            if sim < args.min_score:
                continue
            neighbours.append((j, sim))
        # Sort by similarity descending, then word
        neighbours.sort(key=lambda x: (-x[1], words[x[0]].lower()))
        top = neighbours[: args.top]
        similar = [
            {"word": words[j], "score": round(float(s), 3)}
            for j, s in top
        ]
        enriched_entries.append({
            "word": word,
            "definition": entry.get("definition", ""),
            "forms": entry.get("forms", [word]),
            "cluster": lab,
            "similar": similar,
        })

    # Build clusters summary
    clusters_summary = []
    for cid in sorted(cluster_to_indices.keys()):
        idxs = cluster_to_indices[cid]
        members = [words[i] for i in idxs]
        members_sorted = sorted(members, key=lambda w: w.lower())
        clusters_summary.append({
            "id": cid,
            "size": len(idxs),
            "members": members_sorted,
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "algorithm": "hac",
        "config": {
            "distance_threshold": args.distance_threshold,
            "linkage": args.linkage,
            "metric": "cosine",
            "top": args.top,
            "min_score": args.min_score,
            "use_usage": args.use_usage,
        },
        "count": len(enriched_entries),
        "n_clusters": n_clusters,
        "silhouette_cosine": round(silhouette, 3) if silhouette is not None else None,
        "clusters": clusters_summary,
        "entries": enriched_entries,
    }

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(enriched_entries)} entries, {n_clusters} clusters to {out_path}")

    # Print brief preview
    preview = 5
    print(f"\nPreview ({preview} entries):")
    for e in enriched_entries[:preview]:
        sims = ", ".join(f"{s['word']}({s['score']})" for s in e["similar"]) or "(singleton)"
        print(f"  {e['word']} [cluster {e['cluster']}]: {sims}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
