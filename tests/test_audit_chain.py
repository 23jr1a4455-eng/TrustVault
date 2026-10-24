import threading
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from vault.models import AuditChainHead, AuditEvent
from vault.services import audit
from vault.services.audit import GENESIS, compute_hash, hash_fields_of
from vault.services.audit_chain import parse_anchors, verify_chain

pytestmark = pytest.mark.django_db
postgres_only = pytest.mark.skipif(connection.vendor != "postgresql", reason="needs PostgreSQL")


def add(n, **extra):
    return [audit.record(actor=None, action=f"test.event{i}", allowed=bool(i % 2), detail={"i": i}, **extra) for i in range(n)]


def raw(sql, params=()):
    """Change the table the way a database administrator could: switch the trigger off first."""
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute("ALTER TABLE vault_auditevent DISABLE TRIGGER vault_audit_append_only")
        cursor.execute(sql, params)
        if connection.vendor == "postgresql":
            cursor.execute("ALTER TABLE vault_auditevent ENABLE TRIGGER vault_audit_append_only")


def rebuild_chain(key=None):
    """What an attacker who ALSO has the key could do: recompute every hash after an edit."""
    previous = GENESIS
    for event in AuditEvent.objects.filter(seq__isnull=False).order_by("seq"):
        digest = compute_hash(previous, hash_fields_of(event), key=key)
        raw("UPDATE vault_auditevent SET prev_hash = %s, row_hash = %s WHERE id = %s", [previous, digest, event.pk])
        previous = digest
    AuditChainHead.objects.filter(pk=1).update(last_hash=previous)


def test_rows_form_a_chain_and_verify():
    events = add(5)
    assert [e.seq for e in events] == [1, 2, 3, 4, 5]
    assert events[0].prev_hash == GENESIS
    assert all(events[i].prev_hash == events[i - 1].row_hash for i in range(1, 5))
    report = verify_chain()
    assert report.ok and report.checked == 5


def test_audit_uses_server_time(monkeypatch):
    server_time = datetime(2026, 10, 24, 9, 30, tzinfo=dt_timezone.utc)
    monkeypatch.setattr("vault.services.audit.timezone.now", lambda: server_time)

    event = audit.record(
        actor=None,
        action="test.server_time",
        allowed=True,
        detail={"client_timestamp": "1999-01-01T00:00:00Z"},
    )

    assert event.created_at == server_time


def test_an_empty_log_verifies():
    assert verify_chain().ok


def test_an_edited_row_is_detected():  # U-01, U-02
    add(4)
    raw("UPDATE vault_auditevent SET allowed = %s WHERE seq = 2", [False])
    report = verify_chain()
    assert not report.ok and any("Row 2 was altered" in p for p in report.problems)


def test_a_deleted_row_is_detected():
    add(5)
    raw("DELETE FROM vault_auditevent WHERE seq = 3")
    report = verify_chain()
    assert not report.ok and any("Missing or reordered" in p for p in report.problems)


def test_removing_the_newest_rows_is_detected():
    add(4)
    raw("DELETE FROM vault_auditevent WHERE seq = 4")
    assert not verify_chain().ok


def test_an_inserted_forged_row_is_detected():
    events = add(3)
    last = events[-1]
    raw(
        "INSERT INTO vault_auditevent (created_at, actor_name, action, allowed, detail, seq, prev_hash, row_hash) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        [timezone.now(), "mallory", "document.download", True, "{}", 4, last.row_hash, "f" * 64],
    )
    assert not verify_chain().ok


def test_recomputing_with_plain_sha256_or_a_wrong_key_does_not_help():
    add(4)
    raw("UPDATE vault_auditevent SET allowed = %s WHERE seq = 2", [False])
    rebuild_chain(key="a-key-the-attacker-guessed-0123456789")
    assert not verify_chain().ok  # wrong key: every row mismatches


def test_an_attacker_with_the_key_is_caught_only_by_the_anchors():
    """The honest limit: database owner + secret key can rewrite the chain. The anchors,
    saved outside the app, still expose it."""
    events = add(5)
    anchor = f"2026-10-23T09:00:00Z seq=5 hash={events[-1].row_hash} count=5"
    raw("UPDATE vault_auditevent SET allowed = %s WHERE seq = 2", [False])
    rebuild_chain()  # real key
    assert verify_chain().ok  # the chain alone cannot see it
    report = verify_chain(parse_anchors(anchor))
    assert not report.ok and any("Anchor" in p for p in report.problems)


def test_matching_anchors_pass():
    events = add(3)
    anchor = f"2026-10-23T09:00:00Z seq=3 hash={events[-1].row_hash} count=3"
    report = verify_chain(parse_anchors(anchor))
    assert report.ok and report.anchors_checked == 1


def test_rows_from_before_the_chain_are_counted_not_failed():
    raw("INSERT INTO vault_auditevent (created_at, actor_name, action, allowed, detail, prev_hash, row_hash) "
        "VALUES (%s, '', 'old.event', %s, '{}', '', '')", [timezone.now() - timedelta(days=1), True])
    add(2)
    report = verify_chain()
    assert report.ok and report.legacy == 1 and report.checked == 2


def test_an_unchained_row_added_after_the_chain_started_is_a_problem():
    add(2)
    raw("INSERT INTO vault_auditevent (created_at, actor_name, action, allowed, detail, prev_hash, row_hash) "
        "VALUES (%s, '', 'sneaky', %s, '{}', '', '')", [timezone.now(), True])
    assert not verify_chain().ok


def test_the_model_refuses_bulk_changes():
    add(2)
    with pytest.raises(RuntimeError):
        AuditEvent.objects.all().update(allowed=True)
    with pytest.raises(RuntimeError):
        AuditEvent.objects.all().delete()
    with pytest.raises(RuntimeError):
        AuditEvent.objects.bulk_update(list(AuditEvent.objects.all()), ["allowed"])


def test_the_secret_key_matters(settings):
    event = add(1)[0]
    assert compute_hash(event.prev_hash, hash_fields_of(event)) == event.row_hash
    settings.AUDIT_HMAC_KEY = "another-key-entirely-0123456789abcdef"
    assert compute_hash(event.prev_hash, hash_fields_of(event)) != event.row_hash


def test_log_values_cannot_forge_lines_or_grow_without_limit():  # U-05
    event = audit.record(actor=None, action="auth.login_failed", allowed=False,
                         detail={"username": "x\r\n2026-01-01 ADMIN allowed\x00" + "A" * 500, "deep": {"a": {"b": {"c": {"d": 1}}}}})
    assert "\n" not in event.detail["username"] and "\r" not in event.detail["username"]
    assert len(event.detail["username"]) <= 200
    assert verify_chain().ok


@postgres_only
def test_the_database_itself_refuses_updates_and_deletes():  # U-01
    add(2)
    for sql in ("UPDATE vault_auditevent SET allowed = true", "DELETE FROM vault_auditevent"):
        with pytest.raises(DatabaseError, match="append-only"):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql)
    assert AuditEvent.objects.count() == 2


@postgres_only
@pytest.mark.django_db(transaction=True)
def test_concurrent_writers_never_fork_the_chain():  # U-06
    errors = []

    def writer(worker):
        try:
            for i in range(5):
                audit.record(actor=None, action=f"test.worker{worker}", allowed=True, detail={"i": i})
        except Exception as problem:  # pragma: no cover - reported below
            errors.append(problem)
        finally:
            connection.close()

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert sorted(AuditEvent.objects.values_list("seq", flat=True)) == list(range(1, 41))
    assert verify_chain().ok
