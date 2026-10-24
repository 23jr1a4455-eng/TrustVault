import pathlib
import uuid

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.urls import reverse

from vault import throttle
from vault.models import AuditEvent
from vault.services.flags import find_flags

pytestmark = pytest.mark.django_db


def test_every_response_has_security_headers(cast, letter, client_for, anon_client):
    responses = [
        anon_client.get(reverse("login")),
        anon_client.get("/no-such-page/"),
        client_for(cast.ravi).get(reverse("document_list")),
        client_for(cast.ravi).get(
            reverse("document_detail", kwargs={"doc_id": letter.pk})
        ),
        client_for(cast.sunil).get(
            reverse("document_detail", kwargs={"doc_id": letter.pk})
        ),
    ]
    for response in responses:
        assert "default-src 'none'" in response["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
        assert "camera=()" in response["Permissions-Policy"]
        assert response["Cross-Origin-Resource-Policy"] == "same-origin"
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["X-Frame-Options"] == "DENY"
        assert response["Referrer-Policy"] == "same-origin"


def test_pages_have_no_inline_script_or_style():
    for template in pathlib.Path("vault/templates").rglob("*.html"):
        text = template.read_text(encoding="utf-8").lower()
        assert "<script" not in text, template
        assert "<style" not in text, template
        assert "style=" not in text, template
        assert " onclick=" not in text and " onsubmit=" not in text, template


def test_anonymous_probing_is_slowed_down_and_logged_once(letter, anon_client):
    address = reverse("document_detail", kwargs={"doc_id": letter.pk})
    for _ in range(throttle.PROBE_LIMIT):
        assert anon_client.get(address).status_code == 302
    for _ in range(5):
        assert anon_client.get(address).status_code == 429
    assert AuditEvent.objects.filter(action="auth.probe_throttled").count() == 1
    assert (
        AuditEvent.objects.filter(document_id=letter.pk, allowed=False).count()
        == throttle.PROBE_LIMIT
    )
    assert any(flag.kind.startswith("Anonymous probing") for flag in find_flags())


@override_settings(DEBUG=True)
def test_404_responses_are_generic_and_match_for_unavailable_documents(
    cast, letter, client_for, anon_client
):
    client = client_for(cast.sunil)
    existing = reverse("document_detail", kwargs={"doc_id": letter.pk})
    missing = reverse("document_detail", kwargs={"doc_id": uuid.uuid4()})

    for method in ("GET", "OPTIONS", "POST"):
        denied = getattr(client, method.lower())(existing)
        absent = getattr(client, method.lower())(missing)
        assert denied.status_code == absent.status_code == 404
        assert denied.content == absent.content

    unknown = anon_client.get("/no-such-page-xyz/")
    assert unknown.status_code == 404
    assert b"URLconf" not in unknown.content
    assert b"Traceback" not in unknown.content


def test_signed_in_people_are_not_slowed_down_by_probe_limit(cast, letter, client_for):
    client = client_for(cast.sunil)
    address = reverse("document_detail", kwargs={"doc_id": letter.pk})
    assert all(
        client.get(address).status_code == 404
        for _ in range(throttle.PROBE_LIMIT + 5)
    )


def test_seed_command_rejects_a_weak_password(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "password")
    with pytest.raises(CommandError, match="too weak"):
        call_command("seed")
