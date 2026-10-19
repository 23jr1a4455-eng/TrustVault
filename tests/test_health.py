def test_health_ok(client):
    response = client.get("/health/", secure=True)
    assert response.status_code == 200
    assert response.content == b"ok"


def test_django_admin_is_not_exposed(client):
    assert client.get("/admin/", secure=True).status_code == 404