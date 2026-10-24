import hashlib

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from vault import views
from vault.models import AuditEvent, DocumentFile, Grant

from .helpers import office_bytes, pdf_bytes

pytestmark = pytest.mark.django_db


@pytest.fixture
def stored(letter, cast):
    data = pdf_bytes("original")
    DocumentFile.objects.create(
        document=letter, original_name="letter.pdf", content_type="application/pdf",
        size=len(data), sha256=hashlib.sha256(data).hexdigest(), data=data, uploaded_by=cast.priya,
    )
    return data


def replace(client, letter, name, data):
    return client.post(
        reverse("document_replace", kwargs={"doc_id": letter.pk}),
        {"file": SimpleUploadedFile(name, data)},
    )


def current_bytes(letter):
    return bytes(DocumentFile.objects.get(document=letter).data)


def test_editor_can_replace_the_file_and_the_audit_keeps_both_hashes(cast, letter, stored, client_for):
    Grant.objects.filter(document=letter, user=cast.ravi).update(level="edit")
    new = pdf_bytes("new version")
    assert replace(client_for(cast.ravi), letter, "v2.pdf", new).status_code == 302
    assert current_bytes(letter) == new
    event = AuditEvent.objects.get(action="document.file_replaced")
    assert event.detail["old_sha256"] == hashlib.sha256(stored).hexdigest()
    assert event.detail["new_sha256"] == hashlib.sha256(new).hexdigest()
    assert event.actor_name == "ravi"


def test_readers_strangers_and_admins_cannot_replace(cast, letter, stored, client_for):
    for person in (cast.ravi, cast.sunil, cast.anita, cast.meena):
        assert replace(client_for(person), letter, "evil.pdf", pdf_bytes("evil")).status_code == 404
    assert current_bytes(letter) == stored


def test_a_revoked_editor_cannot_save(cast, letter, stored, client_for):
    Grant.objects.filter(document=letter, user=cast.ravi).update(level="edit")
    editor = client_for(cast.ravi)
    Grant.objects.filter(document=letter, user=cast.ravi).update(revoked_at=timezone.now())
    assert replace(editor, letter, "late.pdf", pdf_bytes("late")).status_code == 404
    assert current_bytes(letter) == stored


@pytest.mark.django_db(transaction=True)
def test_stale_editor_edit_cannot_undo_owner_delete(cast, letter, client_for, monkeypatch):
    Grant.objects.filter(document=letter, user=cast.ravi).update(level="edit")
    editor = client_for(cast.ravi)
    owner = client_for(cast.priya)
    edit_url = reverse("document_edit", kwargs={"doc_id": letter.pk})
    delete_url = reverse("document_delete", kwargs={"doc_id": letter.pk})
    original_is_valid = views.DocumentEditForm.is_valid

    def validate_then_delete(form):
        valid = original_is_valid(form)
        assert owner.post(delete_url).status_code == 302
        return valid

    monkeypatch.setattr(views.DocumentEditForm, "is_valid", validate_then_delete)
    response = editor.post(edit_url, {"title": "Changed by editor", "category": "private"})

    letter.refresh_from_db()
    assert response.status_code == 404
    assert letter.deleted_at is not None
    assert letter.title == "Salary letter - Ravi"
    assert not AuditEvent.objects.filter(action="document.restored", document_id=letter.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_stale_editor_replace_cannot_write_after_owner_delete(
    cast, letter, stored, client_for, monkeypatch
):
    Grant.objects.filter(document=letter, user=cast.ravi).update(level="edit")
    editor = client_for(cast.ravi)
    owner = client_for(cast.priya)
    delete_url = reverse("document_delete", kwargs={"doc_id": letter.pk})
    original_is_valid = views.FileOnlyForm.is_valid

    def validate_then_delete(form):
        valid = original_is_valid(form)
        assert owner.post(delete_url).status_code == 302
        return valid

    monkeypatch.setattr(views.FileOnlyForm, "is_valid", validate_then_delete)
    response = replace(editor, letter, "late.pdf", pdf_bytes("late"))

    letter.refresh_from_db()
    assert response.status_code == 404
    assert letter.deleted_at is not None
    assert current_bytes(letter) == stored


def test_a_bad_replacement_is_refused_and_the_old_file_stays(cast, letter, stored, client_for):
    owner = client_for(cast.priya)
    assert replace(owner, letter, "x.pdf", b"MZ not a pdf").status_code == 400
    macro = office_bytes("docx", extra={"word/vbaProject.bin": b"m"})
    assert replace(owner, letter, "x.docx", macro).status_code == 400
    assert current_bytes(letter) == stored
    assert AuditEvent.objects.filter(action="document.upload_rejected", document_id=letter.pk).count() == 2


def test_declared_oversized_replacement_is_audited_before_parsing(
    cast, letter, stored, client_for, monkeypatch
):
    monkeypatch.setattr("vault.services.uploads.MAX_UPLOAD_BYTES", 8)
    monkeypatch.setattr("vault.services.uploads.MAX_MULTIPART_OVERHEAD_BYTES", 0)

    response = replace(client_for(cast.priya), letter, "large.pdf", b"x" * 128)

    assert response.status_code == 413
    assert current_bytes(letter) == stored
    event = AuditEvent.objects.get(
        action="document.upload_rejected", document_id=letter.pk
    )
    assert event.allowed is False
    assert event.detail["reason"] == "too_large"


def test_unauthorized_oversized_replacement_is_denied_and_audited(
    cast, letter, stored, client_for, monkeypatch
):
    monkeypatch.setattr("vault.services.uploads.MAX_UPLOAD_BYTES", 8)
    monkeypatch.setattr("vault.services.uploads.MAX_MULTIPART_OVERHEAD_BYTES", 0)

    response = replace(client_for(cast.ravi), letter, "large.pdf", b"x" * 128)

    assert response.status_code == 404
    assert current_bytes(letter) == stored
    assert AuditEvent.objects.filter(
        action="document.edit", allowed=False, document_id=letter.pk
    ).exists()
    assert not AuditEvent.objects.filter(
        action="document.upload_rejected", document_id=letter.pk
    ).exists()


def test_downloads_serve_the_new_file(cast, letter, stored, client_for):
    new = pdf_bytes("brand new")
    replace(client_for(cast.priya), letter, "v2.pdf", new)
    response = client_for(cast.ravi).get(reverse("document_download", kwargs={"doc_id": letter.pk}))
    assert b"".join(response.streaming_content) == new
