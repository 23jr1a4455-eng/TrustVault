import uuid
from datetime import timedelta

import pytest
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from vault.authorization import authorize
from vault.models import AuditEvent, Document, Grant

pytestmark = pytest.mark.django_db


def url(name, document):
    return reverse(name, kwargs={"doc_id": document.pk})


def test_granted_reader_can_open(cast, letter, client_for):
    response = client_for(cast.ravi).get(url("document_detail", letter))
    assert response.status_code == 200
    assert "Salary letter - Ravi" in response.content.decode()


def test_owner_can_open_own_document(cast, letter, client_for):
    assert client_for(cast.priya).get(url("document_detail", letter)).status_code == 200


def test_other_user_gets_404_for_unreadable_document(cast, letter, client_for):  # A-01
    assert client_for(cast.sunil).get(url("document_detail", letter)).status_code == 404


def test_nonexistent_and_unreadable_look_identical(cast, letter, client_for):  # A-05
    client = client_for(cast.sunil)
    unreadable = client.get(url("document_detail", letter))
    missing = client.get(reverse("document_detail", kwargs={"doc_id": uuid.uuid4()}))
    assert unreadable.status_code == missing.status_code == 404
    assert unreadable.content == missing.content


def test_owner_cannot_access_other_owners_document(cast, letter, client_for):  # A-04
    assert client_for(cast.anita).get(url("document_detail", letter)).status_code == 404


def test_admin_cannot_read_ungranted_document(cast, letter, client_for):  # A-09
    assert client_for(cast.meena).get(url("document_detail", letter)).status_code == 404


def test_reader_cannot_edit_or_delete(cast, letter, client_for):  # A-03
    client = client_for(cast.ravi)
    assert client.post(url("document_edit", letter), {"title": "Hacked"}).status_code == 404
    assert client.post(url("document_delete", letter)).status_code == 404
    letter.refresh_from_db()
    assert letter.title == "Salary letter - Ravi"
    assert letter.deleted_at is None


def test_editor_can_edit_but_not_delete(cast, letter, client_for):
    Grant.objects.filter(document=letter, user=cast.ravi).update(level="edit")
    client = client_for(cast.ravi)
    response = client.post(url("document_edit", letter), {"title": "Updated", "category": "HR"})
    assert response.status_code == 302
    letter.refresh_from_db()
    assert letter.title == "Updated"
    assert client.post(url("document_delete", letter)).status_code == 404
    letter.refresh_from_db()
    assert letter.deleted_at is None


def test_owner_can_edit_and_delete(cast, letter, client_for):
    client = client_for(cast.priya)
    assert client.post(url("document_edit", letter), {"title": "Renamed"}).status_code == 302
    assert client.post(url("document_delete", letter)).status_code == 302
    letter.refresh_from_db()
    assert letter.deleted_at is not None


def test_deleted_document_is_gone_for_everyone(cast, letter, client_for):
    Document.objects.filter(pk=letter.pk).update(deleted_at=timezone.now())
    assert client_for(cast.priya).get(url("document_detail", letter)).status_code == 404
    assert client_for(cast.ravi).get(url("document_detail", letter)).status_code == 404


def test_expired_grant_denies(cast, letter, client_for):
    Grant.objects.filter(document=letter, user=cast.ravi).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    assert client_for(cast.ravi).get(url("document_detail", letter)).status_code == 404


def test_revoked_grant_denies_on_the_next_request(cast, letter, client_for):  # R-01
    client = client_for(cast.ravi)
    assert client.get(url("document_detail", letter)).status_code == 200
    Grant.objects.filter(document=letter, user=cast.ravi).update(revoked_at=timezone.now())
    assert client.get(url("document_detail", letter)).status_code == 404


def test_disabled_user_session_stops_working(cast, letter, client_for):  # R-02
    client = client_for(cast.ravi)
    assert client.get(url("document_detail", letter)).status_code == 200
    cast.ravi.is_active = False
    cast.ravi.save()
    response = client.get(url("document_detail", letter))
    assert response.status_code == 302
    assert "/login/" in response["Location"]


def test_anonymous_is_redirected_and_audited(letter, anon_client):
    response = anon_client.get(url("document_detail", letter))
    assert response.status_code == 302
    assert "/login/" in response["Location"]
    event = AuditEvent.objects.get(document_id=letter.pk, allowed=False)
    assert event.actor_id is None
    assert event.detail["reason"] == "anonymous"


def test_edit_ignores_owner_field(cast, letter, client_for):  # A-06
    client = client_for(cast.priya)
    client.post(
        url("document_edit", letter),
        {"title": "Salary letter - Ravi", "owner": cast.sunil.pk, "owner_id": cast.sunil.pk},
    )
    letter.refresh_from_db()
    assert letter.owner_id == cast.priya.pk


def test_unknown_action_is_denied(cast, letter):
    with pytest.raises(Http404):
        authorize(cast.priya, letter.pk, "frobnicate")


def test_list_shows_only_readable_documents(cast, letter, client_for):  # A-08 (basic)
    assert "Salary letter" in client_for(cast.ravi).get(reverse("document_list")).content.decode()
    assert "Salary letter" in client_for(cast.priya).get(reverse("document_list")).content.decode()
    for stranger in (cast.sunil, cast.anita, cast.meena):
        page = client_for(stranger).get(reverse("document_list")).content.decode()
        assert "Salary letter" not in page
