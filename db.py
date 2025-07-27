# db.py
"""
SQLite helper layer for LexPrep
-------------------------------
• Two tables: templates, cases
• Lightweight auto-migration keeps schema up to date
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

# ──────────────────────────────
# Database location
# ──────────────────────────────
DB_PATH = Path("data/app.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────
# Connection helper
# ──────────────────────────────
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ──────────────────────────────
# Schema creation + lightweight migrations
# ──────────────────────────────
def init_db() -> None:
    """Create tables if missing, then add any new columns required by
    newer versions. Safe to call on every start-up."""
    conn = get_conn()
    cur = conn.cursor()

    # 1️⃣  Always make sure the core tables exist
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS templates (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            description   TEXT,
            manifest_json TEXT NOT NULL,
            docx_path     TEXT NOT NULL,
            version       INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT,               -- UTC ISO string
            is_active     INTEGER DEFAULT 1   -- soft-delete flag
        );

        CREATE TABLE IF NOT EXISTS cases (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_name         TEXT,
            template_id      INTEGER NOT NULL,
            input_json       TEXT NOT NULL,
            docx_path        TEXT,
            rtf_path         TEXT,
            created_at       TEXT,            -- UTC ISO string
            FOREIGN KEY (template_id) REFERENCES templates(id)
        );
        """
    )

    # 2️⃣  Add columns that older DB files might lack
    # doc_name in cases
    cur.execute("PRAGMA table_info(cases)")
    if "doc_name" not in [row[1] for row in cur.fetchall()]:
        cur.execute("ALTER TABLE cases ADD COLUMN doc_name TEXT")

    # created_at in templates
    cur.execute("PRAGMA table_info(templates)")
    if "created_at" not in [row[1] for row in cur.fetchall()]:
        cur.execute("ALTER TABLE templates ADD COLUMN created_at TEXT")

    # is_active in templates
    cur.execute("PRAGMA table_info(templates)")
    if "is_active" not in [row[1] for row in cur.fetchall()]:
        cur.execute("ALTER TABLE templates ADD COLUMN is_active INTEGER DEFAULT 1")

    conn.commit()
    conn.close()


# Initialise schema immediately when the module is imported
init_db()



# ──────────────────────────────
# Template helpers
# ──────────────────────────────
def get_template(template_id: int):
    """
    Return the row for a single template.
    """
    conn = get_conn()
    conn.row_factory = sqlite3.Row          # if you haven't set it globally
    cur  = conn.execute(
        "SELECT * FROM templates WHERE id = ?",
        (template_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row




def insert_template(
    name: str,
    description: str | None,
    manifest: dict,
    docx_path: str,
) -> int:
    conn = get_conn()
    cur  = conn.cursor()

    # ISO-8601 in UTC, e.g. “2025-07-27T06:18:42Z”
    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)\
                               .isoformat(timespec="seconds") 

    cur.execute(
        """
        INSERT INTO templates
              (name, description, manifest_json, docx_path, created_at)
        VALUES (?,    ?,          ?,             ?,         ?);
        """,
        (name, description, json.dumps(manifest), docx_path, now_utc),
    )
    conn.commit()
    return cur.lastrowid




def list_templates(active_only: bool = True) -> List[sqlite3.Row]:
    cur = get_conn().cursor()
    if active_only:
        cur.execute(
            "SELECT * FROM templates WHERE is_active = 1 ORDER BY created_at DESC"
        )
    else:  # include archived templates
        cur.execute("SELECT * FROM templates ORDER BY created_at DESC")
    return cur.fetchall()



# ──────────────────────────────
# Case helpers
# ──────────────────────────────
# db.py  – keep everything else the same
def insert_case(
    template_id: int,
    inputs: dict[str, Any],
    docx_path: str | None,
    rtf_path: str | None,
    doc_name: str | None,
) -> int:
    conn = get_conn()
    cur  = conn.cursor()

    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    cur.execute(
        """
        INSERT INTO cases
          (template_id, input_json, docx_path, rtf_path,
           doc_name,    created_at)
        VALUES
          (?,           ?,          ?,         ?, 
           ?,           ?);
        """,
        (template_id,
         json.dumps(inputs),
         docx_path,
         rtf_path,
         doc_name,
         now_utc),          # ← new value goes here
    )
    conn.commit()
    return cur.lastrowid



def list_cases() -> List[sqlite3.Row]:
    cur = get_conn().cursor()
    cur.execute(
        """
        SELECT c.*, t.name AS template_name
        FROM cases c
        JOIN templates t ON t.id = c.template_id
        ORDER BY c.created_at DESC;
        """
    )
    return cur.fetchall()


def delete_case(case_id: int, docx_path: str | None = None, rtf_path: str | None = None):
    """
    Delete one generated‐document record and optionally its files.
    """
    conn = get_conn()
    conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))
    conn.commit()
    conn.close()

    # remove the files from disk (comment these lines if you want to keep them)
    for p in (docx_path, rtf_path):
        if p and Path(p).exists():
            Path(p).unlink(missing_ok=True)

