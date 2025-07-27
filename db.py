# db.py
"""
SQLite helper layer for LexPrep
-------------------------------
• Two tables: templates, cases
• Lightweight auto-migration keeps schema in sync (adds columns if missing)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, List

DB_PATH = Path("data/app.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Connection helpers
# ─────────────────────────────────────────────────────────────────────────────
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Schema & lightweight migrations
# ─────────────────────────────────────────────────────────────────────────────
def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    # -- templates table -----------------------------------------------------
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

    # -- cases table ---------------------------------------------------------
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

    # --- lightweight migration: ensure doc_name column exists --------------
    cur.execute("PRAGMA table_info(cases);")
    cols = [row[1] for row in cur.fetchall()]
    if "doc_name" not in cols:
        cur.execute("ALTER TABLE cases ADD COLUMN doc_name TEXT;")

    conn.commit()
    conn.close()


# Initialize schema on import
init_db()


# ─────────────────────────────────────────────────────────────────────────────
# Template helpers
# ─────────────────────────────────────────────────────────────────────────────
def insert_template(
    name: str,
    description: str | None,
    manifest: dict,
    docx_path: str,
) -> int:
    conn, cur = get_conn(), get_conn().cursor()
    cur.execute(
        """
        INSERT INTO templates (name, description, manifest_json, docx_path)
        VALUES (?, ?, ?, ?);
        """,
        (name, description, json.dumps(manifest), docx_path),
    )
    conn.commit()
    return cur.lastrowid


def list_templates() -> List[sqlite3.Row]:
    cur = get_conn().cursor()
    cur.execute("SELECT * FROM templates ORDER BY created_at DESC;")
    return cur.fetchall()


def get_template(template_id: int) -> sqlite3.Row | None:
    cur = get_conn().cursor()
    cur.execute("SELECT * FROM templates WHERE id = ?;", (template_id,))
    return cur.fetchone()


# ─────────────────────────────────────────────────────────────────────────────
# Case helpers
# ─────────────────────────────────────────────────────────────────────────────
def insert_case(
    template_id: int,
    inputs: dict[str, Any],
    docx_path: str | None = None,
    rtf_path: str | None = None,
    doc_name: str | None = None,
) -> int:
    conn, cur = get_conn(), get_conn().cursor()
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


def get_case(case_id: int) -> sqlite3.Row | None:
    cur = get_conn().cursor()
    cur.execute(
        """
        SELECT
            c.*,
            t.name          AS template_name,
            t.manifest_json,
            t.docx_path     AS template_docx_path
        FROM cases c
        JOIN templates t ON t.id = c.template_id
        WHERE c.id = ?;
        """,
        (case_id,),
    )
    return cur.fetchone()
