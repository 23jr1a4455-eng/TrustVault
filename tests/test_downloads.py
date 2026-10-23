import hashlib

import pytest
from django.urls import reverse
from django.utils import timezone

from vault.models import AuditEvent, Document, DocumentFile, Grant

from .helpers import pdf_bytes

pytestmark = pytest.mark.django_db


@pytest.fixture
def stored(letter, cast):
    data = pdf_bytes("salary letter")
    DocumentFile.objects.create(
        document=letter, original_name="salary-letter.pdf", content_type="application/pdf",
        size=len(data), sha256=hashlib.sha256(data).hexdigest(), data=data, uploaded_by=cast.priya,
    )
    return data


def url(document, name="document_download"):
    return reverse(name, kwargs={"doc_id": document.pk})


def test_granted_reader_downloads_the_exact_bytes(cast, letter, stored, client_for):
    response = client_for(cast.ravi).get(url(letter))
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == stored
    assert response["Content-Type"] == "application/pdf"


def test_download_is_a_safe_attachment(cast, letter, stored, client_for):  # F-04
    response = client_for(cast.ravi).get(url(letter))
    assert response["Content-Disposition"].startswith("attachment;")
    assert "salary-letter.pdf" in response["Content-Disposition"]
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in response["Content-Security-Policy"]


def test_strangers_cannot_download(cast, letter, stored, client_for):  # A-01 for files
    for person in (cast.sunil, cast.anita, cast.meena):
        assert client_for(person).get(url(letter)).status_code == 404
    assert AuditEvent.objects.filter(action="document.download", allowed=False).count() == 3


def test_revoked_user_cannot_download_on_the_next_request(cast, letter, stored, client_for):  # R-01
    client = client_for(cast.ravi)
    assert client.get(url(letter)).status_code == 200
    Grant.objects.filter(document=letter, user=cast.ravi).update(revoked_at=timezone.now())
    assert client.get(url(letter)).status_code == 404


def test_deleted_document_cannot_be_downloaded(cast, letter, stored, client_for):
    Document.objects.filter(pk=letter.pk).update(deleted_at=timezone.now())
    assert client_for(cast.priya).get(url(letter)).status_code == 404


def test_document_without_a_file_gives_404(cast, letter, client_for):
    assert client_for(cast.priya).get(url(letter)).status_code == 404


def test_downloads_are_audited(cast, letter, stored, client_for):
    client_for(cast.ravi).get(url(letter))
    event = AuditEvent.objects.get(action="document.download", allowed=True)
    assert event.actor_name == "ravi" and event.document_id == letter.pk


def test_altered_file_bytes_are_detected(cast, letter, stored, client_for):  # F-10
    DocumentFile.objects.filter(document=letter).update(data=b"%PDF-1.4 tampered")
    with pytest.raises(RuntimeError):
        client_for(cast.ravi).get(url(letter))
    assert AuditEvent.objects.filter(action="document.integrity_failure").exists()


def test_document_pages_are_not_cacheable(cast, letter, stored, client_for):  # R-05
    client = client_for(cast.ravi)
    for address in (url(letter), url(letter, "document_detail"), reverse("document_list")):
        assert "no-store" in client.get(address)["Cache-Control"], address


def test_detail_page_shows_download_link_only_to_readers(cast, letter, stored, client_for):
    page = client_for(cast.ravi).get(url(letter, "document_detail")).content.decode()
    assert "salary-letter.pdf" in page and url(letter) in page
