#!/usr/bin/env python3
"""
classify.py — Sub-Phase 2.1: Auto-Classify (The Sorting Hat)

Reads every unprocessed raw capture from raw/, sends content to Groq/Llama 3,
and gets back:
  - PARA category  (Projects | Areas | Resources | Archives)
  - tags           (list of keywords)
  - summary        (one-line description)
  - title          (sanitized, slug-friendly title)

Each classified capture is saved as a Markdown note at:
  wiki/{Category}/{title_slug}.md

with a YAML frontmatter block containing all metadata.
The raw capture's metadata JSON is then marked  "processed": true.
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime

import yaml
from dotenv import load_dotenv
from groq import Groq

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

RAW_DIR  = "raw"
WIKI_DIR = "wiki"

PARA_CATEGORIES = {"Projects", "Areas", "Resources", "Archives"}

# Content will be truncated to this many characters before sending to LLM
# to keep token usage manageable for large web-scrapes.
MAX_CONTENT_CHARS = 6000

GROQ_MODEL = "llama-3.1-8b-instant"   # current Groq free-tier model (llama3-8b-8192 was decommissioned)


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def build_groq_client() -> Groq:
    """Return an authenticated Groq client or exit with a helpful error."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key.lower().startswith("your_"):
        print(
            "ERROR: GROQ_API_KEY is missing or still set to a placeholder.\n"
            "       Add your key to the .env file and try again.",
            file=sys.stderr,
        )
        sys.exit(1)
    return Groq(api_key=api_key)


def classify_with_llm(client: Groq, content: str, source: str, capture_type: str) -> dict:
    """
    Send the raw content to Groq/Llama 3 and parse the structured JSON response.

    Returns a dict with keys: title, category, tags, summary.
    Falls back gracefully if the LLM response cannot be parsed.
    """
    # Trim content to avoid huge prompts
    truncated = content[:MAX_CONTENT_CHARS]
    if len(content) > MAX_CONTENT_CHARS:
        truncated += "\n\n[... content truncated for classification ...]"

    system_prompt = (
        "You are a personal knowledge-management assistant. "
        "Your job is to classify a user's raw capture into the PARA framework and extract metadata.\n\n"
        "PARA Framework:\n"
        "  - Projects  : Active work with a deadline or clear outcome (e.g. a project you are building).\n"
        "  - Areas     : Ongoing responsibilities with no end date (e.g. health, career, finance).\n"
        "  - Resources : Reference material, tutorials, articles, tools to keep for future use.\n"
        "  - Archives  : Completed, inactive, or outdated items.\n\n"
        "Respond ONLY with a valid JSON object — no extra text, no markdown fences. "
        "The JSON must have exactly these four keys:\n"
        '  "title"    : a short, descriptive title (5 words or fewer, suitable for a filename)\n'
        '  "category" : one of "Projects", "Areas", "Resources", "Archives"\n'
        '  "tags"     : a JSON array of 3–6 relevant lowercase keyword strings\n'
        '  "summary"  : one clear sentence describing what this capture is about\n'
    )

    user_prompt = (
        f"Capture type : {capture_type}\n"
        f"Source       : {source}\n\n"
        f"Content:\n{truncated}"
    )

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        raw_response = response.choices[0].message.content.strip()
    except Exception as exc:
        print(f"  [WARN] Groq API error: {exc}", file=sys.stderr)
        return _fallback_classification(source, capture_type)

    # Strip optional markdown fences (```json ... ```)
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_response, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        result = json.loads(cleaned)
        # Validate required keys
        for key in ("title", "category", "tags", "summary"):
            if key not in result:
                raise ValueError(f"Missing key: {key}")
        # Coerce category to valid PARA value
        if result["category"] not in PARA_CATEGORIES:
            result["category"] = "Resources"   # safe default
        # Ensure tags is a list
        if not isinstance(result["tags"], list):
            result["tags"] = [str(result["tags"])]
        return result
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"  [WARN] Could not parse LLM JSON response ({exc}). Using fallback.", file=sys.stderr)
        print(f"  Raw LLM output was: {raw_response[:200]}", file=sys.stderr)
        return _fallback_classification(source, capture_type)


def _fallback_classification(source: str, capture_type: str) -> dict:
    """Return a safe fallback classification when the LLM call fails."""
    return {
        "title":    "Uncategorized Capture",
        "category": "Resources",
        "tags":     [capture_type, "uncategorized"],
        "summary":  f"Raw {capture_type} captured from: {source}",
    }


# ---------------------------------------------------------------------------
# Content reader
# ---------------------------------------------------------------------------

def read_content(metadata: dict) -> str:
    """
    Read the raw text content for a given metadata record.
    Prefers the _extracted.txt file (for PDFs/files), falls back to the main
    raw_file_path.
    """
    # Check for an extracted text file first
    raw_id = metadata["id"]
    extracted_path = os.path.join(RAW_DIR, f"{raw_id}_extracted.txt")
    if os.path.exists(extracted_path):
        try:
            with open(extracted_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            pass

    # Fall back to the raw_file_path recorded in metadata
    raw_path = metadata.get("raw_file_path", "").replace("/", os.sep)
    if os.path.exists(raw_path):
        try:
            with open(raw_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            pass

    return ""


# ---------------------------------------------------------------------------
# Wiki note writer
# ---------------------------------------------------------------------------

def slugify(title: str) -> str:
    """Convert a title string into a lowercase, hyphenated filename-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)       # remove special chars
    slug = re.sub(r"[\s_]+", "-", slug)         # spaces → hyphens
    slug = re.sub(r"-{2,}", "-", slug)          # collapse double hyphens
    return slug.strip("-") or "note"


def save_wiki_note(classification: dict, metadata: dict, content: str) -> str:
    """
    Write a Markdown file to wiki/{Category}/{slug}.md with YAML frontmatter.
    Returns the path of the created file.
    """
    category  = classification["category"]
    title     = classification["title"]
    tags      = classification["tags"]
    summary   = classification["summary"]
    raw_id    = metadata["id"]
    timestamp = metadata.get("timestamp", datetime.utcnow().isoformat() + "Z")
    source    = metadata.get("source", "")

    slug         = slugify(title)
    category_dir = os.path.join(WIKI_DIR, category)
    os.makedirs(category_dir, exist_ok=True)

    # Avoid name collisions: append id suffix if file already exists
    note_path = os.path.join(category_dir, f"{slug}.md")
    if os.path.exists(note_path):
        note_path = os.path.join(category_dir, f"{slug}-{raw_id[:8]}.md")

    # Truncate body for the wiki note (keep it readable)
    body_preview = content[:3000].strip()
    if len(content) > 3000:
        body_preview += "\n\n> *[Content truncated — see raw capture for full text]*"

    frontmatter = {
        "id":        raw_id,
        "title":     title,
        "category":  category,
        "tags":      tags,
        "summary":   summary,
        "source":    source,
        "captured":  timestamp,
        "classified": datetime.utcnow().isoformat() + "Z",
        "processed": True,
    }

    note_content = (
        "---\n"
        + yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        + "---\n\n"
        + f"# {title}\n\n"
        + f"> **Summary:** {summary}\n\n"
        + "## Content\n\n"
        + body_preview
        + "\n\n---\n"
        + "*Auto-classified by SecondSelf · classify.py (Sub-Phase 2.1)*\n"
    )

    with open(note_path, "w", encoding="utf-8") as f:
        f.write(note_content)

    return note_path


# ---------------------------------------------------------------------------
# Metadata updater
# ---------------------------------------------------------------------------

def mark_processed(raw_id: str, classification: dict, wiki_path: str):
    """Update the raw .json metadata to mark capture as processed."""
    meta_path = os.path.join(RAW_DIR, f"{raw_id}.json")
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        metadata["processed"]       = True
        metadata["wiki_note_path"]  = wiki_path.replace("\\", "/")
        metadata["classification"]  = classification
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
    except Exception as exc:
        print(f"  [WARN] Could not update metadata for {raw_id}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def load_raw_captures(only_unprocessed: bool = True) -> list[dict]:
    """
    Scan raw/ and load all metadata JSON files.
    If only_unprocessed=True, skip captures already marked processed=True.
    """
    captures = []
    if not os.path.isdir(RAW_DIR):
        print(f"ERROR: raw/ directory not found at '{RAW_DIR}'.", file=sys.stderr)
        sys.exit(1)

    for filename in sorted(os.listdir(RAW_DIR)):
        if not filename.endswith(".json"):
            continue
        # Skip extracted-text companion files (they don't have .json counterparts with same name)
        meta_path = os.path.join(RAW_DIR, filename)
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue

        # Must have required keys
        if "id" not in meta or "type" not in meta:
            continue

        if only_unprocessed and meta.get("processed", False):
            continue

        captures.append(meta)

    return captures


def run_classify(only_unprocessed: bool = True, dry_run: bool = False):
    """
    Main classification pipeline:
    1. Load unprocessed raw captures.
    2. Read their content.
    3. Classify via Groq/Llama 3.
    4. Write wiki Markdown notes.
    5. Mark originals as processed.
    """
    captures = load_raw_captures(only_unprocessed=only_unprocessed)

    if not captures:
        qualifier = "unprocessed " if only_unprocessed else ""
        print(f"✅  No {qualifier}captures found in raw/. Nothing to classify.")
        return

    print(f"\n[CLASSIFY] The Sorting Hat -- classifying {len(captures)} capture(s)...\n")
    print("-" * 60)

    client = build_groq_client()

    success = 0
    skipped = 0

    for idx, metadata in enumerate(captures, start=1):
        raw_id       = metadata["id"]
        capture_type = metadata.get("type", "unknown")
        source       = metadata.get("source", "unknown")

        print(f"[{idx}/{len(captures)}] {raw_id[:8]}...  type={capture_type}  source={source[:60]}")

        content = read_content(metadata)
        if not content.strip():
            print(f"  [SKIP] Empty content — skipping.")
            skipped += 1
            continue

        classification = classify_with_llm(client, content, source, capture_type)

        print(f"  Category : {classification['category']}")
        print(f"  Tags     : {', '.join(classification['tags'])}")
        print(f"  Summary  : {classification['summary'][:80]}")
        print(f"  Title    : {classification['title']}")

        if not dry_run:
            wiki_path = save_wiki_note(classification, metadata, content)
            mark_processed(raw_id, classification, wiki_path)
            print(f"  [OK] Saved -> {wiki_path}")
        else:
            print(f"  [DRY RUN] Would save to wiki/{classification['category']}/")

        print()
        success += 1

    print("-" * 60)
    print(f"\n[DONE] Classified: {success}  |  Skipped: {skipped}")
    if not dry_run and success > 0:
        print(f"       Wiki notes written to -> {WIKI_DIR}/\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SecondSelf classify.py — Sub-Phase 2.1: Auto-Classify with PARA"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-classify ALL captures, including already-processed ones.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be classified without writing any files.",
    )
    args = parser.parse_args()

    only_unprocessed = not args.all
    run_classify(only_unprocessed=only_unprocessed, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
