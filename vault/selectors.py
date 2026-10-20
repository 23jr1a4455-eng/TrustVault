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
