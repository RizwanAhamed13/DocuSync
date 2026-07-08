"""
Fast re-tagger for existing documents (especially SciFact corpus).

Reads documents from SQLite, runs DeBERTa classification on each text snippet
to produce subject/field/doc_type/methodology classifications, then writes back.

Run from the project root:
    python -m scripts.retag_scifact              # retag unclassified docs
    python -m scripts.retag_scifact --force      # retag everything
    python -m scripts.retag_scifact --limit 200  # test on first 200 only
"""
from __future__ import annotations
import argparse
import json
import sys

# Patch pysqlite3 before any other imports
try:
    import pysqlite3
    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass

import sqlite3  # noqa: E402  (needed after pysqlite3 patch)

from core.db import get_db_connection
from services.indexer import _classify_dimensions, _extract_keyword_tags

BATCH = 50  # commit every N rows


def retag(force: bool = False, limit: int | None = None):
    conn = get_db_connection()
    cursor = conn.cursor()

    if force:
        query = (
            "SELECT d.id, d.filename, f.text FROM documents d "
            "LEFT JOIN documents_fts f ON d.id = f.id "
            "WHERE d.status='completed'"
        )
    else:
        query = (
            "SELECT d.id, d.filename, f.text FROM documents d "
            "LEFT JOIN documents_fts f ON d.id = f.id "
            "WHERE d.status='completed' "
            "AND (d.classifications IS NULL OR d.classifications='{}' OR d.classifications='')"
        )

    rows = cursor.execute(query).fetchall()
    if limit:
        rows = rows[:limit]

    total = len(rows)
    print(f"Re-tagging {total} documents…")

    updated = 0
    for i, row in enumerate(rows, 1):
        text = (row["text"] or "")[:1500]
        if not text.strip():
            continue
        try:
            cls = _classify_dimensions(text, row["filename"])
        except Exception as e:
            print(f"  [{i}/{total}] SKIP {row['filename']}: {e}")
            continue

        # Keyword tags: content-specific terms, NOT classification labels
        keyword_tags = _extract_keyword_tags(text, row["filename"])

        # Summary: derive from first 2 sentences of real text
        # (replaces placeholder "SciFact scientific claim document.")
        raw_text = (row["text"] or "")
        import re as _re
        _sents = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", raw_text[:600]) if len(s.strip()) > 20]
        summary = " ".join(_sents[:2])
        if len(summary) > 280:
            summary = summary[:277] + "…"

        cursor.execute(
            "UPDATE documents SET classifications=?, tags=?, summary=? WHERE id=?",
            (json.dumps(cls), json.dumps(keyword_tags), summary, row["id"]),
        )
        updated += 1

        if i % 10 == 0:
            print(f"  [{i}/{total}] {row['filename'][:60]} → {cls.get('subject', [])}")

        if updated % BATCH == 0:
            conn.commit()
            print(f"  Committed {updated}/{total}")

    conn.commit()
    conn.close()
    print(f"\nDone. Updated {updated}/{total} documents.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Retag all docs, not just unclassified")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of docs processed")
    args = parser.parse_args()
    retag(force=args.force, limit=args.limit)
