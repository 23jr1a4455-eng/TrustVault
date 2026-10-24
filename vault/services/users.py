"""Switching accounts off and on. Roles are never changed from the website."""

from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from vault.services import audit


class UserChangeRefused(Exception):
    pass


def end_sessions(user):
    """Delete every live login of this user, so nothing issued earlier keeps working."""
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if session.get_decoded().get("_auth_user_id") == str(user.pk):
            session.delete()


def _check(target, by):
    if target.role == "admin":
        raise UserChangeRefused("Administrator accounts cannot be changed from the website.")
    if target.pk == by.pk:
        raise UserChangeRefused("You cannot change your own account.")


def disable_user(*, target, by, request=None):
    _check(target, by)
    with transaction.atomic():
        target.is_active = False
        target.save(update_fields=["is_active"])
        audit.record(actor=by, action="user.disabled", allowed=True, request=request,
                     detail={"target": target.get_username(), "target_id": target.pk})
    end_sessions(target)


def enable_user(*, target, by, request=None):
    _check(target, by)
    with transaction.atomic():
        target.is_active = True
        target.save(update_fields=["is_active"])
        audit.record(actor=by, action="user.enabled", allowed=True, request=request,
                     detail={"target": target.get_username(), "target_id": target.pk})
