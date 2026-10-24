"""The suggestion workflow; only the owner's decision creates a grant."""

from django.db import transaction
from django.http import Http404
from django.utils import timezone

from vault.models import Suggestion
from vault.services import audit, grants, suggestion_engine


def generate(*, document, by, request=None):
    proposals = suggestion_engine.propose(document)
    created = []
    with transaction.atomic():
        pending = set(
            Suggestion.objects.filter(document=document, status="pending").values_list(
                "candidate_id", flat=True
            )
        )
        for proposal in proposals:
            if proposal.user.pk in pending:
                continue
            created.append(
                Suggestion.objects.create(
                    document=document,
                    candidate=proposal.user,
                    level=proposal.level,
                    reason=proposal.reason,
                    source=suggestion_engine.SOURCE,
                    requested_by=by,
                )
            )
        audit.record(
            actor=by,
            action="ai.suggested",
            allowed=True,
            document_id=document.pk,
            request=request,
            detail={
                "source": suggestion_engine.SOURCE,
                "count": len(created),
                "candidates": [item.candidate.get_username() for item in created],
            },
        )
    return created


def accept(*, document, suggestion_id, by, level, request=None):
    with transaction.atomic():
        suggestion = (
            Suggestion.objects.select_for_update()
            .select_related("candidate")
            .filter(pk=suggestion_id, document=document, status="pending")
            .first()
        )
        if suggestion is None:
            raise Http404
        grants.grant_access(
            document=document,
            by=by,
            username=suggestion.candidate.get_username(),
            level=level,
            request=request,
        )
        suggestion.status = "accepted"
        suggestion.decided_by = by
        suggestion.decided_at = timezone.now()
        suggestion.final_level = level
        suggestion.save(
            update_fields=["status", "decided_by", "decided_at", "final_level"]
        )
        audit.record(
            actor=by,
            action="ai.accepted",
            allowed=True,
            document_id=document.pk,
            request=request,
            detail={
                "suggestion_id": suggestion.pk,
                "candidate": suggestion.candidate.get_username(),
                "source": suggestion.source,
                "proposed_level": suggestion.level,
                "final_level": level,
                "level_changed": level != suggestion.level,
            },
        )
    return suggestion


def reject(*, document, suggestion_id, by, request=None):
    with transaction.atomic():
        suggestion = (
            Suggestion.objects.select_for_update()
            .select_related("candidate")
            .filter(pk=suggestion_id, document=document, status="pending")
            .first()
        )
        if suggestion is None:
            raise Http404
        suggestion.status = "rejected"
        suggestion.decided_by = by
        suggestion.decided_at = timezone.now()
        suggestion.save(update_fields=["status", "decided_by", "decided_at"])
        audit.record(
            actor=by,
            action="ai.rejected",
            allowed=True,
            document_id=document.pk,
            request=request,
            detail={
                "suggestion_id": suggestion.pk,
                "candidate": suggestion.candidate.get_username(),
                "source": suggestion.source,
            },
        )
    return suggestion
