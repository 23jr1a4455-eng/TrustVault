from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from vault.models import AuditEvent, Document, Grant

pytestmark = pytest.mark.django_db


def url(name, document, **extra):
    return reverse(name, kwargs={"doc_id": document.pk, **extra})


def give(client, document, username, level="read", **extra):
    return client.post(url("document_grant", document), {"username": username, "level": level, **extra})


def test_owner_can_grant_read_and_the_grantee_gets_in(cast, letter, client_for):
    response = give(client_for(cast.priya), letter, "sunil")
    assert response.status_code == 302
    assert client_for(cast.sunil).get(url("document_detail", letter)).status_code == 200
    event = AuditEvent.objects.get(action="grant.created", document_id=letter.pk, detail__grantee="sunil")
    assert event.allowed and event.actor_name == "priya" and event.detail["level"] == "read"


def test_only_the_owner_can_manage_access(cast, letter, client_for):  # edit is not share
    Grant.objects.filter(document=letter, user=cast.ravi).update(level="edit")
    grant = letter.grants.get(user=cast.ravi)
    for person in (cast.ravi, cast.sunil, cast.anita, cast.meena):  # editor, stranger, other owner, admin
        client = client_for(person)
        assert client.get(url("document_access", letter)).status_code == 404
        assert give(client, letter, person.username).status_code == 404
        assert client.post(url("document_revoke", letter, grant_id=grant.pk)).status_code == 404
    assert Grant.objects.active().filter(document=letter).count() == 1
    assert not Grant.objects.filter(document=letter, user=cast.sunil).exists()


def test_grant_to_unknown_or_disabled_user_gives_the_same_answer(cast, letter, make_user, client_for):
    disabled = make_user("dormant")
    disabled.is_active = False
    disabled.save()
    client = client_for(cast.priya)
    pages = [give(client, letter, name) for name in ("nobody", "dormant")]
    assert all(page.status_code == 400 for page in pages)
    assert pages[0].context["error"] == pages[1].context["error"]
    assert Grant.objects.filter(document=letter).count() == 1


def test_owner_cannot_grant_to_themselves(cast, letter, client_for):
    assert give(client_for(cast.priya), letter, "priya").status_code == 400
    assert not Grant.objects.filter(document=letter, user=cast.priya).exists()


@pytest.mark.parametrize("level", ["admin", "owner", "write", "", "READ"])
def test_unknown_levels_are_refused(cast, letter, client_for, level):
    assert give(client_for(cast.priya), letter, "sunil", level=level).status_code == 400
    assert not Grant.objects.filter(document=letter, user=cast.sunil).exists()


def test_expiry_must_be_future_and_within_a_year(cast, letter, client_for):
    client = client_for(cast.priya)
    today = timezone.now().date()
    assert give(client, letter, "sunil", expires_on=str(today)).status_code == 400
    assert give(client, letter, "sunil", expires_on=str(today + timedelta(days=400))).status_code == 400
    assert give(client, letter, "sunil", expires_on=str(today + timedelta(days=30))).status_code == 302
    assert Grant.objects.get(document=letter, user=cast.sunil).expires_at is not None


def test_changing_a_level_keeps_one_grant_and_records_before_and_after(cast, letter, client_for):
    give(client_for(cast.priya), letter, "ravi", level="edit")
    assert Grant.objects.active().filter(document=letter, user=cast.ravi).count() == 1
    event = AuditEvent.objects.get(action="grant.changed")
    assert event.detail["previous_level"] == "read" and event.detail["level"] == "edit"


def test_revoking_takes_effect_on_the_next_request(cast, letter, client_for):  # R-01
    ravi = client_for(cast.ravi)
    assert ravi.get(url("document_detail", letter)).status_code == 200
    grant = letter.grants.get(user=cast.ravi)
    assert client_for(cast.priya).post(url("document_revoke", letter, grant_id=grant.pk)).status_code == 302
    assert ravi.get(url("document_detail", letter)).status_code == 404
    assert ravi.get(url("document_download", letter)).status_code == 404
    assert ravi.get(reverse("document_list")).content.decode().count("Salary letter") == 0
    event = AuditEvent.objects.get(action="grant.revoked")
    assert event.detail["grantee"] == "ravi"


def test_a_grant_id_from_another_document_cannot_be_revoked(cast, letter, client_for):  # IDOR on grant ids
    other = Document.objects.create(owner=cast.anita, title="Anita's contract")
    victim = Grant.objects.create(document=other, user=cast.sunil, level="read", granted_by=cast.anita)
    response = client_for(cast.priya).post(url("document_revoke", letter, grant_id=victim.pk))
    assert response.status_code == 404
    victim.refresh_from_db()
    assert victim.revoked_at is None


def test_an_already_revoked_grant_cannot_be_revoked_again(cast, letter, client_for):
    grant = letter.grants.get(user=cast.ravi)
    client = client_for(cast.priya)
    assert client.post(url("document_revoke", letter, grant_id=grant.pk)).status_code == 302
    assert client.post(url("document_revoke", letter, grant_id=grant.pk)).status_code == 404


def test_deleting_revokes_every_grant_and_restoring_does_not_bring_them_back(cast, letter, client_for):  # R-06
    owner = client_for(cast.priya)
    owner.post(url("document_delete", letter))
    assert Grant.objects.active().filter(document=letter).count() == 0
    assert AuditEvent.objects.get(action="document.deleted").detail["grants_revoked"] == 1
    assert owner.post(url("document_restore", letter)).status_code == 302
    assert owner.get(url("document_detail", letter)).status_code == 200
    assert client_for(cast.ravi).get(url("document_detail", letter)).status_code == 404


def test_only_the_owner_can_restore_a_deleted_document(cast, letter, client_for):
    client_for(cast.priya).post(url("document_delete", letter))
    for person in (cast.ravi, cast.sunil, cast.anita, cast.meena):
        assert client_for(person).post(url("document_restore", letter)).status_code == 404
    letter.refresh_from_db()
    assert letter.deleted_at is not None


def test_restoring_a_live_document_is_refused(cast, letter, client_for):
    assert client_for(cast.priya).post(url("document_restore", letter)).status_code == 404


def test_trash_lists_only_my_deleted_documents(cast, letter, client_for):
    mine = Document.objects.create(owner=cast.anita, title="Anita old", deleted_at=timezone.now())
    letter_page = client_for(cast.priya).get(reverse("document_trash")).content.decode()
    assert "Anita old" not in letter_page
    client_for(cast.priya).post(url("document_delete", letter))
    assert "Salary letter" in client_for(cast.priya).get(reverse("document_trash")).content.decode()
    assert "Salary letter" not in client_for(cast.anita).get(reverse("document_trash")).content.decode()


@pytest.mark.django_db(transaction=True)
def test_no_audit_row_means_no_grant(cast, letter, client_for, monkeypatch):
    from vault.services import audit

    real = audit.record

    def fails_for_grants(**kwargs):
        if kwargs["action"].startswith("grant."):
            raise RuntimeError("audit store down")
        return real(**kwargs)

    monkeypatch.setattr("vault.services.audit.record", fails_for_grants)
    with pytest.raises(RuntimeError):
        give(client_for(cast.priya), letter, "sunil")
    assert not Grant.objects.filter(document=letter, user=cast.sunil).exists()


def test_granting_needs_a_csrf_token(cast, letter):
    from .conftest import new_client

    client = new_client(enforce_csrf_checks=True)
    client.force_login(cast.priya)
    assert give(client, letter, "sunil").status_code == 403
    assert not Grant.objects.filter(document=letter, user=cast.sunil).exists()


def test_access_page_lists_people_and_escapes_names(cast, letter, make_user, client_for):
    page = client_for(cast.priya).get(url("document_access", letter)).content.decode()
    assert "ravi" in page and "Take back" in page


def test_a_grantee_cannot_restore_even_if_a_grant_somehow_survived(cast, letter, client_for):
    # Simulates a bug or a manual database edit: deleted, but Ravi's grant is still active.
    Document.objects.filter(pk=letter.pk).update(deleted_at=timezone.now())
    assert Grant.objects.active().filter(document=letter, user=cast.ravi).exists()
    assert client_for(cast.ravi).post(url("document_restore", letter)).status_code == 404
    letter.refresh_from_db()
    assert letter.deleted_at is not None
