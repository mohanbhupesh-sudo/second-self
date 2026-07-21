#!/usr/bin/env python3
"""
link.py — Sub-Phase 2.2: Auto-Link Related Notes (Connect the Dots)

Steps:
  1. Walk wiki/ and collect all Markdown note paths.
  2. Load (or build) the embeddings cache at embeddings.json.
  3. Compute TF-IDF vectors for notes using scikit-learn (zero install overhead,
     no PyTorch / CUDA required — runs on any Python 3.8+ environment).
  4. Compare every note pair via cosine similarity.
  5. For every pair above the threshold, append reciprocal
     "### Related Notes" backlinks at the bottom of each file.

Usage:
    python link.py                  # link notes (default threshold from .env)
    python link.py --rebuild-cache  # force-recompute all embeddings
    python link.py --threshold 0.5  # override similarity threshold
    python link.py --dry-run        # show links that would be inserted, no writes
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

import yaml
from dotenv import load_dotenv
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

WIKI_DIR        = "wiki"
EMBEDDINGS_FILE = "embeddings.json"

DEFAULT_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.45"))

# PARA sub-directories to scan
PARA_DIRS = ["Projects", "Areas", "Resources", "Archives"]

# Marker used to find / replace the Related Notes block
RELATED_HEADER = "### Related Notes"
AUTO_LINK_FOOTER   = "*Auto-linked by SecondSelf · link.py (Sub-Phase 2.2)*"


# ---------------------------------------------------------------------------
# Note discovery & text extraction
# ---------------------------------------------------------------------------

def discover_notes() -> list[dict]:
    """
    Walk wiki/ and return a list of note dicts:
      { path, title, category, id, text }
    Only .md files with valid YAML frontmatter are included.
    """
    notes = []
    for para_dir in PARA_DIRS:
        folder = os.path.join(WIKI_DIR, para_dir)
        if not os.path.isdir(folder):
            continue
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(folder, fname)
            note = _load_note(fpath, para_dir)
            if note:
                notes.append(note)
    return notes


def _load_note(fpath: str, category: str) -> dict | None:
    """Parse a wiki Markdown file; return a note dict or None on failure."""
    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except Exception as exc:
        print(f"  [WARN] Cannot read {fpath}: {exc}", file=sys.stderr)
        return None

    # Extract YAML frontmatter between the first two "---" delimiters
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
    if not fm_match:
        return None   # not a classified note

    try:
        frontmatter = yaml.safe_load(fm_match.group(1))
    except yaml.YAMLError:
        return None

    # Build embedding text: title + summary + tags + body (stripped of markdown)
    title   = str(frontmatter.get("title", Path(fpath).stem))
    summary = str(frontmatter.get("summary", ""))
    tags    = " ".join(frontmatter.get("tags", []))
    body    = raw[fm_match.end():]           # everything after frontmatter
    body    = _strip_markdown(body)

    embed_text = f"{title}. {summary}. {tags}. {body[:2000]}"

    return {
        "path":     fpath,
        "title":    title,
        "category": category,
        "id":       str(frontmatter.get("id", Path(fpath).stem)),
        "text":     embed_text,
        "raw":      raw,          # full file content for backlink insertion
    }


def _strip_markdown(text: str) -> str:
    """Remove common Markdown syntax to get clean text for embedding."""
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)   # headings
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)           # bold/italic
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)         # links
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)                # code
    text = re.sub(r">\s+", "", text)                              # blockquotes
    text = re.sub(r"\n{3,}", "\n\n", text)                       # blank lines
    return text.strip()


# ---------------------------------------------------------------------------
# Embeddings cache
# ---------------------------------------------------------------------------

def load_embeddings_cache() -> dict:
    """Load the embeddings JSON cache, or return an empty dict."""
    if os.path.exists(EMBEDDINGS_FILE):
        try:
            with open(EMBEDDINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_embeddings_cache(cache: dict):
    """Persist the embeddings cache to disk."""
    with open(EMBEDDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def _cache_key(note: dict) -> str:
    """Stable cache key based on note path + file mtime."""
    mtime = os.path.getmtime(note["path"])
    return f"{note['path']}::{mtime}"


def build_tfidf_vectors(notes: list[dict], cache: dict,
                        rebuild: bool = False) -> dict:
    """
    Compute TF-IDF vectors for all notes using scikit-learn.
    Uses the cache to skip unchanged notes, but TF-IDF must be fit on the
    full corpus so we always refit when anything changes.

    Returns a mapping  note_path -> numpy vector.
    """
    # Check if all notes are cached and unchanged
    all_cached = not rebuild and all(
        _cache_key(n) in cache for n in notes
    )

    if all_cached:
        print(f"  All {len(notes)} notes cached — loading vectors from {EMBEDDINGS_FILE}")
        vectors = {}
        for note in notes:
            key = _cache_key(note)
            vectors[note["path"]] = np.array(cache[key]["vector"])
        return vectors

    print(f"  Fitting TF-IDF vectorizer on {len(notes)} notes...")
    texts = [n["text"] for n in notes]

    vectorizer = TfidfVectorizer(
        sublinear_tf=True,
        max_features=10000,
        ngram_range=(1, 2),
        min_df=1,
    )
    tfidf_matrix = vectorizer.fit_transform(texts)   # sparse (n_notes x vocab)

    # Convert each row to a dense vector for caching and comparison
    vectors = {}
    now = datetime.utcnow().isoformat() + "Z"
    for note, row in zip(notes, tfidf_matrix):
        vec = row.toarray()[0]
        vec_list = vec.tolist()
        key = _cache_key(note)
        cache[key] = {
            "path":    note["path"],
            "title":   note["title"],
            "note_id": note["id"],
            "vector":  vec_list,
            "updated": now,
        }
        vectors[note["path"]] = vec

    return vectors


# ---------------------------------------------------------------------------
# Similarity computation
# ---------------------------------------------------------------------------

def pairwise_cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors using sklearn."""
    return float(sklearn_cosine(a.reshape(1, -1), b.reshape(1, -1))[0][0])


def find_related_pairs(notes: list[dict], vectors: dict,
                       threshold: float) -> dict[str, list[dict]]:
    """
    Return a mapping  note_path -> [list of related note dicts above threshold].
    Only includes pairs where similarity >= threshold.
    """
    related: dict[str, list[dict]] = {n["path"]: [] for n in notes}
    n = len(notes)

    for i in range(n):
        for j in range(i + 1, n):
            a = notes[i]
            b = notes[j]
            va = vectors.get(a["path"])
            vb = vectors.get(b["path"])
            if va is None or vb is None:
                continue
            sim = pairwise_cosine(va, vb)
            if sim >= threshold:
                related[a["path"]].append({"note": b, "score": sim})
                related[b["path"]].append({"note": a, "score": sim})

    # Sort each note's related list by descending similarity
    for path in related:
        related[path].sort(key=lambda x: x["score"], reverse=True)

    return related


# ---------------------------------------------------------------------------
# Backlink insertion
# ---------------------------------------------------------------------------

def _related_section(related_notes: list[dict]) -> str:
    """Build the ### Related Notes markdown block."""
    lines = [RELATED_SECTION_MARKER := RELATED_HEADER]
    lines = [RELATED_HEADER]
    for item in related_notes:
        note  = item["note"]
        score = item["score"]
        # Relative markdown link pointing to the sibling/cousin file
        rel_path = os.path.relpath(note["path"], start=WIKI_DIR).replace("\\", "/")
        lines.append(
            f"- [{note['title']}]({rel_path}) "
            f"_(similarity: {score:.2f})_"
        )
    lines.append("")
    lines.append(AUTO_LINK_FOOTER)
    return "\n".join(lines)


def _strip_old_related_section(raw: str) -> str:
    """Remove any existing ### Related Notes block (and everything after it)."""
    # Find the marker from the auto-linker
    marker = "\n\n---\n" + RELATED_HEADER
    idx = raw.find(marker)
    if idx != -1:
        return raw[:idx]
    # Also try without the leading blank lines (edge-case)
    marker2 = "---\n" + RELATED_HEADER
    idx2 = raw.find(marker2)
    if idx2 != -1:
        # Walk back to the newline before ---
        return raw[:max(0, idx2 - 1)]
    return raw


def insert_backlinks(note: dict, related_notes: list[dict], dry_run: bool = False) -> bool:
    """
    Append (or replace) a ### Related Notes section at the bottom of the note file.
    Returns True if the file was changed.
    """
    raw = note["raw"]

    # Strip the old auto-linked footer (from the classify step)
    auto_classify_footer = "\n---\n*Auto-classified by SecondSelf"
    classify_idx = raw.find(auto_classify_footer)
    if classify_idx != -1:
        base = raw[:classify_idx]
    else:
        base = _strip_old_related_section(raw)

    new_section = _related_section(related_notes)
    new_raw = (
        base.rstrip()
        + "\n\n---\n"
        + new_section
        + "\n"
    )

    if new_raw == raw:
        return False   # no change

    if not dry_run:
        with open(note["path"], "w", encoding="utf-8") as f:
            f.write(new_raw)

    return True


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def run_link(threshold: float = DEFAULT_THRESHOLD,
             rebuild_cache: bool = False,
             dry_run: bool = False):
    """
    Full auto-linking pipeline.
    """
    print(f"\n[LINK] Connect the Dots -- Auto-Linking Related Notes")
    print(f"       Threshold: {threshold}  |  Rebuild cache: {rebuild_cache}  |  Dry run: {dry_run}")
    print("-" * 60)

    # 1. Discover notes
    notes = discover_notes()
    if not notes:
        print(f"  No Markdown notes found in wiki/. Run classify.py first.")
        return
    print(f"  Found {len(notes)} wiki notes across {WIKI_DIR}/")
    print(f"  Engine: TF-IDF + Cosine Similarity (scikit-learn, no GPU/API needed)")

    # 2. Build/update TF-IDF vector cache
    cache = load_embeddings_cache()
    vectors = build_tfidf_vectors(notes, cache, rebuild=rebuild_cache)
    save_embeddings_cache(cache)
    print(f"  Vector cache saved to {EMBEDDINGS_FILE}  ({len(cache)} entries)")

    # 4. Compute similarity pairs
    print(f"  Computing pairwise cosine similarity for {len(notes)} notes...")
    related_map = find_related_pairs(notes, vectors, threshold)

    # 5. Report & insert backlinks
    total_pairs   = sum(len(v) for v in related_map.values()) // 2
    linked_notes  = sum(1 for v in related_map.values() if v)
    skipped_notes = len(notes) - linked_notes

    print(f"  Related pairs found (>= {threshold}): {total_pairs}")
    print()

    changed = 0
    for note in notes:
        rel = related_map[note["path"]]
        if not rel:
            continue

        titles = ", ".join(r["note"]["title"] for r in rel[:3])
        suffix = f" (+{len(rel)-3} more)" if len(rel) > 3 else ""
        print(f"  {note['title'][:50]}")
        print(f"    -> Related: {titles}{suffix}")

        was_changed = insert_backlinks(note, rel, dry_run=dry_run)
        if was_changed:
            action = "[DRY RUN] Would update" if dry_run else "Updated"
            print(f"    {action}: {note['path']}")
            changed += 1
        print()

    print("-" * 60)
    print(f"\n[DONE] Notes linked: {changed}  |  No relations found: {skipped_notes}")
    if not dry_run and changed > 0:
        print(f"       Backlinks written into wiki/ Markdown files")
        print(f"       Embeddings cached at {EMBEDDINGS_FILE}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SecondSelf link.py -- Sub-Phase 2.2: Auto-Link Related Notes"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Cosine similarity threshold (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--rebuild-cache",
        action="store_true",
        help="Force-recompute all embeddings, ignoring existing cache.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be linked without writing any files.",
    )
    args = parser.parse_args()

    run_link(
        threshold=args.threshold,
        rebuild_cache=args.rebuild_cache,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
