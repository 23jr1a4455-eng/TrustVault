"""Checking an uploaded file before it is stored. The client's word is never trusted."""

import hashlib
import io
import os
import re
import zipfile
from dataclasses import dataclass

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_MULTIPART_OVERHEAD_BYTES = 1_000_000
MAX_ZIP_ENTRIES = 5000
MAX_ZIP_UNCOMPRESSED = 200 * 1024 * 1024  # total size declared inside a DOCX/XLSX/PPTX
MAX_ZIP_RATIO = 200  # one entry may not claim to be more than 200x its compressed size
MAX_CONTENT_TYPES_BYTES = 1_000_000

KINDS = {
    ".pdf": ("pdf", "application/pdf"),
    ".docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xlsx": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".pptx": ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
}
MAIN_PART = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml", "pptx": "ppt/presentation.xml"}

MESSAGES = {
    "empty": "The file is empty.",
    "too_large": "The file is too large (the limit is 25 MB).",
    "type_not_allowed": "Only PDF, DOCX, XLSX and PPTX files are accepted.",
    "bad_signature": "The file content does not match its type.",
    "macros_not_allowed": "Files with macros are not accepted.",
    "unsafe_archive": "The file could not be accepted.",
}


class UploadRejected(Exception):
    """Raised with a short machine code; `message` is safe to show to the person."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code
        self.message = MESSAGES.get(code, MESSAGES["unsafe_archive"])


@dataclass(frozen=True)
class Inspected:
    kind: str
    safe_name: str
    content_type: str
    size: int
    sha256: str


def clean_filename(name):
    """Keep only a harmless display name: no folders, no control characters."""
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)  # also stops header injection (CR/LF)
    name = re.sub(r'[<>:"|?*]', "_", name).strip(" .")
    stem, ext = os.path.splitext(name)
    return (stem[:140] or "document") + ext.lower()


def inspect_upload(filename, data):
    """Return what the file really is, or raise UploadRejected."""
    if not data:
        raise UploadRejected("empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected("too_large")
    safe_name = clean_filename(filename)
    extension = os.path.splitext(safe_name)[1]
    if extension not in KINDS:
        raise UploadRejected("type_not_allowed")
    kind, content_type = KINDS[extension]
    if kind == "pdf":
        if not data.startswith(b"%PDF-"):
            raise UploadRejected("bad_signature")
    else:
        _check_office_archive(kind, data)
    return Inspected(kind, safe_name, content_type, len(data), hashlib.sha256(data).hexdigest())


def _check_office_archive(kind, data):
    """DOCX, XLSX and PPTX are zip files. We never unpack them on the server, but we
    refuse archives that look like bombs, that try odd paths, or that carry macros."""
    if not data.startswith(b"PK\x03\x04"):
        raise UploadRejected("bad_signature")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        entries = archive.infolist()
    except zipfile.BadZipFile:
        raise UploadRejected("bad_signature")
    if len(entries) > MAX_ZIP_ENTRIES:
        raise UploadRejected("unsafe_archive")
    names, total = set(), 0
    for entry in entries:
        name = entry.filename
        if name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/"):
            raise UploadRejected("unsafe_archive")
        if entry.flag_bits & 0x1:  # encrypted entry
            raise UploadRejected("unsafe_archive")
        total += entry.file_size
        if total > MAX_ZIP_UNCOMPRESSED:
            raise UploadRejected("unsafe_archive")
        if entry.file_size and (
            entry.compress_size == 0 or entry.file_size / entry.compress_size > MAX_ZIP_RATIO
        ):
            raise UploadRejected("unsafe_archive")
        if name.lower().endswith("vbaproject.bin"):
            raise UploadRejected("macros_not_allowed")
        names.add(name)
    if "[Content_Types].xml" not in names or MAIN_PART[kind] not in names:
        raise UploadRejected("bad_signature")
    info = archive.getinfo("[Content_Types].xml")
    if info.file_size > MAX_CONTENT_TYPES_BYTES:
        raise UploadRejected("unsafe_archive")
    if b"macroEnabled" in archive.read(info):
        raise UploadRejected("macros_not_allowed")
