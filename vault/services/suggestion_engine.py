"""Proposes potential grantees using document metadata and existing grants only."""

from collections import Counter
from dataclasses import dataclass

from django.contrib.auth import get_user_model

from vault.models import Document, Grant

SOURCE = "rules-v1"
MAX_SUGGESTIONS = 5


@dataclass(frozen=True)
class Proposal:
    user: object
    level: str
    reason: str


def propose(document):
    if not document.category:
        return []
    siblings = list(
        Document.objects.filter(
            owner_id=document.owner_id,
            category__iexact=document.category,
            deleted_at__isnull=True,
        )
        .exclude(pk=document.pk)
        .values_list("pk", flat=True)
    )
    counts = Counter(
        Grant.objects.active()
        .filter(document_id__in=siblings)
        .values_list("user_id", flat=True)
    )
    already = set(
        Grant.objects.active().filter(document=document).values_list("user_id", flat=True)
    )
    people = (
        get_user_model().objects.filter(pk__in=counts.keys(), is_active=True)
        .exclude(pk=document.owner_id)
        .exclude(pk__in=already)
        .exclude(role="admin")
    )
    ranked = sorted(people, key=lambda user: (-counts[user.pk], user.get_username()))[
        :MAX_SUGGESTIONS
    ]
    return [
        Proposal(
            user=user,
            level="read",
            reason=(
                f"Already has access to {counts[user.pk]} other "
                f"{document.category} document(s) you own."
            ),
        )
        for user in ranked
    ]
