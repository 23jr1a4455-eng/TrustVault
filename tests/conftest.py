from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client

from vault.models import Document, Grant

PASSWORD = "test-only-password-123"


def new_client(**extra):
    """A test client that looks like it arrived through the host's HTTPS proxy."""
    return Client(HTTP_X_FORWARDED_PROTO="https", **extra)


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    """Tests only: a cheap hasher keeps the suite fast. Production keeps Django's default."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def make_user(db):
    User = get_user_model()

    def _make(username, role="viewer", **extra):
        return User.objects.create_user(username=username, password=PASSWORD, role=role, **extra)

    return _make


@pytest.fixture
def cast(make_user):
    """Priya and Anita own documents, Ravi and Sunil are viewers, Meena is the admin."""
    return SimpleNamespace(
        priya=make_user("priya", "owner"),
        anita=make_user("anita", "owner"),
        ravi=make_user("ravi", "viewer"),
        sunil=make_user("sunil", "viewer"),
        meena=make_user("meena", "admin"),
    )


@pytest.fixture
def letter(cast):
    """Priya's salary letter. Only Ravi has been granted read access."""
    document = Document.objects.create(owner=cast.priya, title="Salary letter - Ravi", category="HR")
    Grant.objects.create(document=document, user=cast.ravi, level="read", granted_by=cast.priya)
    return document


@pytest.fixture
def client_for():
    def _client_for(user):
        client = new_client()
        client.force_login(user)
        return client

    return _client_for


@pytest.fixture
def anon_client():
    return new_client()
