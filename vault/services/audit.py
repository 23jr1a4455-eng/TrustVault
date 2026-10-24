"""Writing the audit trail as a keyed hash chain.

Every row stores HMAC-SHA256(key, previous hash + this row's fields). The key lives in
an environment variable, never in the database. Rows are committed immediately unless
the caller is already inside a transaction (then they commit together).
"""

import hashlib
import hmac
import ipaddress
import json
import re
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from vault.models import AuditChainHead, AuditEvent

GENESIS = "0" * 64
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def normalise_ip(value):
    try:
        return str(ipaddress.ip_address(value)) if value else None
    except ValueError:
        return None


def client_ip(request):
    """Best-effort client address, or None.

    Behind the host's proxy the LAST X-Forwarded-For entry is the one our own proxy
    added; earlier entries can be forged by the client.
    """
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidate = forwarded.split(",")[-1].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    return normalise_ip(candidate)


def _clean(value, depth=0):
    """Make log values safe: no control characters (so no fake log lines), short."""
    if isinstance(value, str):
        return _CONTROL.sub(" ", value)[:200]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict) and depth < 3:
        return {_CONTROL.sub(" ", str(k))[:50]: _clean(v, depth + 1) for k, v in list(value.items())[:20]}
    if isinstance(value, (list, tuple)) and depth < 3:
        return [_clean(v, depth + 1) for v in list(value)[:20]]
    return _CONTROL.sub(" ", str(value))[:200]


def fields_for_hash(*, seq, created_at, actor_id, actor_name, action, allowed, document_id, ip_address, detail):
    """The exact values that go into the hash, in one canonical form."""
    return {
        "seq": seq,
        "created_at": created_at.astimezone(dt_timezone.utc).isoformat(),
        "actor_id": actor_id,
        "actor_name": actor_name,
        "action": action,
        "allowed": bool(allowed),
        "document_id": str(document_id) if document_id else None,
        "ip_address": normalise_ip(ip_address),
        "detail": detail,
    }


def compute_hash(prev_hash, fields, key=None):
    key = (key or settings.AUDIT_HMAC_KEY).encode()
    body = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(key, f"{prev_hash}|{body}".encode(), hashlib.sha256).hexdigest()


def hash_fields_of(event):
    return fields_for_hash(
        seq=event.seq, created_at=event.created_at, actor_id=event.actor_id, actor_name=event.actor_name,
        action=event.action, allowed=event.allowed, document_id=event.document_id,
        ip_address=event.ip_address, detail=event.detail,
    )


def record(*, actor, action, allowed, document_id=None, request=None, detail=None):
    """Append one event to the chain. If this raises, the caller must NOT carry on."""
    is_user = actor is not None and getattr(actor, "is_authenticated", False)
    created_at = timezone.now()
    actor_id = actor.pk if is_user else None
    actor_name = _CONTROL.sub(" ", actor.get_username())[:150] if is_user else ""
    action = action[:64]
    ip = client_ip(request)
    clean_detail = _clean(detail or {})
    with transaction.atomic():
        head, _ = AuditChainHead.objects.select_for_update().get_or_create(pk=1)
        seq = head.last_seq + 1
        fields = fields_for_hash(
            seq=seq, created_at=created_at, actor_id=actor_id, actor_name=actor_name, action=action,
            allowed=allowed, document_id=document_id, ip_address=ip, detail=clean_detail,
        )
        row_hash = compute_hash(head.last_hash, fields)
        event = AuditEvent.objects.create(
            created_at=created_at, actor_id=actor_id, actor_name=actor_name, action=action,
            allowed=allowed, document_id=document_id, ip_address=ip, detail=clean_detail,
            seq=seq, prev_hash=head.last_hash, row_hash=row_hash,
        )
        head.last_seq, head.last_hash = seq, row_hash
        head.save(update_fields=["last_seq", "last_hash"])
    return event
