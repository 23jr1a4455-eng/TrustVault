import pytest
from django.urls import reverse

from vault.models import AuditEvent


def url(name, document):
    return reverse(name, kwargs={"doc_id": document.pk})


# transaction=True so the test does NOT hide a rollback inside one big test transaction.
@pytest.mark.django_db(transaction=True)
def test_denied_request_leaves_audit_row(cast, letter, client_for):  # U-03
    response = client_for(cast.sunil).get(url("document_detail", letter))
    assert response.status_code == 404
    event = AuditEvent.objects.get(action="document.read", document_id=letter.pk, allowed=False)
    assert event.actor_name == "sunil"
    assert event.actor_id == cast.sunil.pk


@pytest.mark.django_db(transaction=True)
def test_allowed_access_is_audited(cast, letter, client_for):
    client_for(cast.ravi).get(url("document_detail", letter))
    event = AuditEvent.objects.get(action="document.read", document_id=letter.pk, allowed=True)
    assert event.actor_name == "ravi"


@pytest.mark.django_db(transaction=True)
def test_edit_and_delete_are_audited(cast, letter, client_for):
    client = client_for(cast.priya)
    client.post(url("document_edit", letter), {"title": "New title", "category": "HR"})
    client.post(url("document_delete", letter))
    assert AuditEvent.objects.filter(action="document.updated", allowed=True).exists()
    assert AuditEvent.objects.filter(action="document.deleted", allowed=True).exists()
    updated = AuditEvent.objects.get(action="document.updated")
    assert updated.detail == {"fields": ["title"]}  # field names only, never the values


@pytest.mark.django_db
def test_audit_failure_blocks_access(cast, letter, client_for, monkeypatch):  # U-04
    client = client_for(cast.ravi)

    def audit_store_down(**kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr("vault.services.audit.record", audit_store_down)
    with pytest.raises(RuntimeError):
        client.get(url("document_detail", letter))


@pytest.mark.django_db
def test_audit_events_cannot_be_changed_through_the_model(cast, letter, client_for):
    client_for(cast.sunil).get(url("document_detail", letter))
    event = AuditEvent.objects.filter(allowed=False).first()
    event.detail = {"tampered": True}
    with pytest.raises(RuntimeError):
        event.save()
    with pytest.raises(RuntimeError):
        event.delete()


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["update", "delete", "bulk_update", "bulk_upsert"])
def test_audit_events_cannot_be_changed_through_bulk_queryset_operations(
    cast, letter, client_for, operation
):
    client_for(cast.sunil).get(url("document_detail", letter))
    event = AuditEvent.objects.filter(allowed=False).first()

    with pytest.raises(RuntimeError, match="append-only"):
        if operation == "update":
            AuditEvent.objects.filter(pk=event.pk).update(allowed=True)
        elif operation == "delete":
            AuditEvent.objects.filter(pk=event.pk).delete()
        elif operation == "bulk_update":
            event.allowed = True
            AuditEvent.objects.bulk_update([event], ["allowed"])
        else:
            event.allowed = True
            AuditEvent.objects.bulk_create(
                [event],
                update_conflicts=True,
                update_fields=["allowed"],
                unique_fields=["id"],
            )

    event.refresh_from_db()
    assert event.allowed is False


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["update", "delete"])
def test_audit_base_manager_rejects_mutation_and_deletion(operation):
    event = AuditEvent.objects.create(
        action="document.read",
        allowed=False,
        detail={"level": 0},
    )
    queryset = AuditEvent._base_manager.filter(pk=event.pk)

    with pytest.raises(RuntimeError, match="append-only"):
        if operation == "update":
            queryset.update(allowed=True)
        else:
            queryset.delete()

    event.refresh_from_db()
    assert event.allowed is False
    assert event.detail == {"level": 0}
    assert AuditEvent.objects.filter(pk=event.pk).exists()
