"""Writing the audit trail. Rows are committed immediately (autocommit)."""

import ipaddress

from vault.models import AuditEvent


def client_ip(request):
    """Best-effort client address, or None.

    Behind the host's proxy the LAST X-Forwarded-For entry is the one our own proxy
    added; earlier entries can be forged by the client.
    """
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidate = forwarded.split(",")[-1].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def record(*, actor, action, allowed, document_id=None, request=None, detail=None):
    """Append one event. If this raises, the caller must NOT carry on (fail closed)."""
    is_user = actor is not None and getattr(actor, "is_authenticated", False)
    return AuditEvent.objects.create(
        actor_id=actor.pk if is_user else None,
        actor_name=actor.get_username() if is_user else "",
        action=action,
        allowed=allowed,
        document_id=document_id,
        ip_address=client_ip(request),
        detail=detail or {},
    )
