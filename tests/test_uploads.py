import os

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from vault.models import AuditEvent, Document, DocumentFile
from vault.services import audit as audit_service
from vault.services.uploads import clean_filename

from .helpers import office_bytes, pdf_bytes

pytestmark = pytest.mark.django_db
UPLOAD = "document_upload"


def upload(client, name, data, **fields):
    payload = {"file": SimpleUploadedFile(name, data), **fields}
    return client.post(reverse(UPLOAD), payload)


def rejected_reasons():
    return list(AuditEvent.objects.filter(action="document.upload_rejected").values_list("detail__reason", flat=True))


def test_owner_can_upload_a_pdf(cast, client_for):
    response = upload(client_for(cast.priya), "contract.pdf", pdf_bytes(), title="Contract", category="Legal")
    assert response.status_code == 302
    document = Document.objects.get(title="Contract")
    assert document.owner_id == cast.priya.pk
    stored = DocumentFile.objects.get(document=document)
    assert stored.content_type == "application/pdf"
    assert stored.size == len(pdf_bytes())
    event = AuditEvent.objects.get(action="document.uploaded", document_id=document.pk)
    assert event.allowed and event.detail["sha256"] == stored.sha256


@pytest.mark.parametrize("kind", ["docx", "xlsx", "pptx"])
def test_office_files_are_accepted(cast, client_for, kind):
    assert upload(client_for(cast.priya), f"file.{kind}", office_bytes(kind)).status_code == 302


def test_title_defaults_to_the_file_name(cast, client_for):
    upload(client_for(cast.priya), "Quarterly report.pdf", pdf_bytes())
    assert Document.objects.filter(title="Quarterly report").exists()


def test_viewers_and_admins_cannot_upload(cast, client_for):  # A-03
    for person in (cast.ravi, cast.meena):
        assert upload(client_for(person), "x.pdf", pdf_bytes()).status_code == 404
    assert Document.objects.count() == 0
    assert AuditEvent.objects.filter(action="document.upload", allowed=False).count() == 2


def test_executable_renamed_to_pdf_is_rejected(cast, client_for):  # F-02
    response = upload(client_for(cast.priya), "invoice.pdf", b"MZ\x90\x00 this is a program")
    assert response.status_code == 400
    assert Document.objects.count() == 0
    assert rejected_reasons() == ["bad_signature"]


@pytest.mark.parametrize("name", ["page.html", "image.svg", "tool.exe", "macro.docm", "notes.txt", "noextension"])
def test_other_file_types_are_rejected(cast, client_for, name):
    assert upload(client_for(cast.priya), name, pdf_bytes()).status_code == 400
    assert rejected_reasons() == ["type_not_allowed"]


def test_zip_that_is_not_an_office_file_is_rejected(cast, client_for):
    assert upload(client_for(cast.priya), "x.docx", b"PK\x03\x04 not really a zip").status_code == 400
    assert rejected_reasons() == ["bad_signature"]


def test_office_file_with_macros_is_rejected(cast, client_for):
    data = office_bytes("docx", extra={"word/vbaProject.bin": b"macro"})
    assert upload(client_for(cast.priya), "x.docx", data).status_code == 400
    assert rejected_reasons() == ["macros_not_allowed"]
    data = office_bytes("docx", content_types=b'<Override ContentType="application/vnd.ms-word.document.macroEnabled.12"/>')
    assert upload(client_for(cast.priya), "y.docx", data).status_code == 400


def test_zip_bomb_is_rejected(cast, client_for):  # F-03
    bomb = office_bytes("docx", extra={"word/big.xml": b"0" * (50 * 1024 * 1024)})
    assert len(bomb) < 1_000_000  # tiny on the wire, huge when unpacked
    assert upload(client_for(cast.priya), "bomb.docx", bomb).status_code == 400
    assert rejected_reasons() == ["unsafe_archive"]
    assert Document.objects.count() == 0


def test_archive_with_too_many_entries_is_rejected(cast, client_for, monkeypatch):
    monkeypatch.setattr("vault.services.uploads.MAX_ZIP_ENTRIES", 3)
    data = office_bytes("docx", extra={f"word/{i}.xml": b"x" for i in range(5)})
    assert upload(client_for(cast.priya), "x.docx", data).status_code == 400
    assert rejected_reasons() == ["unsafe_archive"]


def test_archive_that_unpacks_too_large_is_rejected(cast, client_for, monkeypatch):
    monkeypatch.setattr("vault.services.uploads.MAX_ZIP_UNCOMPRESSED", 1000)
    data = office_bytes("docx", extra={"word/blob.bin": os.urandom(2000)}, compression=0)
    assert upload(client_for(cast.priya), "x.docx", data).status_code == 400
    assert rejected_reasons() == ["unsafe_archive"]


def test_archive_with_path_traversal_entry_is_rejected(cast, client_for):
    data = office_bytes("docx", extra={"../../evil.txt": b"x"})
    assert upload(client_for(cast.priya), "x.docx", data).status_code == 400
    assert rejected_reasons() == ["unsafe_archive"]


def test_oversized_file_is_rejected(cast, client_for, monkeypatch):  # F-09
    monkeypatch.setattr("vault.services.uploads.MAX_UPLOAD_BYTES", 100)
    assert upload(client_for(cast.priya), "big.pdf", pdf_bytes()).status_code == 413
    assert rejected_reasons() == ["too_large"]


def test_declared_oversized_multipart_is_rejected(cast, client_for, monkeypatch):
    monkeypatch.setattr("vault.services.uploads.MAX_UPLOAD_BYTES", 100)
    monkeypatch.setattr("vault.services.uploads.MAX_MULTIPART_OVERHEAD_BYTES", 0)

    response = upload(client_for(cast.priya), "large.pdf", pdf_bytes())

    assert response.status_code == 413
    assert Document.objects.count() == 0
    assert rejected_reasons() == ["too_large"]


def test_streaming_upload_handler_stops_after_file_limit(monkeypatch):
    from types import SimpleNamespace

    from django.core.files.uploadhandler import StopUpload

    from vault.upload_handlers import UploadSizeLimitHandler

    monkeypatch.setattr("vault.services.uploads.MAX_UPLOAD_BYTES", 3)
    request = SimpleNamespace()
    handler = UploadSizeLimitHandler(request)

    with pytest.raises(StopUpload):
        handler.receive_data_chunk(b"four", 0)

    assert request.upload_too_large is True


def test_empty_file_is_rejected(cast, client_for):
    assert upload(client_for(cast.priya), "empty.pdf", b"").status_code == 400


def test_file_names_cannot_escape_or_inject_headers():  # F-01, F-05
    assert clean_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert clean_filename("..\\..\\evil.pdf") == "evil.pdf"
    assert clean_filename("bad\r\nname.pdf") == "badname.pdf"
    assert clean_filename("a" * 400 + ".pdf").endswith(".pdf")
    assert len(clean_filename("a" * 400 + ".pdf")) <= 145


def test_uploaded_path_name_is_stored_as_plain_name(cast, client_for):
    upload(client_for(cast.priya), "../../etc/passwd.pdf", pdf_bytes())
    assert DocumentFile.objects.get().original_name == "passwd.pdf"


def test_titles_are_escaped_in_pages(cast, client_for):  # F-06
    client = client_for(cast.priya)
    response = upload(client, "x.pdf", pdf_bytes(), title="<script>alert(1)</script>")
    page = client.get(response["Location"]).content.decode()
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


@pytest.mark.django_db(transaction=True)
def test_no_audit_row_means_no_stored_document(cast, client_for, monkeypatch):  # U-04
    real_record = audit_service.record

    def fails_for_uploads(**kwargs):
        if kwargs["action"] == "document.uploaded":
            raise RuntimeError("audit store down")
        return real_record(**kwargs)

    monkeypatch.setattr("vault.services.audit.record", fails_for_uploads)
    with pytest.raises(RuntimeError):
        upload(client_for(cast.priya), "x.pdf", pdf_bytes())
    assert Document.objects.count() == 0
    assert DocumentFile.objects.count() == 0


def test_upload_needs_a_csrf_token(cast):
    from .conftest import new_client

    client = new_client(enforce_csrf_checks=True)
    client.force_login(cast.priya)
    assert upload(client, "x.pdf", pdf_bytes()).status_code == 403
    assert Document.objects.count() == 0
