import os
import uuid
from pathlib import Path
from docxtpl import DocxTemplate
import pypandoc

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def render_docx_rtf(template_docx_path: str, context: dict):
    docx_out = OUTPUT_DIR / f"{uuid.uuid4()}.docx"
    rtf_out = docx_out.with_suffix(".rtf")

    tpl = DocxTemplate(template_docx_path)
    tpl.render(context)
    tpl.save(docx_out.as_posix())

    # Convert to RTF
    pypandoc.convert_file(docx_out.as_posix(), 'rtf', outputfile=rtf_out.as_posix())
    return docx_out.as_posix(), rtf_out.as_posix()
