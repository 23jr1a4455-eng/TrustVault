import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command


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