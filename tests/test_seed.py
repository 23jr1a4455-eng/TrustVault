import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from vault.models import Document, Grant


@pytest.mark.django_db
def test_seed_is_repeatable_and_roles_are_correct(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "test-only-password")
    call_command("seed")
    call_command("seed")
    User = get_user_model()
    assert User.objects.count() == 6
    assert User.objects.get(username="meena").role == "admin"
    assert not User.objects.filter(is_staff=True).exists()
    assert not User.objects.filter(is_superuser=True).exists()
    assert Document.objects.count() == 3
    assert Grant.objects.count() == 2


@pytest.mark.django_db
def test_seeded_stranger_cannot_open_the_salary_letter(monkeypatch):
    from django.urls import reverse

    from tests.conftest import new_client

    monkeypatch.setenv("SEED_PASSWORD", "test-only-password")
    call_command("seed")
    letter = Document.objects.get(title__startswith="Salary letter")
    sunil = get_user_model().objects.get(username="sunil")
    client = new_client()
    client.force_login(sunil)
    assert client.get(reverse("document_detail", kwargs={"doc_id": letter.pk})).status_code == 404
