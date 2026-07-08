"""
Database layer — connection, schema initialisation, and migrations.
"""
from __future__ import annotations
import json
import sys

# ChromaDB requires sqlite3 >= 3.35.0. On older systems (Python 3.9 / Ubuntu 20.04)
# the bundled sqlite3 is too old. pysqlite3-binary ships its own up-to-date build.
try:
    import pysqlite3
    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass  # system sqlite3 is new enough (Mac, Ubuntu 22+)

import sqlite3

from core.config import DB_PATH


def get_db_connection() -> sqlite3.Connection:
    """Return a WAL-mode SQLite connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """Create tables and run all pending schema migrations in order."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS db_meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    row = cursor.execute(
        "SELECT value FROM db_meta WHERE key = 'schema_version'"
    ).fetchone()
    schema_version = int(row["value"]) if row else 0

    # ── v1: base documents table ──────────────────────────────────────────────
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id               TEXT PRIMARY KEY,
            filename         TEXT NOT NULL,
            file_size_bytes  INTEGER NOT NULL,
            page_count       INTEGER NOT NULL,
            summary          TEXT,
            tags             TEXT,
            key_findings     TEXT,
            entities         TEXT,
            status           TEXT DEFAULT 'processing',
            error_message    TEXT,
            upload_date      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # ── v2: FTS table with porter tokenizer ──────────────────────────────────
    if schema_version < 2:
        existing_fts: list = []
        try:
            existing_fts = cursor.execute(
                "SELECT id, filename, text, tags, summary FROM documents_fts"
            ).fetchall()
        except Exception:
            pass

        cursor.execute("DROP TABLE IF EXISTS documents_fts")
        for ddl in [
            """CREATE VIRTUAL TABLE documents_fts USING fts5(
                   id UNINDEXED, filename, text, tags, summary,
                   tokenize = 'porter unicode61')""",
            """CREATE VIRTUAL TABLE documents_fts USING fts5(
                   id UNINDEXED, filename, text, tags, summary,
                   tokenize = 'porter ascii')""",
            """CREATE VIRTUAL TABLE documents_fts USING fts4(
                   id, filename, text, tags, summary, tokenize=porter)""",
        ]:
            try:
                cursor.execute(ddl)
                break
            except sqlite3.OperationalError:
                continue

        for r in existing_fts:
            cursor.execute(
                "INSERT INTO documents_fts (id, filename, text, tags, summary) VALUES (?, ?, ?, ?, ?)",
                (r["id"], r["filename"], r["text"], r["tags"], r["summary"]),
            )
        cursor.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('schema_version', '2')"
        )
        print(f"FTS table migrated to porter tokenizer ({len(existing_fts)} docs re-indexed).")

    # ── v3: doc_type column ───────────────────────────────────────────────────
    if schema_version < 3:
        try:
            cursor.execute("ALTER TABLE documents ADD COLUMN doc_type TEXT DEFAULT 'other'")
        except sqlite3.OperationalError:
            pass
        _SYLLABUS = {"Course Syllabus", "Syllabus"}
        _NOTES    = {"Lecture Notes", "Lab Report", "Lab Notes"}
        _ASSIGN   = {"Assignment", "Final Exam", "Midterm Exam", "Exam / Quiz",
                     "Question Bank", "Homework", "Project"}

        def _v3_doc_type(tags: list) -> str:
            s = set(tags)
            if s & _SYLLABUS: return "syllabus"
            if s & _NOTES:    return "notes"
            if s & _ASSIGN:   return "assign"
            return "other"

        rows = cursor.execute(
            "SELECT id, tags FROM documents WHERE status='completed'"
        ).fetchall()
        for row in rows:
            tags = json.loads(row["tags"]) if row["tags"] else []
            cursor.execute(
                "UPDATE documents SET doc_type=? WHERE id=?",
                (_v3_doc_type(tags), row["id"]),
            )
        cursor.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('schema_version', '3')"
        )

    # ── v4: classifications column (multi-perspective AI dimensions) ──────────
    if schema_version < 4:
        try:
            cursor.execute(
                "ALTER TABLE documents ADD COLUMN classifications TEXT DEFAULT '{}'"
            )
        except sqlite3.OperationalError:
            pass
        cursor.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('schema_version', '4')"
        )

    # ── v5: Dynamic Taxonomy Tables ───────────────────────────────────────────
    if schema_version < 5:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS taxonomy_dimensions (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                is_multi_label INTEGER NOT NULL DEFAULT 1,
                ui_color TEXT,
                ui_dim_color TEXT,
                ui_icon TEXT,
                ui_chip_colors TEXT,
                dim_order INTEGER DEFAULT 0
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS taxonomy_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dimension_id TEXT NOT NULL,
                name TEXT NOT NULL,
                FOREIGN KEY(dimension_id) REFERENCES taxonomy_dimensions(id)
            )
            """
        )
        
        


        

        
        

        cursor.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('schema_version', '5')"
        )


    # ── v6: System Settings ───────────────────────────────────────────────────
    if schema_version < 6:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        
        
        
        cursor.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('schema_version', '6')"
        )

    # Mark only OLD stuck docs as failed (> 2h old = truly abandoned, not just slow AI queue)
    cursor.execute(
        "UPDATE documents SET status = 'failed', "
        "error_message = 'Ingestion interrupted by system restart. Please re-upload.' "
        "WHERE status = 'processing' "
        "AND upload_date < datetime('now', '-2 hours')"
    )
    conn.commit()
    conn.close()
