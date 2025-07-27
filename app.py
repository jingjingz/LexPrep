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
from pathlib import Path

import streamlit as st

st.markdown(
    """
    <style>
    .lex-title {
        font-family: 'Georgia', serif;
        font-size: 36px;
        font-weight: 600;
        color: #2F2F2F;
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
from db import (
    init_db,
    insert_template,
    list_templates,
    get_template,
    insert_case,
    list_cases,
    delete_case,           
)

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
        path  = f"{parent}.{key}" if parent else key
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


def collect_ctx(schema: list[dict], parent: str = "") -> dict:
    """Collect user inputs from Streamlit session-state into a context dict."""
    ctx = {}
    for field in schema:
        key, ftype = field["key"], field["type"]
        path  = f"{parent}.{key}" if parent else key
        wkey  = f"w::{path}"

        if ftype in ("text", "textarea"):
            ctx[key] = st.session_state.get(wkey, "")

        elif ftype == "repeat":
            cnt_key = f"{wkey}::__count"
            count = int(st.session_state.get(cnt_key, 1))
            ctx[key] = [
                collect_ctx(field["fields"], f"{path}[{i}]")
                for i in range(count)
            ]
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
with st.sidebar:
    st.markdown(
        f'<div class="lex-title">{APP_NAME}</div>'
        f'<div class="lex-ver">{APP_VERSION}</div>',
        unsafe_allow_html=True,
    )
    PAGE = st.radio(
        "Navigation",
        ["Create Template", "Create Case / Fill Form", "Generated Documents"],
    )

# ════════════════════════════════════════════════════════════════════════════
# 1. CREATE TEMPLATE
# ════════════════════════════════════════════════════════════════════════════
if PAGE == "Create Template":
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
            c[1].markdown(row["created_at"])

            # ---------- fixed delete handler ----------
            if c[2].button("Delete", key=f"del_{row['id']}"):
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
elif PAGE == "Create Case / Fill Form":
    st.header("Generate a Document From a Template")

    templates = list_templates()
    if not templates:
        st.error("Please upload at least one template first."); st.stop()

    tmpl_name = st.selectbox("Choose a Template", [t["name"] for t in templates])
    tmpl_row = next(t for t in templates if t["name"] == tmpl_name)
    manifest = json.loads(tmpl_row["manifest_json"])

    st.subheader("Fill in the Fields")
    render_fields(manifest["fields"])

    doc_name = st.text_input("Document Name (Optional)")

    bcols = st.columns(2)
    gen_docx = bcols[0].button("Generate DOCX", type="primary")
    gen_rtf  = bcols[1].button("Generate RTF",  type="primary")

    if gen_docx or gen_rtf:
        ctx = collect_ctx(manifest["fields"])

        # create a base filename stem
        next_case_id = len(list_cases()) + 1  # approximate preview
        base_stem = _slug(doc_name) if doc_name else _slug(f"{tmpl_row['name']}_{next_case_id}")

        docx_path, rtf_path = render_docx_rtf(
            tmpl_row["docx_path"],
            ctx,
            base_name=base_stem,
        )

        case_id = insert_case(
            tmpl_row["id"],
            ctx,
            docx_path,
            rtf_path,
            doc_name or None,
        )

        st.success(f"Generated! Case #{case_id}")

        dcols = st.columns(2)
        with open(docx_path, "rb") as fdocx:
            dcols[0].download_button(
                "Download DOCX",
                fdocx,
                file_name=f"{base_stem}.docx",
                key=f"dl_docx_{case_id}",
            )
        with open(rtf_path, "rb") as frtf:
            dcols[1].download_button(
                "Download RTF",
                frtf,
                file_name=f"{base_stem}.rtf",
                key=f"dl_rtf_{case_id}",
            )

# ════════════════════════════════════════════════════════════════════════════
# 3. GENERATED DOCUMENTS
# ════════════════════════════════════════════════════════════════════════════
else:  # PAGE == "Generated Documents"
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
        cols[3].markdown(c["created_at"])

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
        if cols[6].button("🗑️", key=f"del_{c['id']}"):
            delete_case(c["id"], c["docx_path"], c["rtf_path"])   # remove row + files
            st.experimental_rerun()                               # refresh table
        
