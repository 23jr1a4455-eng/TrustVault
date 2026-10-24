from datetime import timedelta

import pytest
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from vault.models import AuditEvent, Document, Grant
from vault.services import audit
from vault.services.flags import busiest, find_flags

pytestmark = pytest.mark.django_db


def titles(response):
    return response.content.decode()


def test_admin_can_read_the_activity_log(cast, letter, client_for):
    client_for(cast.sunil).get(reverse("document_detail", kwargs={"doc_id": letter.pk}))
    page = titles(client_for(cast.meena).get(reverse("admin_activity")))
    assert "sunil" in page and "refused" in page and "Salary letter - Ravi" in page


def test_administrators_looking_at_the_log_are_themselves_recorded(cast, client_for):
    client_for(cast.meena).get(reverse("admin_activity"))
    assert AuditEvent.objects.filter(action="admin.admin_activity", allowed=True, actor_name="meena").exists()


def test_non_admins_are_refused_and_recorded(cast, client_for):
    for person in (cast.priya, cast.ravi):
        assert client_for(person).get(reverse("admin_activity")).status_code == 404
    assert AuditEvent.objects.filter(action="admin.admin_activity", allowed=False).count() == 2


@pytest.mark.parametrize(
    ("route_name", "action"),
    [
        ("admin_activity", "admin.admin_activity"),
        ("document_upload", "document.upload"),
    ],
)
def test_anonymous_admin_and_upload_denials_are_recorded(anon_client, route_name, action):
    response = anon_client.get(reverse(route_name))

    assert response.status_code == 302
    assert response["Location"].startswith("/login/?next=")
    assert AuditEvent.objects.filter(
        action=action,
        allowed=False,
        actor_id__isnull=True,
    ).exists()


def test_groups_filter_the_log(cast, letter, client_for):
    client_for(cast.sunil).get(reverse("document_detail", kwargs={"doc_id": letter.pk}))
    client_for(cast.priya).post(reverse("document_grant", kwargs={"doc_id": letter.pk}), {"username": "sunil", "level": "read"})
    admin = client_for(cast.meena)
    permissions = admin.get(reverse("admin_activity"), {"group": "permissions"})
    names = {e.action for e in permissions.context["page"].object_list}
    assert names and all(n.startswith("grant.") or n.startswith("document.") for n in names) and "grant.created" in names
    denied = admin.get(reverse("admin_activity"), {"group": "denied"})
    assert all(not e.allowed for e in denied.context["page"].object_list)
    by_actor = admin.get(reverse("admin_activity"), {"actor": "sunil"})
    assert {e.actor_name for e in by_actor.context["page"].object_list} == {"sunil"}


def test_filters_by_document_and_bad_input_is_harmless(cast, letter, client_for):
    admin = client_for(cast.meena)
    client_for(cast.ravi).get(reverse("document_detail", kwargs={"doc_id": letter.pk}))
    found = admin.get(reverse("admin_activity"), {"document": str(letter.pk)})
    assert {str(e.document_id) for e in found.context["page"].object_list} == {str(letter.pk)}
    for params in ({"document": "nope"}, {"date_from": "x"}, {"group": "'; DROP TABLE"}, {"page": "-1"}):
        assert admin.get(reverse("admin_activity"), params).status_code == 200


def test_log_text_is_escaped_in_the_page(cast, client_for, anon_client):
    anon_client.post(reverse("login"), {"username": "<script>alert(1)</script>", "password": "x"})
    page = titles(client_for(cast.meena).get(reverse("admin_activity"), {"group": "auth"}))
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


def test_the_admin_still_cannot_open_documents(cast, letter, client_for):
    assert client_for(cast.meena).get(reverse("document_detail", kwargs={"doc_id": letter.pk})).status_code == 404


def test_verify_button_reports_a_healthy_and_a_damaged_chain(cast, client_for):
    admin = client_for(cast.meena)
    assert admin.post(reverse("admin_verify")).status_code == 200
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute("ALTER TABLE vault_auditevent DISABLE TRIGGER vault_audit_append_only")
        cursor.execute("UPDATE vault_auditevent SET allowed = %s WHERE seq = 1", [False])
        if connection.vendor == "postgresql":
            cursor.execute("ALTER TABLE vault_auditevent ENABLE TRIGGER vault_audit_append_only")
    response = admin.post(reverse("admin_verify"))
    assert response.status_code == 409 and "NOT intact" in titles(response)
    assert admin.get(reverse("admin_verify")).status_code == 405


# ---- worth noticing
def attempt(client, document, times):
    for _ in range(times):
        client.get(reverse("document_detail", kwargs={"doc_id": document.pk}))


def test_repeated_refusals_are_flagged_but_a_few_are_not(cast, letter, client_for):
    attempt(client_for(cast.sunil), letter, 4)
    assert not [f for f in find_flags() if f.kind == "Repeated refused attempts"]
    attempt(client_for(cast.sunil), letter, 2)
    flag = [f for f in find_flags() if f.kind == "Repeated refused attempts"]
    assert flag and flag[0].who == "sunil" and flag[0].count >= 5


def test_old_events_are_not_flagged(cast, letter, client_for):
    attempt(client_for(cast.sunil), letter, 8)
    assert find_flags()
    assert find_flags(now=timezone.now() + timedelta(days=3)) == []


def test_many_downloads_are_flagged(cast, letter, client_for):
    from .helpers import pdf_bytes
    import hashlib
    from vault.models import DocumentFile
    data = pdf_bytes()
    DocumentFile.objects.create(document=letter, original_name="a.pdf", content_type="application/pdf", size=len(data),
                                sha256=hashlib.sha256(data).hexdigest(), data=data, uploaded_by=cast.priya)
    client = client_for(cast.ravi)
    for _ in range(10):
        client.get(reverse("document_download", kwargs={"doc_id": letter.pk}))
    assert [f for f in find_flags() if f.kind == "Many downloads" and f.who == "ravi"]


def test_repeated_failed_sign_ins_are_flagged(cast, anon_client):
    for _ in range(5):
        anon_client.post(reverse("login"), {"username": "ravi", "password": "wrong"})
    assert [f for f in find_flags() if f.kind == "Repeated failed sign-ins" and f.who == "ravi"]


def test_access_for_a_brand_new_account_is_flagged(cast, letter, client_for):
    client_for(cast.priya).post(reverse("document_grant", kwargs={"doc_id": letter.pk}), {"username": "sunil", "level": "read"})
    assert [f for f in find_flags() if f.kind == "Access given to a brand-new account"]
    assert not find_flags(now=timezone.now() + timedelta(days=30))


def test_a_failed_integrity_check_is_flagged(cast, letter):
    audit.record(actor=cast.ravi, action="document.integrity_failure", allowed=False, document_id=letter.pk)
    assert [f for f in find_flags() if f.kind.startswith("A stored file failed")]


def test_flags_page_loads_for_admins_only(cast, client_for):
    assert client_for(cast.meena).get(reverse("admin_flags")).status_code == 200
    assert client_for(cast.priya).get(reverse("admin_flags")).status_code == 404


def test_busiest_window_arithmetic():
    base = timezone.now()
    times = [base + timedelta(minutes=m) for m in (0, 1, 2, 30, 31)]
    assert busiest(times, 5) == 3 and busiest(times, 60) == 5 and busiest([], 5) == 0


# ---- user management
def login_session(client_for, person):
    client = client_for(person)
    assert client.get(reverse("document_list")).status_code == 200
    return client


def test_disabling_a_user_ends_every_session_at_once(cast, letter, client_for):  # R-02, the "left the company" case
    ravi = login_session(client_for, cast.ravi)
    admin = client_for(cast.meena)
    sessions_before = Session.objects.count()
    response = admin.post(reverse("admin_user_disable", kwargs={"user_id": cast.ravi.pk}))
    assert response.status_code == 302
    assert Session.objects.count() == sessions_before - 1
    assert ravi.get(reverse("document_detail", kwargs={"doc_id": letter.pk})).status_code == 302  # sent to sign in
    assert AuditEvent.objects.filter(action="user.disabled", detail__target="ravi").exists()


def test_a_disabled_user_cannot_sign_back_in_until_enabled(cast, anon_client, client_for):
    admin = client_for(cast.meena)
    admin.post(reverse("admin_user_disable", kwargs={"user_id": cast.ravi.pk}))
    from .conftest import PASSWORD
    assert anon_client.post(reverse("login"), {"username": "ravi", "password": PASSWORD}).status_code == 200
    admin.post(reverse("admin_user_enable", kwargs={"user_id": cast.ravi.pk}))
    assert anon_client.post(reverse("login"), {"username": "ravi", "password": PASSWORD}).status_code == 302


def test_administrators_cannot_be_changed_from_the_website(cast, make_user, client_for):
    other_admin = make_user("admin2", "admin")
    admin = client_for(cast.meena)
    for target in (other_admin, cast.meena):
        assert admin.post(reverse("admin_user_disable", kwargs={"user_id": target.pk})).status_code == 400
        target.refresh_from_db()
        assert target.is_active


def test_the_website_has_no_way_to_change_roles(cast):
    from django.urls import get_resolver
    routes = " ".join(str(p.pattern) for p in get_resolver().url_patterns)
    assert "role" not in routes and "promote" not in routes


# ---- owner history
def test_owner_sees_who_opened_and_who_was_refused(cast, letter, client_for):
    client_for(cast.ravi).get(reverse("document_detail", kwargs={"doc_id": letter.pk}))
    client_for(cast.sunil).get(reverse("document_detail", kwargs={"doc_id": letter.pk}))
    page = titles(client_for(cast.priya).get(reverse("document_history", kwargs={"doc_id": letter.pk})))
    assert "ravi" in page and "sunil" in page and "refused" in page


def test_only_the_owner_sees_the_history(cast, letter, client_for):
    for person in (cast.ravi, cast.sunil, cast.anita, cast.meena):
        assert client_for(person).get(reverse("document_history", kwargs={"doc_id": letter.pk})).status_code == 404


# ---- command line
def test_create_user_makes_a_plain_account(monkeypatch):
    from django.contrib.auth import get_user_model
    monkeypatch.setenv("NEW_USER_PASSWORD", "a-long-unusual-passphrase-91")
    call_command("create_user", "nadia", "--role", "owner")
    user = get_user_model().objects.get(username="nadia")
    assert user.role == "owner" and not user.is_staff and not user.is_superuser
    assert AuditEvent.objects.filter(action="user.created", detail__username="nadia").exists()


def test_create_user_refuses_weak_passwords_and_duplicates(monkeypatch, cast):
    monkeypatch.setenv("NEW_USER_PASSWORD", "short")
    with pytest.raises(CommandError):
        call_command("create_user", "weak")
    monkeypatch.setenv("NEW_USER_PASSWORD", "a-long-unusual-passphrase-91")
    with pytest.raises(CommandError):
        call_command("create_user", "priya")


def test_anchor_and_verify_commands(tmp_path, capsys):
    audit.record(actor=None, action="test.event", allowed=True)
    call_command("anchor")
    line = capsys.readouterr().out.strip()
    assert "seq=1" in line and "hash=" in line
    log = tmp_path / "anchors.log"
    log.write_text(line + "\n")
    call_command("verify_audit", anchors=str(log))
    log.write_text(line.replace("hash=", "hash=0")[:-1] + "\n")  # corrupt the saved hash
    with pytest.raises(CommandError):
        call_command("verify_audit", anchors=str(log))
    log.write_text("not an anchor\n")
    with pytest.raises(CommandError, match="Unable to read valid anchors"):
        call_command("verify_audit", anchors=str(log))
    log.write_text("")
    with pytest.raises(CommandError, match="anchor file is empty"):
        call_command("verify_audit", anchors=str(log))
