"""Creating and removing grants. This is the ONLY code that writes grants.

Callers must already have passed the SHARE gate. Each change and its audit row are
written in one transaction, so there is never a grant without a record of who made it.
"""

from datetime import datetime, time, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from vault.models import Grant
from vault.services import audit

LEVELS = {"read", "edit"}

MESSAGES = {
    "no_such_user": "No active user with that username.",
    "owner": "The owner already has full access.",
    "bad_level": "Choose read or edit.",
    "bad_expiry": "The expiry date must be in the future and within one year.",
    "conflict": "Please try again.",
}


class GrantRefused(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code
        self.message = MESSAGES[code]


def _expiry(expires_on):
    if expires_on is None:
        return None
    today = timezone.now().date()
    if expires_on <= today or (expires_on - today).days > 365:
        raise GrantRefused("bad_expiry")
    return datetime.combine(expires_on, time(23, 59, 59), tzinfo=dt_timezone.utc)


def grant_access(*, document, by, username, level, expires_on=None, request=None):
    """Give `username` read or edit access to `document`, or change what they have."""
    if level not in LEVELS:
        raise GrantRefused("bad_level")
    expires_at = _expiry(expires_on)
    grantee = get_user_model().objects.filter(username=username.strip(), is_active=True).first()
    if grantee is None:
        raise GrantRefused("no_such_user")  # same message for missing and disabled users
    if grantee.pk == document.owner_id:
        raise GrantRefused("owner")
    try:
        with transaction.atomic():
            existing = Grant.objects.unrevoked().filter(document=document, user=grantee).first()
            if existing is None:
                grant = Grant.objects.create(
                    document=document, user=grantee, level=level, granted_by=by, expires_at=expires_at
                )
                action, previous = "grant.created", None
            else:
                previous = existing.level
                existing.level, existing.expires_at = level, expires_at
                existing.save(update_fields=["level", "expires_at"])
                grant, action = existing, "grant.changed"
            audit.record(
                actor=by,
                action=action,
                allowed=True,
                document_id=document.pk,
                request=request,
                detail={
                    "grantee": grantee.get_username(),
                    "grantee_id": grantee.pk,
                    "level": level,
                    "previous_level": previous,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                },
            )
    except IntegrityError:  # two requests raced to create the same grant
        raise GrantRefused("conflict")
    return grant


def revoke_access(*, document, grant_id, by, request=None):
    """Take access away. The grant must belong to THIS document, so a guessed grant id
    from someone else's document finds nothing."""
    with transaction.atomic():
        grant = (
            Grant.objects.unrevoked()
            .select_related("user")
            .filter(pk=grant_id, document=document)
            .first()
        )
        if grant is None:
            raise Http404
        grant.revoked_at = timezone.now()
        grant.revoked_by = by
        grant.save(update_fields=["revoked_at", "revoked_by"])
        audit.record(
            actor=by,
            action="grant.revoked",
            allowed=True,
            document_id=document.pk,
            request=request,
            detail={"grantee": grant.user.get_username(), "grantee_id": grant.user_id, "level": grant.level},
        )
    return grant


def revoke_all(*, document, by):
    """Used when a document is deleted, so restoring it can never bring old access back."""
    return Grant.objects.unrevoked().filter(document=document).update(
        revoked_at=timezone.now(), revoked_by=by
    )
