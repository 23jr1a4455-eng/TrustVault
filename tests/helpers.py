"""Builders for small, valid test files."""

import io
import zipfile

from vault.sample_files import demo_pdf

MAIN_PART = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml", "pptx": "ppt/presentation.xml"}


def pdf_bytes(text="test document"):
    return demo_pdf(text)


def office_bytes(kind="docx", extra=None, content_types=b"<Types/>", compression=zipfile.ZIP_DEFLATED):
    """A tiny but structurally valid DOCX / XLSX / PPTX. `extra` adds more zip entries."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr(MAIN_PART[kind], b"<xml>hello</xml>")
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()
