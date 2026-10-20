import pytest
from django.test import Client
from django.urls import reverse

from vault.models import AuditEvent

from .conftest import PASSWORD, new_client

pytestmark = pytest.mark.django_db


def login(client, username, password=PASSWORD, query=""):
    return client.post(reverse("login") + query, {"username": username, "password": password})


def test_login_success_goes_to_the_document_list(cast, anon_client):
    response = login(anon_client, "ravi")
    assert response.status_code == 302
    assert response["Location"] == reverse("document_list")


def test_login_error_is_identical_for_every_kind_of_failure(cast, make_user, anon_client):  # S-02
    disabled = make_user("kiran")
    disabled.is_active = False
    disabled.save()
    messages = []
    for username, password in [("ravi", "wrong-password"), ("nobody", "whatever"), ("kiran", PASSWORD)]:
        response = login(anon_client, username, password)
        assert response.status_code == 200
        messages.append(list(response.context["form"].non_field_errors()))
    assert messages[0] == messages[1] == messages[2]
    text = " ".join(messages[0]).lower()
    assert "inactive" not in text and "disabled" not in text and "exist" not in text


def test_login_is_rate_limited(cast, anon_client):  # S-01, U-07
    for _ in range(5):
        assert login(anon_client, "sunil", "wrong").status_code == 200
    response = login(anon_client, "sunil", PASSWORD)  # even the right password is refused now
    assert response.status_code == 429
    assert AuditEvent.objects.filter(action="auth.login_throttled").exists()


def test_throttling_one_account_does_not_block_another(cast, anon_client):
    for _ in range(5):
        login(anon_client, "sunil", "wrong")
    assert login(anon_client, "ravi").status_code == 302


def test_login_rejects_external_next_url(cast, anon_client):  # A-10
    response = login(anon_client, "ravi", query="?next=https://evil.example/")
    assert response.status_code == 302
    assert response["Location"] == reverse("document_list")


def test_login_keeps_a_local_next_url(cast, anon_client):
    response = login(anon_client, "ravi", query="?next=/documents/")
    assert response["Location"] == "/documents/"


def test_failed_login_never_stores_the_password(cast, anon_client):
    login(anon_client, "ravi", "SuperSecret-123")
    stored = str(list(AuditEvent.objects.values()))
    assert "SuperSecret-123" not in stored
    assert AuditEvent.objects.filter(action="auth.login_failed").exists()


def test_logout_ends_the_session(cast, client_for):  # S-03
    client = client_for(cast.priya)
    old_session = client.cookies["sessionid"].value
    assert client.post(reverse("logout")).status_code == 302
    stale = new_client()
    stale.cookies["sessionid"] = old_session
    response = stale.get(reverse("document_list"))
    assert response.status_code == 302
    assert "/login/" in response["Location"]


def test_logout_needs_post(cast, client_for):
    assert client_for(cast.priya).get(reverse("logout")).status_code == 405


def test_post_without_csrf_token_is_rejected(cast, letter):  # S-04
    client = new_client(enforce_csrf_checks=True)
    client.force_login(cast.priya)
    response = client.post(
        reverse("document_edit", kwargs={"doc_id": letter.pk}), {"title": "Changed"}
    )
    assert response.status_code == 403
    letter.refresh_from_db()
    assert letter.title == "Salary letter - Ravi"


def test_404_page_has_no_debug_information(anon_client):  # P-09
    response = anon_client.get("/definitely-not-a-page/")
    assert response.status_code == 404
    body = response.content.decode()
    assert "Django tried" not in body and "URLconf" not in body and "Request URL" not in body
