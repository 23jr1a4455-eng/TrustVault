"""Builders for small, valid test files."""

import io
import zipfile

from vault.sample_files import demo_pdf

MAIN_PART = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml", "pptx": "ppt/presentation.xml"}
MAIN_ROOT_XML = {
    "docx": (
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:body><w:p/></w:body></w:document>"
    ),
    "xlsx": (
        b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        b"<sheets/></workbook>"
    ),
    "pptx": (
        b'<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        b"<p:sldIdLst/></p:presentation>"
    ),
}
MAIN_CONTENT_TYPE = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
}


def pdf_bytes(text="test document"):
    return demo_pdf(text)


def office_bytes(kind="docx", extra=None, content_types=None, compression=zipfile.ZIP_DEFLATED):
    """A tiny but structurally valid DOCX / XLSX / PPTX. `extra` adds more zip entries."""
    if content_types is None:
        content_types = (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            f'<Override PartName="/{MAIN_PART[kind]}" ContentType="{MAIN_CONTENT_TYPE[kind]}"/>'
            "</Types>"
        ).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr(MAIN_PART[kind], MAIN_ROOT_XML[kind])
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()
