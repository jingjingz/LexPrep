# renderer.py
"""
Render a DOCX template with python-docxtpl, then convert it to RTF.

* Prefers LibreOffice's `soffice --convert-to rtf` for the highest fidelity.
* Falls back to Pandoc if LibreOffice is not available.
"""

from __future__ import annotations

import subprocess
import shutil
import uuid
from pathlib import Path
from typing import Tuple

from docxtpl import DocxTemplate
import pypandoc   # still needed as a fallback/bridge

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _convert_with_soffice(docx_path: Path, rtf_path: Path) -> None:
    """Use LibreOffice to convert DOCX → RTF (headless)."""
    cmd = [
        "soffice",
        "--headless",
        "--convert-to",
        "rtf:Rich Text Format",
        "--outdir",
        str(rtf_path.parent),
        str(docx_path),
    ]
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _convert_with_pandoc(docx_path: Path, rtf_path: Path) -> None:
    """Fallback conversion using Pandoc."""
    if shutil.which("pandoc") is None:
        raise RuntimeError(
            "DOCX ➜ RTF conversion failed: neither LibreOffice (`soffice`) "
            "nor Pandoc is available on PATH."
        )
    pypandoc.convert_file(str(docx_path), "rtf", outputfile=str(rtf_path))


def render_docx_rtf(
    template_docx_path: str | Path,
    context: dict,
    base_name: str | None = None,
) -> Tuple[str, str]:
    """
    Renders *template_docx_path* with *context* and returns
    paths to (docx_path, rtf_path).
    """
    stem = base_name or str(uuid.uuid4())
    docx_out = OUTPUT_DIR / f"{stem}.docx"
    rtf_out = OUTPUT_DIR / f"{stem}.rtf"

    # ------------------------------------------------------------------ DOCX
    tpl = DocxTemplate(str(template_docx_path))
    tpl.render(context)
    tpl.save(docx_out)

    # ------------------------------------------------------------ DOCX → RTF
    try:
        if shutil.which("soffice"):
            _convert_with_soffice(docx_out, rtf_out)
        else:
            _convert_with_pandoc(docx_out, rtf_out)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"LibreOffice conversion failed: {e}") from e

    return str(docx_out), str(rtf_out)
