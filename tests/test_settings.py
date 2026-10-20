import pytest
from django.conf import settings as django_settings
from django.db import connection
from django.test import Client


@pytest.mark.django_db
def test_runs_on_postgresql():
    assert connection.vendor == "postgresql"


def test_requests_are_not_wrapped_in_a_transaction():
    # If this were True, a refused request would roll back its own audit row.
    assert django_settings.DATABASES["default"]["ATOMIC_REQUESTS"] is False


def test_http_is_redirected_to_https(settings):
    settings.SECURE_SSL_REDIRECT = True
    response = Client().get("/documents/")
    assert response.status_code == 301
    assert response["Location"].startswith("https://")
