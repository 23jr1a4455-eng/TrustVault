from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from vault.models import Document, DocumentFile, Grant

pytestmark = pytest.mark.django_db


def search(client, **params):
    return client.get(reverse("document_list"), params)


def titles_on(response):
    return [d.title for d in response.context["page"].object_list]


@pytest.fixture
def library(cast):
    """Priya owns three documents, Anita owns one. Ravi can read two of Priya's."""
    hr = Document.objects.create(owner=cast.priya, title="Salary letter - Ravi", category="HR")
    offer = Document.objects.create(owner=cast.priya, title="Offer letter - Kiran", category="HR")
    legal = Document.objects.create(owner=cast.priya, title="Supplier contract", category="Legal")
    other = Document.objects.create(owner=cast.anita, title="Anita secret plan", category="Strategy")
    Grant.objects.create(document=hr, user=cast.ravi, level="read", granted_by=cast.priya)
    Grant.objects.create(document=legal, user=cast.ravi, level="read", granted_by=cast.priya)
    return SimpleNamespaceLike(hr=hr, offer=offer, legal=legal, other=other)


class SimpleNamespaceLike:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_search_only_finds_what_the_person_may_read(cast, library, client_for):  # A-08
    ravi = client_for(cast.ravi)
    assert sorted(titles_on(search(ravi))) == ["Salary letter - Ravi", "Supplier contract"]
    assert titles_on(search(ravi, q="letter")) == ["Salary letter - Ravi"]  # not the offer letter
    assert titles_on(search(ravi, q="secret")) == []
    assert titles_on(search(ravi, owner="anita")) == []
    assert titles_on(search(ravi, category="Strategy")) == []


def test_counts_never_include_hidden_documents(cast, library, client_for):
    for person, expected in ((cast.ravi, 2), (cast.sunil, 0), (cast.meena, 0), (cast.priya, 3), (cast.anita, 1)):
        response = search(client_for(person))
        assert response.context["total"] == expected, person.username
        assert f"{expected} document" in response.content.decode()


def test_a_stranger_gets_nothing_for_any_filter(cast, library, client_for):
    sunil = client_for(cast.sunil)
    for params in ({"q": "Salary"}, {"owner": "priya"}, {"category": "HR"}, {"q": "contract"}):
        assert titles_on(search(sunil, **params)) == [], params


def test_filters_by_name_owner_category_and_date(cast, library, client_for):
    priya = client_for(cast.priya)
    assert sorted(titles_on(search(priya, q="LETTER"))) == ["Offer letter - Kiran", "Salary letter - Ravi"]
    assert titles_on(search(priya, owner="PRIYA")).__len__() == 3
    assert titles_on(search(priya, category="legal")) == ["Supplier contract"]
    Document.objects.filter(pk=library.legal.pk).update(created_at=timezone.now() - timedelta(days=10))
    today = timezone.now().date()
    assert "Supplier contract" not in titles_on(search(priya, date_from=str(today - timedelta(days=2))))
    assert titles_on(search(priya, date_to=str(today - timedelta(days=5)))) == ["Supplier contract"]


def test_search_matches_the_file_name_too(cast, library, client_for):
    DocumentFile.objects.create(
        document=library.hr, original_name="payslip-march.pdf", content_type="application/pdf",
        size=3, sha256="0" * 64, data=b"abc", uploaded_by=cast.priya,
    )
    assert titles_on(search(client_for(cast.ravi), q="payslip")) == ["Salary letter - Ravi"]
    assert titles_on(search(client_for(cast.sunil), q="payslip")) == []


def test_category_choices_come_only_from_readable_documents(cast, library, client_for):
    assert search(client_for(cast.ravi)).context["categories"] == ["HR", "Legal"]
    assert search(client_for(cast.sunil)).context["categories"] == []
    assert "Strategy" not in search(client_for(cast.ravi)).content.decode()


def test_revoked_expired_and_deleted_documents_leave_search_at_once(cast, library, client_for):
    ravi = client_for(cast.ravi)
    assert len(titles_on(search(ravi))) == 2
    Grant.objects.filter(document=library.hr, user=cast.ravi).update(revoked_at=timezone.now())
    Grant.objects.filter(document=library.legal, user=cast.ravi).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert titles_on(search(ravi)) == []
    Document.objects.filter(pk=library.offer.pk).update(deleted_at=timezone.now())
    assert "Offer letter - Kiran" not in titles_on(search(client_for(cast.priya)))


def test_odd_input_is_harmless(cast, library, client_for):
    ravi = client_for(cast.ravi)
    for q in ("' OR 1=1 --", "%", "_", "<script>alert(1)</script>", "a" * 5000):
        response = search(ravi, q=q)
        assert response.status_code == 200
        assert titles_on(response) == []
    bad = search(ravi, date_from="not-a-date")
    assert bad.status_code == 200 and bad.context["form_invalid"]
    assert titles_on(bad) == []  # an unreadable search shows nothing, it does not widen


def test_pagination_stays_inside_permissions(cast, client_for):
    for number in range(45):
        document = Document.objects.create(owner=cast.priya, title=f"Report {number:02d}")
        Grant.objects.create(document=document, user=cast.ravi, level="read", granted_by=cast.priya)
    for number in range(30):
        Document.objects.create(owner=cast.priya, title=f"Hidden {number:02d}")
    ravi = client_for(cast.ravi)
    first, second, third = (search(ravi, page=n) for n in (1, 2, 3))
    assert [len(titles_on(r)) for r in (first, second, third)] == [20, 20, 5]
    assert all(t.startswith("Report") for r in (first, second, third) for t in titles_on(r))
    assert search(ravi, page=9999).status_code == 200
    assert first.context["total"] == 45


def test_search_needs_a_login(anon_client):
    response = anon_client.get(reverse("document_list"), {"q": "x"})
    assert response.status_code == 302 and "/login/" in response["Location"]
