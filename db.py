import sqlite3
import json
import os
from pathlib import Path

DB_PATH = Path("data/app.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS templates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      description TEXT,
      manifest_json TEXT NOT NULL,
      docx_path TEXT NOT NULL,
      version INTEGER NOT NULL DEFAULT 1,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cases (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      template_id INTEGER NOT NULL,
      input_json TEXT NOT NULL,
      docx_path TEXT,
      rtf_path TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(template_id) REFERENCES templates(id)
    )
    """)
    conn.commit()
    conn.close()

def insert_template(name, description, manifest, docx_path):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO templates (name, description, manifest_json, docx_path)
        VALUES (?, ?, ?, ?)
    """, (name, description, json.dumps(manifest), docx_path))
    conn.commit()
    return cur.lastrowid

def list_templates():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM templates ORDER BY created_at DESC")
    return cur.fetchall()

def get_template(template_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
    row = cur.fetchone()
    return row

def insert_case(template_id, inputs, docx_path=None, rtf_path=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cases (template_id, input_json, docx_path, rtf_path)
        VALUES (?, ?, ?, ?)
    """, (template_id, json.dumps(inputs), docx_path, rtf_path))
    conn.commit()
    return cur.lastrowid

def list_cases():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.*, t.name as template_name
        FROM cases c
        JOIN templates t ON t.id = c.template_id
        ORDER BY c.created_at DESC
    """)
    return cur.fetchall()

def get_case(case_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.*, t.name as template_name, t.manifest_json, t.docx_path as template_docx_path
        FROM cases c
        JOIN templates t ON t.id = c.template_id
        WHERE c.id = ?
    """, (case_id,))
    return cur.fetchone()

