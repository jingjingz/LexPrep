# app.py
"""
Streamlit prototype – legal‑document generator
---------------------------------------------
* Template library  : upload DOCX + JSON manifest
* Dynamic form UI   : repeatable groups supported
* Output pipeline   : docxtpl → DOCX → RTF  (see renderer.py)
* Persistence       : SQLite                 (see db.py)
"""

import json
from pathlib import Path
import streamlit as st

from db import (
    init_db,
    insert_template,
    list_templates,
    get_template,
    insert_case,
    list_cases,
)
from renderer import render_docx_rtf

# ----------------------------- one‑time setup ------------------------------
init_db()
st.set_page_config(page_title="Legal Doc Prototype", layout="wide")
TEMPLATES_DIR = Path("templates")
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# ------------------- helpers: render + collect context ---------------------
def render_fields(fields: list[dict], parent_path: str = "") -> None:
    """Render widgets for the list of manifest `fields` (recursively)."""
    for field in fields:
        key   = field["key"]
        label = field.get("label", key)
        ftype = field["type"]
        path  = f"{parent_path}.{key}" if parent_path else key
        wkey  = f"w::{path}"                     # unique widget key

        # ----- scalar -------------------------------------------------------
        if ftype in ("text", "textarea"):
            default = st.session_state.get(wkey, "")
            if ftype == "text":
                st.text_input(label, value=default, key=wkey)
            else:
                st.text_area(label, value=default, key=wkey)

        # ----- repeatable group --------------------------------------------
        elif ftype == "repeat":
            cnt_key = f"{wkey}::__count"         # unique key for the counter
            current = st.number_input(
                f"How many {label.lower()}?",
                min_value=0,
                step=1,
                value=st.session_state.get(cnt_key, 0),
                key=cnt_key,
            )

            for i in range(int(current)):
                with st.expander(f"{label} #{i+1}", expanded=True):
                    render_fields(field["fields"], parent_path=f"{path}[{i}]")

        else:
            st.warning(f"Unsupported field type: {ftype}")


def collect_context(fields: list[dict], parent_path: str = "") -> dict:
    """Build the nested dict for docxtpl from st.session_state."""
    ctx = {}
    for field in fields:
        key   = field["key"]
        ftype = field["type"]
        path  = f"{parent_path}.{key}" if parent_path else key
        wkey  = f"w::{path}"

        if ftype in ("text", "textarea"):
            ctx[key] = st.session_state.get(wkey, "")

        elif ftype == "repeat":
            cnt_key = f"{wkey}::__count"
            count   = int(st.session_state.get(cnt_key, 0))
            ctx[key] = [
                collect_context(field["fields"], parent_path=f"{path}[{i}]")
                for i in range(count)
            ]

    return ctx

# ------------------------------ sidebar nav -------------------------------
PAGES = ["Create Template", "Create Case / Fill Form", "Generated Documents"]
page  = st.sidebar.radio("Navigation", PAGES)

# ============================ 1. CREATE TEMPLATE ===========================
if page == "Create Template":
    st.header("Upload a new template")

    col1, col2 = st.columns(2)
    t_name        = col1.text_input("Template name")
    t_description = col1.text_area("Description (optional)")
    t_docx        = col2.file_uploader("DOCX template", type=["docx"])

    st.markdown("#### Manifest (JSON)")
    manifest_str = st.text_area(
        "Paste the field‑manifest JSON",
        height=250,
        value='{"title":"My Template","fields":[{"key":"title","label":"Title","type":"text"}]}',
    )

    if st.button("Save template", type="primary"):
        if not t_docx:
            st.error("Please upload a DOCX file.")
            st.stop()
        try:
            manifest = json.loads(manifest_str)
            assert isinstance(manifest.get("fields"), list)
        except Exception as e:
            st.error(f"Manifest JSON error: {e}")
            st.stop()

        dest = TEMPLATES_DIR / t_docx.name
        dest.write_bytes(t_docx.read())
        tid = insert_template(t_name, t_description, manifest, dest.as_posix())
        st.success(f"Template saved (id {tid}).")

    st.markdown("#### Existing templates")
    rows = list_templates()
    if rows:
        st.table(
            [{"ID": r["id"], "Name": r["name"], "Created": r["created_at"]} for r in rows]
        )
    else:
        st.info("No templates uploaded yet.")

# ============================ 2. CREATE CASE ==============================
elif page == "Create Case / Fill Form":
    st.header("Generate a document from a template")

    templates = list_templates()
    if not templates:
        st.warning("Upload a template first.")
        st.stop()

    choice = st.selectbox(
        "Choose a template",
        [f'{r["id"]} – {r["name"]}' for r in templates],
    )
    template_id  = int(choice.split(" –")[0])
    template_row = get_template(template_id)
    manifest     = json.loads(template_row["manifest_json"])

    st.subheader("Fill in the fields")
    render_fields(manifest["fields"])            # live‑updating widgets

    if st.button("Generate document", type="primary"):
        context = collect_context(manifest["fields"])
        try:
            docx_path, rtf_path = render_docx_rtf(template_row["docx_path"], context)
        except Exception as e:
            st.error(f"Document generation failed: {e}")
            st.stop()

        case_id = insert_case(template_id, context, docx_path, rtf_path)
        st.success(f"Generated! Case #{case_id}")

        col1, col2 = st.columns(2)
        with open(docx_path, "rb") as f:
            col1.download_button("Download DOCX", f, file_name=f"case_{case_id}.docx")
        with open(rtf_path, "rb") as f:
            col2.download_button("Download RTF", f, file_name=f"case_{case_id}.rtf")

# ======================== 3. GENERATED DOCUMENTS ==========================
elif page == "Generated Documents":
    st.header("All generated cases")

    rows = list_cases()
    if not rows:
        st.info("No cases yet.")
    else:
        for r in rows:
            with st.expander(
                f'Case #{r["id"]} | Template {r["template_name"]} | {r["created_at"]}'
            ):
                st.json(json.loads(r["input_json"]))
                col1, col2 = st.columns(2)
                if r["docx_path"] and Path(r["docx_path"]).exists():
                    with open(r["docx_path"], "rb") as f:
                        col1.download_button(
                            "DOCX", f, file_name=f'case_{r["id"]}.docx'
                        )
                if r["rtf_path"] and Path(r["rtf_path"]).exists():
                    with open(r["rtf_path"], "rb") as f:
                        col2.download_button(
                            "RTF", f, file_name=f'case_{r["id"]}.rtf'
                        )
