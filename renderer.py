# renderer.py
"""
Render a DOCX template with docxtpl, then convert it to RTF.

• Fast path: Pandoc  ➜  DOCX → RTF in ~1 s
• Fallback:  LibreOffice (`soffice --convert-to rtf`) for edge-case docs
"""

from __future__ import annotations

import subprocess
import shutil
import uuid
from pathlib import Path
from typing import Tuple

from docxtpl import DocxTemplate
import pypandoc

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HAVE_SOFFICE = shutil.which("soffice") is not None

def _convert_with_pandoc(docx: Path, rtf: Path) -> None:
    if shutil.which("pandoc") is None:
        raise FileNotFoundError("pandoc not on PATH")
    pypandoc.convert_file(str(docx), "rtf", outputfile=str(rtf))
    

# ── NEW helper: DOCX → RTF via Pandoc ─────────────────────────────────────────
def _convert_to_rtf(docx_in: Path, out_dir: Path) -> Path:
    """
    Convert a .docx file to .rtf using Pandoc (already installed on Streamlit
    via packages.txt). Returns the path to the RTF file.
    """
    rtf_out = out_dir / (docx_in.stem + ".rtf")
    pypandoc.convert_file(str(docx_in), "rtf", outputfile=str(rtf_out))
    return rtf_out


def _convert_with_soffice(docx: Path, rtf_dir: Path) -> None:
    if shutil.which("soffice") is None:
        raise FileNotFoundError("LibreOffice soffice not on PATH")
    subprocess.run(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "rtf:Rich Text Format",
            "--outdir",
            str(rtf_dir),
            str(docx),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def render_docx_rtf(
    template_docx_path: str | Path,
    context: dict,
    base_name: str | None = None,
) -> Tuple[str, str]:
    stem = base_name or str(uuid.uuid4())
    docx_out = OUTPUT_DIR / f"{stem}.docx"
    rtf_out  = OUTPUT_DIR / f"{stem}.rtf"

    # ── Fill DOCX ───────────────────────────────────────────────────────────
    tpl = DocxTemplate(str(template_docx_path))
    tpl.render(context)
    tpl.save(docx_out)

    # ── DOCX ➜ RTF  (fast path: Pandoc) ─────────────────────────────────────
    try:
        _convert_with_pandoc(docx_out, rtf_out)

        # sanity-check: if visible text < 100 chars, maybe Pandoc mis-fired
        if _plain_text_len(rtf_out) < 100:
            rtf_out.unlink(missing_ok=True)
            raise RuntimeError("Pandoc produced incomplete RTF")

    except Exception as err:
        logging.warning("Pandoc path failed: %s", err)

        if HAVE_SOFFICE:
            logging.info("Falling back to LibreOffice (‘soffice’) conversion…")
            _convert_with_soffice(docx_out, rtf_out.parent)
        else:
            # Nothing else we can do on Streamlit Cloud → re-raise to surface error
            logging.error("LibreOffice not available – cannot convert DOCX ➜ RTF")
            raise
    
    return str(docx_out), str(rtf_out)
