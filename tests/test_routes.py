import pytest
from django.urls import URLResolver, get_resolver, reverse

from vault.models import AuditEvent

pytestmark = pytest.mark.django_db

METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]


def all_routes(patterns=None, prefix=""):
    patterns = get_resolver().url_patterns if patterns is None else patterns
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from all_routes(pattern.url_patterns, prefix + str(pattern.pattern))
        else:
            yield prefix + str(pattern.pattern), pattern.callback


def test_every_route_declares_how_it_is_protected():  # A-02
    unmarked = [
        route
        for route, view in all_routes()
        if getattr(view, "access", None) not in {"public", "authenticated", "gated", "uploader"}
    ]
    assert unmarked == [], f"Routes without a protection marker: {unmarked}"


def gated_routes():
    return [route for route, view in all_routes() if getattr(view, "access", None) == "gated"]


def test_the_inventory_actually_finds_the_gated_routes():
    # Guards against a vacuous test: if this drops, the loop tests below prove nothing.
    assert len(gated_routes()) >= 9


def real_path(route, letter):
    grant = letter.grants.first()
    path = "/" + route.replace("<uuid:doc_id>", str(letter.pk)).replace("<int:grant_id>", str(grant.pk))
    assert "<" not in path, f"unfilled route parameter in {path}"  # a 404 here would be a false pass
    return path


def test_all_gated_routes_deny_an_ungranted_user_for_every_method(cast, letter, client_for):  # A-07
    client = client_for(cast.sunil)
    for route in gated_routes():
        path = real_path(route, letter)
        for method in METHODS:
            response = client.generic(method, path)
            assert response.status_code == 404, f"{method} {path} returned {response.status_code}"
    letter.refresh_from_db()
    assert letter.deleted_at is None
    assert letter.title == "Salary letter - Ravi"


def test_all_gated_routes_send_anonymous_users_to_login(letter, anon_client):
    for route in gated_routes():
        path = real_path(route, letter)
        response = anon_client.get(path)
        assert response.status_code == 302, path
        assert "/login/" in response["Location"], path
    assert AuditEvent.objects.filter(document_id=letter.pk, allowed=False).count() >= 3


def test_upload_routes_refuse_viewers_admins_and_anonymous(cast, client_for, anon_client):
    routes = [route for route, view in all_routes() if getattr(view, "access", None) == "uploader"]
    assert routes, "no upload route found"
    for route in routes:
        path = "/" + route
        for person in (cast.ravi, cast.meena):
            client = client_for(person)
            for method in METHODS:
                assert client.generic(method, path).status_code == 404, (person.username, method, path)
        assert anon_client.get(path).status_code == 302
