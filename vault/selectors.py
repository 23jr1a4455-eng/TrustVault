"""Read-side queries. Permission is part of the query, never a filter afterwards."""

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from vault.models import Document, Grant


def readable_documents(user):
    """Documents `user` may read right now."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return Document.objects.none()
    now = timezone.now()
    active_grant = Grant.objects.filter(
        document=OuterRef("pk"), user=user, revoked_at__isnull=True
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    return Document.objects.filter(deleted_at__isnull=True).filter(
        Q(owner=user) | Exists(active_grant)
    )


def search_documents(user, q="", owner="", category="", date_from=None, date_to=None):
    """Search ONLY inside what `user` may already read. The permission is in the query,
    so counts, pages and filters can never reveal a document the person cannot open."""
    results = readable_documents(user).select_related("owner")
    if q:
        results = results.filter(Q(title__icontains=q) | Q(file__original_name__icontains=q))
    if owner:
        results = results.filter(owner__username__iexact=owner)
    if category:
        results = results.filter(category__iexact=category)
    if date_from:
        results = results.filter(created_at__date__gte=date_from)
    if date_to:
        results = results.filter(created_at__date__lte=date_to)
    return results.order_by("-created_at", "-id")


def readable_categories(user):
    """Category names for the filter box, taken only from documents the user can read."""
    return list(
        readable_documents(user).exclude(category="").order_by("category")
        .values_list("category", flat=True).distinct()
    )
