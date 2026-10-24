"""THE authorisation gate. Every document action is decided here, and only here."""

from django.http import Http404

from vault.models import Document, Grant
from vault.services import audit

READ, DOWNLOAD, EDIT, DELETE = "read", "download", "edit", "delete"
SHARE, RESTORE = "share", "restore"  # owner only: manage who has access / undelete

# Level needed for each action. An action that is not listed is denied.
REQUIRED_LEVEL = {READ: 1, DOWNLOAD: 1, EDIT: 2, DELETE: 3, SHARE: 3, RESTORE: 3}
# Plain string keys on purpose; the database stores "read" / "edit".
GRANT_LEVEL = {"read": 1, "edit": 2}
OWNER_LEVEL = 3
NEVER = 99


def level_for(user, document, include_deleted=False):
    """The user's access level on the document right now, read fresh from the database.

    0 = none, 1 = read, 2 = edit, 3 = owner. Admins get nothing special.
    """
    if document is None or user is None:
        return 0
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return 0
    if document.deleted_at is not None and not include_deleted:
        return 0
    if document.owner_id == user.pk:
        return OWNER_LEVEL
    grant = Grant.objects.active().filter(document=document, user=user).first()
    return GRANT_LEVEL.get(grant.level, 0) if grant else 0


def can(user, document, action):
    """Quiet check for deciding which buttons to show. Writes no audit row.

    The screen is only a hint; the server still decides in authorize().
    """
    return level_for(user, document) >= REQUIRED_LEVEL.get(action, NEVER)


def authorize(user, doc_id, action, request=None):
    """Return the document if `user` may do `action` on it, otherwise raise Http404.

    Every decision, allowed or refused, is written to the audit log FIRST. That row is
    committed before the 404 is raised, so refused attempts are never lost. Never call
    this inside a transaction.atomic() block.
    """
    document = Document.objects.filter(pk=doc_id).first()
    level = level_for(user, document, include_deleted=(action == RESTORE))
    allowed = document is not None and level >= REQUIRED_LEVEL.get(action, NEVER)
    detail = {"level": level}
    if not getattr(user, "is_authenticated", False):
        detail["reason"] = "anonymous"
    audit.record(
        actor=user,
        action=f"document.{action}",
        allowed=allowed,
        document_id=doc_id,
        request=request,
        detail=detail,
    )
    if not allowed:
        raise Http404  # same answer for "no such document" and "not yours"
    return document


def authorize_upload(user, request=None):
    """Gate for creating a new document. Only active users with the owner role may upload.

    Admins and viewers are refused (and the refusal is audited), like any other denial.
    """
    allowed = (
        getattr(user, "is_authenticated", False)
        and user.is_active
        and getattr(user, "role", "") == "owner"
    )
    audit.record(
        actor=user,
        action="document.upload",
        allowed=allowed,
        request=request,
        detail={"role": getattr(user, "role", "")},
    )
    if not allowed:
        raise Http404
