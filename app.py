# app.py
"""
LexPrep – Streamlit prototype
=============================
• Upload a DOCX template that contains {{ field }} placeholders.
  The app auto-extracts those tokens and builds a draft JSON manifest.
• Fill the form to generate a DOCX **and** an RTF (via LibreOffice or Pandoc).
• All generated cases are stored in SQLite and listed in a history tab.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import streamlit as st
from pathlib import Path

# ── Template location ─────────────────────────────────────────────────────────
TEMPLATE_DIR = Path(__file__).parent / "default_templates"   # ← update path

def load_template(name: str) -> Path:
    """Return the full path to a stored .docx template."""
    return TEMPLATE_DIR / f"{name}.docx"


# ── Calculating correct time zones─────────────────────────────────────────────────────────
from datetime import datetime
from zoneinfo import ZoneInfo          # std-lib ≥3.9
import re

# Detect the browser/host machine’s zone once
LOCAL_TZ = datetime.now().astimezone().tzinfo

def _to_local(iso_ts: str) -> str:
    """
    Convert an ISO-8601 timestamp that the DB stored in UTC
    (e.g. “2025-07-27T07:07:26+00:00” or “…Z”) to the local timezone
    and return a short, readable string like “2025-07-27 00:07”.

    Handles legacy glitches such as “…+00:00Z” and “…+00:00+00:00”.
    """
    try:
        # 1️⃣ Collapse the two bad patterns we introduced earlier
        # “+00:00Z”  → “+00:00”
        # “+00:00+00:00” → “+00:00”
        iso_ts = re.sub(r'\+00:00(?:Z|\+00:00)$', '+00:00', iso_ts)

        # 2️⃣ Normalise a plain “Z” suffix to “+00:00”
        if iso_ts.endswith("Z"):
            iso_ts = iso_ts[:-1] + "+00:00"

        dt = datetime.fromisoformat(iso_ts)

        # 3️⃣ If the string was naïve, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))

        # 4️⃣ Return in local zone, nice format
        return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        # Any parsing hiccup: fall back to the raw text
        return iso_ts


# ── Title style ─────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .lex-title {
        font-family: 'Georgia', serif;
        font-size: 40px;
        font-weight: 600;
        color: #0077C8;
        margin-bottom: 0.2rem;
    }
    .lex-ver {
        font-size: 0.9rem;
        color: #666;
        margin-bottom: 1.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)




# ── project modules ─────────────────────────────────────────────────────────

# ===== database bootstrap =====
from db import (
    init_db,
    insert_template,
    list_templates,
    get_template,
    insert_case,
    list_cases,
    delete_case,
    get_conn,
)

init_db()  # ensure tables exist BEFORE anything else

# -------------------------------------------------------------------------
# Built-in template seeder (only on a fresh DB)

import pathlib

def _load_builtin_templates():
    if list_templates():          # DB already has templates → skip
        return

    tpl_dir = pathlib.Path(__file__).parent / "default_templates"

    builtins = [
        {
            "name": "NDA (Mutual)",
            "file": "nda_template.docx",
            "description": "Standard mutual non-disclosure agreement",
            "manifest": {
                "fields": [
                    {"key": "effective_date",   "type": "date"},
                    {"key": "disclosing_party", "type": "text"},
                    {"key": "receiving_party",  "type": "text"},
                    {"key": "term_years",       "type": "number"},
                ]
            },
        },
        {
            "name": "Residential Lease",
            "file": "lease_template.docx",
            "description": "Simple one-year residential lease",
            "manifest": {
                "fields": [
                    {"key": "landlord_name",    "type": "text"},
                    {"key": "tenant_name",      "type": "text"},
                    {"key": "property_address", "type": "text"},
                    {"key": "lease_start",      "type": "date"},
                    {"key": "lease_end",        "type": "date"},
                    {"key": "rent_amount",      "type": "currency"},
                    {"key": "security_deposit", "type": "currency"},
                ]
            },
        },
        {
            "name": "General Power of Attorney",
            "file": "poa_template.docx",
            "description": "Broad POA with durability clause",
            "manifest": {
                "fields": [
                    {"key": "principal_name",    "type": "text"},
                    {"key": "principal_address", "type": "text"},
                    {"key": "agent_name",        "type": "text"},
                    {"key": "agent_address",     "type": "text"},
                    {"key": "date",              "type": "date"},
                ]
            },
        },
    ]
    

    for t in builtins:
        insert_template(
            name=t["name"],
            description=t["description"],
            manifest=t["manifest"],
            docx_path=str(tpl_dir / t["file"]),
        )

_load_builtin_templates()
# ===== end database bootstrap =====




from renderer import render_docx_rtf
from utils import extract_placeholders

# ── app meta ────────────────────────────────────────────────────────────────
APP_NAME    = "LexPrep"
APP_VERSION = "v0.9.0"

# ── local paths ─────────────────────────────────────────────────────────────
TEMPLATES_DIR = Path("data/templates")
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# ── helper utilities ────────────────────────────────────────────────────────
def _slug(text: str) -> str:
    """Return a safe, lowercase slug suitable for filenames."""
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()


def _make_label(raw: str) -> str:
    """Snake-case → Title Case for default manifest labels."""
    return (
        raw.replace("[]", "")
        .replace(".", " ")
        .replace("_", " ")
        .title()
    )


def render_fields(schema: list[dict], parent: str = "") -> None:
    """Recursively render widgets from the manifest schema."""
    for field in schema:
        key, ftype = field["key"], field["type"]
        label = field.get("label", key).title()
        path  = f"{parent}.{key}"
        wkey  = f"w::{path}"

        if ftype in ("text", "textarea"):
            if ftype == "text":
                st.text_input(label, key=wkey)
            else:
                st.text_area(label, key=wkey)

        elif ftype == "repeat":
            cnt_key = f"{wkey}::__count"
            count = st.number_input(
                f"{label} – How many?", min_value=1,
                value=int(st.session_state.get(cnt_key, 1)),
                key=cnt_key,
            )
            for i in range(int(count)):
                with st.expander(f"{label} #{i + 1}", expanded=i == 0):
                    render_fields(field["fields"], f"{path}[{i}]")


def collect_ctx(schema: list[dict], parent: str) -> dict:
    """
    Rebuild a context dict from Streamlit session-state, using the same
    namespaced keys that render_fields() created.

    Each widget key is   w::<parent>.<field_path>
    where *parent* is the page / template prefix passed in.
    """
    ctx: dict[str, Any] = {}

    for field in schema:
        key   = field["key"]
        ftype = field["type"]

        path  = f"{parent}.{key}"           # always include the prefix
        wkey  = f"w::{path}"                # full widget key in session_state

        # simple scalar types
        if ftype in ("text", "textarea", "number", "date", "currency"):
            ctx[key] = st.session_state.get(wkey)

        # repeat group → recurse for each repetition
        elif ftype == "repeat":
            cnt = int(st.session_state.get(f"{wkey}::__count", 1))
            ctx[key] = [
                collect_ctx(field["fields"], parent=f"{path}[{i}]")
                for i in range(cnt)
            ]

        # fallback for any custom / future field types
        else:
            ctx[key] = st.session_state.get(wkey)

    return ctx


# ── global CSS ──────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* larger, semi-bold form labels */
    div[data-testid="stTextInput"]  label,
    div[data-testid="stTextArea"]   label,
    div[data-testid="stNumberInput"] label,
    div[data-testid="stFileUploader"] label,
    div[data-testid="stSelectbox"]  label {
        font-size: 1.05rem;
        font-weight: 600;
    }

    /* prettier drag-and-drop zone */
    .stFileUploader > div[data-testid="stFileUploaderDropzone"]{
        border: 2px dashed #6CACE4;
        background-color: #F0F8FF;
        border-radius: 8px;
        padding: 1.25rem;
    }

    /* prettier “Browse files” button */
    .stFileUploader button{
        background-color: #6CACE4;
        color: #fff;
        border: none;
        border-radius: 6px;
        padding: 0.35rem 1rem;
    }

    /* ───── sidebar app title / version ───── */
    section[data-testid="stSidebar"] .lex-title{
        font-size: 1.45rem;
        font-weight: 700;
        color: #6CACE4;
        margin-bottom: .15rem;
    }
    section[data-testid="stSidebar"] .lex-ver{
        font-size: .9rem;
        color: #666;
        margin-bottom: .8rem;
    }

    /* ───── prettier radio pills in sidebar ───── */
    section[data-testid="stSidebar"] .row-widget.stRadio div[role="radiogroup"]{gap:.3rem;}
    section[data-testid="stSidebar"] .row-widget.stRadio label[data-baseweb="radio"]>div:first-child{display:none;}
    section[data-testid="stSidebar"] .row-widget.stRadio input[type="radio"]{display:none;}
    section[data-testid="stSidebar"] .row-widget.stRadio input[type="radio"]+div{
        font-size:1.15rem;font-weight:600;padding:.45rem .9rem;border-radius:8px;
        cursor:pointer;transition:background .15s,color .15s;}
    section[data-testid="stSidebar"] .row-widget.stRadio input[type="radio"]:checked+div{
        background:rgb(108,172,228);color:#fff;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ── sidebar navigation ──────────────────────────────────────────────────────
# App name and version display at the top (instead of sidebar)
st.markdown(
    f'<div class="lex-title">{APP_NAME}</div>'
    f'<div class="lex-ver">{APP_VERSION}</div>',
    unsafe_allow_html=True,
)

# Tab-based navigation (mobile-friendly)
tab1, tab2, tab3 = st.tabs([
    "Create Template", 
    "Create Case / Fill Form", 
    "Generated Documents"
])



    

# ════════════════════════════════════════════════════════════════════════════
# 1. CREATE TEMPLATE
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    PAGE_PREFIX = "create_tpl"
    st.header("Upload a New Template")

    # basic metadata
    tpl_name = st.text_input("Template Name")
    tpl_file = st.file_uploader("Upload DOCX Template", type=["docx"])
    tpl_desc = st.text_area("Description (Optional)")

    # auto-extract placeholders once a DOCX is uploaded
    default_manifest = ""
    file_bytes: bytes | None = None
    if tpl_file:
        file_bytes = tpl_file.read()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        keys = extract_placeholders(tmp_path)

        simple: list[dict] = []
        repeats: dict[str, list[str]] = {}

        for k in keys:
            if "[]." in k:
                root, sub = k.split("[].", 1)
                repeats.setdefault(root, []).append(sub)
            else:
                simple.append({"key": k, "label": _make_label(k), "type": "text"})

        manifest_fields = simple.copy()
        for root, subs in repeats.items():
            manifest_fields.append({
                "key": root,
                "type": "repeat",
                "fields": [
                    {"key": sub, "label": _make_label(sub), "type": "text"}
                    for sub in subs
                ],
            })

        default_manifest = json.dumps(
            {"title": tpl_name or "Untitled", "fields": manifest_fields},
            indent=2,
        )

    st.markdown("#### Manifest (auto-generated — edit if needed)")
    manifest_text = st.text_area(
        label="",
        value=default_manifest,
        height=280,
        key="manifest_text",
    )

    if st.button("Save Template", type="primary"):
        if not tpl_file:
            st.error("Please upload a DOCX file."); st.stop()

        try:
            manifest = json.loads(manifest_text)
            assert isinstance(manifest.get("fields"), list)
        except Exception as e:
            st.error(f"Manifest JSON error: {e}"); st.stop()

        clean_name = tpl_name.strip() or f"Template {len(list_templates()) + 1}"
        dst_path = TEMPLATES_DIR / tpl_file.name
        dst_path.write_bytes(file_bytes or b"")

        insert_template(
            clean_name,
            tpl_desc,
            manifest,
            dst_path.as_posix(),
        )
        st.success(f"Template “{clean_name}” saved.")

    # list existing templates
    st.markdown("#### Existing Templates")
    templates = list_templates()
    if not templates:
        st.info("No templates uploaded yet.")
    else:
        hdr = st.columns([4, 3, 1])
        hdr[0].markdown("**Template**")
        hdr[1].markdown("**Uploaded**")
        hdr[2].markdown("")
        for row in templates:
            c = st.columns([4, 3, 1])
            c[0].markdown(row["name"])
            c[1].markdown(_to_local(row["created_at"]))

            # ---------- fixed delete handler ----------
            if c[2].button("Delete", key=f"del_tpl_{row['id']}"):
                conn = get_conn()
                conn.execute(
                    "UPDATE templates SET is_active = 0 WHERE id = ?",
                    (row["id"],),
                )
                conn.commit()
                conn.close()

                st.success(f"Template “{row['name']}” archived. Existing documents retained.")
                st.experimental_rerun()
            
    

# ════════════════════════════════════════════════════════════════════════════
# 2. CREATE CASE / FILL FORM
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Generate a Document From a Template")
    
    # ── Template picker ───────────────────────────────────────────────────────
    templates = list_templates()
    tmpl_map  = {t["name"]: t for t in templates}              # quick lookup
    tmpl_name = st.selectbox("Choose a Template", list(tmpl_map.keys()))

    if tmpl_name:                                              # user picked one
        tmpl_row = tmpl_map[tmpl_name]
        manifest = json.loads(tmpl_row["manifest_json"])

        # prefix every widget key with page + template ID
        PAGE_PREFIX = f"case_{tmpl_row['id']}"

        # ── Fill-in form (values persist) ─────────────────────────────────────
        with st.form("case_form", clear_on_submit=False):
            st.subheader("Fill in the Fields")
            render_fields(manifest["fields"], parent=PAGE_PREFIX)

            doc_name = st.text_input(
                "Document Name (Optional)",
                key=f"{PAGE_PREFIX}.__doc_name"
            )

            col1, col2 = st.columns(2)
            gen_docx = col1.form_submit_button("Generate DOCX", type="primary")
            gen_rtf  = col2.form_submit_button("Generate RTF",  type="primary")

            if gen_docx or gen_rtf:
                # gather inputs using the same prefix
                ctx = collect_ctx(manifest["fields"], parent=PAGE_PREFIX)

                # build a base file-stem
                next_case_id = len(list_cases()) + 1
                base_stem = _slug(doc_name) if doc_name else _slug(
                    f"{tmpl_row['name']}_{next_case_id}"
                )

                docx_path, rtf_path = render_docx_rtf(
                    tmpl_row["docx_path"], ctx, base_name=base_stem
                )

                case_id = insert_case(
                    tmpl_row["id"], ctx, docx_path, rtf_path, doc_name or None
                )

                st.session_state["last_gen"] = {
                    "docx_path": docx_path,
                    "rtf_path":  rtf_path,
                    "base":      base_stem,
                    "case_id":   case_id,
                }
                st.success(f"Generated! Case #{case_id}")

        # ── Download buttons (stay after clicks) ──────────────────────────────
        if "last_gen" in st.session_state:
            g = st.session_state["last_gen"]
            d1, d2 = st.columns(2)

            with open(g["docx_path"], "rb") as fdocx:
                d1.download_button(
                    "Download DOCX",
                    fdocx,
                    file_name=f"{g['base']}.docx",
                    key=f"dl_docx_{g['case_id']}",
                )
            with open(g["rtf_path"], "rb") as frtf:
                d2.download_button(
                    "Download RTF",
                    frtf,
                    file_name=f"{g['base']}.rtf",
                    key=f"dl_rtf_{g['case_id']}",
                )
    
    

# ════════════════════════════════════════════════════════════════════════════
# 3. GENERATED DOCUMENTS
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    PAGE_PREFIX = "gen_docs"
    st.header("Previously Generated Documents")
    
    cases = list_cases()
    if not cases:
        st.info("No documents generated yet."); st.stop()

    h = st.columns([1, 4, 3, 3, 2, 2, 2])   
    h[0].markdown("**ID**")
    h[1].markdown("**Document Name**")
    h[2].markdown("**Template**")
    h[3].markdown("**Date & Time**")
    h[4].markdown("**DOCX**")
    h[5].markdown("**RTF**")
    h[6].markdown("**Delete**")             
    

    for c in cases:
        cols = st.columns([1, 4, 3, 3, 2, 2, 2])   # ← seven columns now
        cols[0].markdown(str(c["id"]))
        display_name = c["doc_name"] or f"Case {c['id']}"
        cols[1].markdown(display_name)
        cols[2].markdown(c["template_name"])
        cols[3].markdown(_to_local(c["created_at"]))

        base = _slug(c["doc_name"]) if c["doc_name"] else _slug(f"{c['template_name']}_{c['id']}")

        # DOCX download
        if os.path.exists(c["docx_path"]):
            with open(c["docx_path"], "rb") as fd:
                cols[4].download_button("📄", fd, file_name=f"{base}.docx", key=f"docx_{c['id']}")
        else:
            cols[4].markdown("—")

        # RTF download
        if os.path.exists(c["rtf_path"]):
            with open(c["rtf_path"], "rb") as fr:
                cols[5].download_button("📝", fr, file_name=f"{base}.rtf", key=f"rtf_{c['id']}")
        else:
            cols[5].markdown("—")

        # Delete button
        # app.py  – inside the Generated Documents loop
        if cols[6].button("🗑️", key=f"del_case_{c['id']}"):
            delete_case(c["id"], c["docx_path"], c["rtf_path"])

            # 🔑 clear the stale “last generated” cache
            if st.session_state.get("last_gen", {}).get("case_id") == c["id"]:
                st.session_state.pop("last_gen")

            st.experimental_rerun()
                                  # refresh table
        
