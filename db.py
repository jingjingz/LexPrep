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
from pathlib import Path
from typing import Any, List

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
# Schema + migrations
# ──────────────────────────────
def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS templates (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            description   TEXT,
            manifest_json TEXT NOT NULL,
            docx_path     TEXT NOT NULL,
            version       INTEGER NOT NULL DEFAULT 1,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cases (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_name     TEXT,
            template_id  INTEGER NOT NULL,
            input_json   TEXT NOT NULL,
            docx_path    TEXT,
            rtf_path     TEXT,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (template_id) REFERENCES templates(id)
        );
        """
    )

    # add doc_name column if an old DB lacks it
    cur.execute("PRAGMA table_info(cases)")
    if "doc_name" not in [row[1] for row in cur.fetchall()]:
        cur.execute("ALTER TABLE cases ADD COLUMN doc_name TEXT")

    # add is_active column to templates (soft-delete flag)
    cur.execute("PRAGMA table_info(templates)")
    if "is_active" not in [row[1] for row in cur.fetchall()]:
        cur.execute("ALTER TABLE templates ADD COLUMN is_active INTEGER DEFAULT 1")

    conn.commit()
    conn.close()
    


# initialize schema when module loads
init_db()


# ──────────────────────────────
# Template helpers
# ──────────────────────────────
def insert_template(
    name: str,
    description: str | None,
    manifest: dict,
    docx_path: str,
) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO templates (name, description, manifest_json, docx_path)
        VALUES (?, ?, ?, ?);
        """,
        (name, description, json.dumps(manifest), docx_path),
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
def insert_case(
    template_id: int,
    inputs: dict[str, Any],
    docx_path: str | None,
    rtf_path: str | None,
    doc_name: str | None,
) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO cases
          (template_id, input_json, docx_path, rtf_path, doc_name)
        VALUES
          (?, ?, ?, ?, ?);
        """,
        (template_id, json.dumps(inputs), docx_path, rtf_path, doc_name),
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
