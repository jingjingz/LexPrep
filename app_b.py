# app.py
"""
LexPrep – Streamlit prototype
=============================
• Upload DOCX templates + JSON manifests
• Fill templates to generate legal documents
• SQLite for persistence (see db.py)
"""

import json
import os
from pathlib import Path
import streamlit as st
import tempfile         
from utils import extract_placeholders  


# ── DB + renderer ────────────────────────────────────────────────────────────
from db import (
    init_db,
    insert_template,
    list_templates,
    insert_case,
    list_cases,
    get_conn,
)
from renderer import render_docx_rtf  # must return (docx_path, rtf_path)

# ── paths & DB init ──────────────────────────────────────────────────────────
TEMPLATES_DIR = Path("data/templates")
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
init_db()

# ── global UI CSS ────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* larger, semi-bold field labels … (unchanged) */
    div[data-testid="stTextInput"]  label,
    div[data-testid="stTextArea"]   label,
    div[data-testid="stNumberInput"] label,
    div[data-testid="stFileUploader"] label,
    div[data-testid="stSelectbox"]  label {
        font-size: 1.05rem;
        font-weight: 600;
    }

    /* prettier drag-and-drop zone … (unchanged) */
    .stFileUploader > div[data-testid="stFileUploaderDropzone"] {
        border: 2px dashed #6CACE4;
        background-color: #F0F8FF;
        border-radius: 8px;
        padding: 1.25rem;
    }

    /* prettier “Browse files” button … (unchanged) */
    .stFileUploader button {
        background-color: #6CACE4;
        color: #fff;
        border: none;
        border-radius: 6px;
        padding: 0.35rem 1rem;
    }

    /* ───────────────────────────────────────────────────────────────
       Nicer sidebar navigation pills (reskins st.sidebar.radio)
    ─────────────────────────────────────────────────────────────── */
    /* tighten vertical gap */
    section[data-testid="stSidebar"] .row-widget.stRadio div[role="radiogroup"] {
        gap: .3rem;
    }

    /* hide the tiny circle */
    section[data-testid="stSidebar"] .row-widget.stRadio
        label[data-baseweb="radio"] > div:first-child {
        display: none;
    }

    /* hide the actual <input>, keep it for state */
    section[data-testid="stSidebar"] .row-widget.stRadio input[type="radio"] {
        display: none;
    }

    /* base pill look */
    section[data-testid="stSidebar"] .row-widget.stRadio
        input[type="radio"] + div {            /* sibling that shows the text */
        font-size: 1.15rem;
        font-weight: 600;
        padding: .45rem .9rem;
        border-radius: 8px;
        cursor: pointer;
        transition: background .15s, color .15s;
    }

    /* active pill – UC-blue background, white text */
    section[data-testid="stSidebar"] .row-widget.stRadio
        input[type="radio"]:checked + div {
        background: rgb(108, 172, 228) !important;
        color: #fff !important;
    }
    
    </style>
    """,
    unsafe_allow_html=True,
)


# ── helper functions ─────────────────────────────────────────────────────────
def render_fields(fields, parent=""):
    """Recursively render widgets based on manifest."""
    for f in fields:
        key, ftype = f["key"], f["type"]
        label = f.get("label", key).title()
        path  = f"{parent}.{key}" if parent else key
        wkey  = f"w::{path}"

        if ftype in ("text", "textarea"):
            if ftype == "text":
                st.text_input(label, key=wkey)
            else:
                st.text_area(label, key=wkey)

        elif ftype == "repeat":
            count_key = f"{wkey}::__count"
            count = st.number_input(
                f"{label} – How Many?", min_value=1,
                value=int(st.session_state.get(count_key, 1)),
                key=count_key,
            )
            for i in range(int(count)):
                with st.expander(f"{label} #{i+1}", expanded=i == 0):
                    render_fields(f["fields"], f"{path}[{i}]")

def collect_ctx(fields, parent=""):
    """Collect widget values into context dict matching manifest structure."""
    ctx = {}
    for f in fields:
        key, ftype = f["key"], f["type"]
        path  = f"{parent}.{key}" if parent else key
        wkey  = f"w::{path}"

        if ftype in ("text", "textarea"):
            ctx[key] = st.session_state.get(wkey, "")

        elif ftype == "repeat":
            cnt_key = f"{wkey}::__count"
            count = int(st.session_state.get(cnt_key, 1))
            ctx[key] = [
                collect_ctx(f["fields"], f"{path}[{i}]") for i in range(count)
            ]
    return ctx

import re
def _slug(s: str) -> str:
    """alnum-and-dash slug for filenames"""
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()


# ── sidebar navigation ───────────────────────────────────────────────────────
PAGES = ["Create Template", "Create Case / Fill Form", "Generated Documents"]
page = st.sidebar.radio("Navigation", PAGES)


# ═════════════════════════════════════════════════════════════════════════════
# 1. CREATE TEMPLATE
# ═════════════════════════════════════════════════════════════════════════════
if page == "Create Template":
    st.header("Upload a New Template")

    # ① basic metadata
    t_name = st.text_input("Template Name")
    t_docx = st.file_uploader("Upload DOCX Template", type=["docx"])
    t_desc = st.text_area("Description (Optional)")

    # ② auto-extract placeholders as soon as a DOCX is chosen
    default_manifest_json = ""
    if t_docx is not None:
        # read once into memory so we can both parse & later save
        file_bytes = t_docx.read()

        # write to a temp file for python-docx
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        placeholder_keys = extract_placeholders(tmp_path)

        # helper to turn snake_case into "Title Case"
        def prettify(s: str) -> str:
            return (
                s.replace("[]", "")
                 .replace(".", " ")
                 .replace("_", " ")
                 .title()
            )

        # build a draft manifest
        simple_fields = []
        repeat_groups = {}

        for k in placeholder_keys:
            if "[]." in k:
                root, sub = k.split("[].", 1)
                repeat_groups.setdefault(root, []).append(sub)
            else:
                simple_fields.append(
                    {"key": k, "label": prettify(k), "type": "text"}
                )

        manifest_fields = simple_fields.copy()
        for root, subs in repeat_groups.items():
            manifest_fields.append(
                {
                    "key": root,
                    "type": "repeat",
                    "fields": [
                        {"key": sub, "label": prettify(sub), "type": "text"}
                        for sub in subs
                    ],
                }
            )

        default_manifest_json = json.dumps(
            {"title": t_name or "Untitled", "fields": manifest_fields},
            indent=2,
        )

    # ③ let user review / tweak the JSON (pre-filled if we got one)
    st.markdown("#### Manifest (auto-generated — edit if needed)")
    manifest_text = st.text_area(
        label="",
        height=260,
        value=default_manifest_json,
        key="manifest_text",
    )

    # ④ save template
    if st.button("Save Template", type="primary"):
        if t_docx is None:
            st.error("Please upload a DOCX file."); st.stop()

        # parse JSON (user may have edited)
        try:
            manifest = json.loads(manifest_text)
            assert isinstance(manifest.get("fields"), list)
        except Exception as e:
            st.error(f"Manifest JSON error: {e}"); st.stop()

        # store DOCX on disk
        clean_name = (t_name.strip() or f"Template {len(list_templates()) + 1}")
        dst_path = TEMPLATES_DIR / t_docx.name
        dst_path.write_bytes(file_bytes)         # use the bytes we cached

        tid = insert_template(clean_name, t_desc, manifest, dst_path.as_posix())
        st.success(f"Template “{clean_name}” saved (ID {tid}).")

    # ⑤ list existing templates (unchanged from before)
    st.markdown("#### Existing Templates")
    tmpl_rows = list_templates()
    if tmpl_rows:
        header = st.columns([4, 3, 1])
        header[0].markdown("**Template**")
        header[1].markdown("**Uploaded**")
        header[2].markdown("")
        for r in tmpl_rows:
            cols = st.columns([4, 3, 1])
            cols[0].markdown(r["name"])
            cols[1].markdown(r["created_at"])
            if cols[2].button("Delete", key=f"del_{r['id']}"):
                get_conn().execute("DELETE FROM templates WHERE id = ?", (r["id"],))
                get_conn().commit()
                st.experimental_rerun()
    else:
        st.info("No templates uploaded yet.")


# ═════════════════════════════════════════════════════════════════════════════
# 2. CREATE CASE / FILL FORM
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Create Case / Fill Form":
    st.header("Generate a Document From a Template")

    templates = list_templates()
    if not templates:
        st.error("Please upload at least one template first."); st.stop()

    tmpl_names = [t["name"] for t in templates]
    choice_name = st.selectbox("Choose a Template", tmpl_names)
    tmpl_row = next(t for t in templates if t["name"] == choice_name)
    manifest = json.loads(tmpl_row["manifest_json"])

    st.subheader("Fill in the Fields")
    render_fields(manifest["fields"])

    # ── NEW – optional custom title for output doc ───────────────────────────
    doc_name = st.text_input("Document Name (Optional)")

    btn_cols = st.columns(2)
    generate_docx = btn_cols[0].button("Generate DOCX", type="primary")
    generate_rtf  = btn_cols[1].button("Generate RTF",  type="primary")  # was “secondary”

    # if either button pressed, generate both formats once
    if generate_docx or generate_rtf:
        ctx = collect_ctx(manifest["fields"])
        docx_path, rtf_path = render_docx_rtf(tmpl_row["docx_path"], ctx)
        case_id = insert_case(
            tmpl_row["id"],
            ctx,
            docx_path,
            rtf_path,
            doc_name or None,   # new argument
        )
        st.success(f"Generated! Case #{case_id}")

        dl_cols = st.columns(2)
        with open(docx_path, "rb") as fdocx:
            dl_cols[0].download_button(
                "Download DOCX",
                fdocx,
                file_name=Path(docx_path).name,
                key=f"dl_docx_{case_id}",
            )
        with open(rtf_path, "rb") as frtf:
            dl_cols[1].download_button(
                "Download RTF",
                frtf,
                file_name=Path(rtf_path).name,
                key=f"dl_rtf_{case_id}",
            )

# ═════════════════════════════════════════════════════════════════════════════
# 3. GENERATED DOCUMENTS
# ═════════════════════════════════════════════════════════════════════════════
else:  # page == "Generated Documents"
    st.header("Previously Generated Documents")

    cases = list_cases()
    if not cases:
        st.info("No documents generated yet."); st.stop()

    # newest first
    cases = sorted(cases, key=lambda c: c["created_at"], reverse=True)

    header = st.columns([1, 4, 3, 3, 1, 1])
    header[0].markdown("**ID**")
    header[1].markdown("**Document Name**")
    header[2].markdown("**Template Type**")
    header[3].markdown("**Date & Time**")
    header[4].markdown("**DOCX**")
    header[5].markdown("**RTF**")

    for c in cases:
        cols = st.columns([1, 4, 3, 3, 1, 1])
        cols[0].markdown(str(c["id"]))

        doc_name_disp = (
            c["doc_name"] if "doc_name" in c.keys() and c["doc_name"] else f"Case {c['id']}"
        )
        cols[1].markdown(doc_name_disp)
        cols[2].markdown(c["template_name"])
        cols[3].markdown(c["created_at"])

        # icon-only download buttons if files exist
        if os.path.exists(c["docx_path"]):
            with open(c["docx_path"], "rb") as fd:
                cols[4].download_button(
                    "📄", fd,
                    file_name=Path(c["docx_path"]).name,
                    key=f"docx_{c['id']}",
                )
        else:
            cols[4].markdown("—")

        if os.path.exists(c["rtf_path"]):
            with open(c["rtf_path"], "rb") as fr:
                cols[5].download_button(
                    "📝", fr,
                    file_name=Path(c["rtf_path"]).name,
                    key=f"rtf_{c['id']}",
                )
        else:
            cols[5].markdown("—")
