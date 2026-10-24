"""Login throttling. Counters live in the process cache (fine for one server)."""

import hashlib

from django.core.cache import cache

from vault.services import audit
from vault.services.audit import client_ip

USER_LIMIT = 5  # failed attempts per username
IP_LIMIT = 20  # failed attempts per address
WINDOW = 15 * 60  # seconds


def _keys(request, username):
    name = (username or "").strip().lower()[:150]
    digest = hashlib.sha256(name.encode()).hexdigest()[:32]
    return f"login-fail:user:{digest}", f"login-fail:ip:{client_ip(request) or 'unknown'}"


def is_blocked(request, username):
    user_key, ip_key = _keys(request, username)
    return cache.get(user_key, 0) >= USER_LIMIT or cache.get(ip_key, 0) >= IP_LIMIT


def register_failure(request, username):
    for key in _keys(request, username):
        cache.add(key, 0, WINDOW)
        try:
            cache.incr(key)
        except ValueError:  # expired between add and incr
            cache.set(key, 1, WINDOW)


def clear(request, username):
    cache.delete(_keys(request, username)[0])


PROBE_LIMIT = 30
PROBE_WINDOW = 10 * 60


def probe_blocked(request):
    """Throttle anonymous document probes and log one summary event per window."""
    key = f"probe:{client_ip(request) or 'unknown'}"
    cache.add(key, 0, PROBE_WINDOW)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, PROBE_WINDOW)
        count = 1
    if count <= PROBE_LIMIT:
        return False
    if cache.add(key + ":logged", 1, PROBE_WINDOW):
        audit.record(
            actor=None,
            action="auth.probe_throttled",
            allowed=False,
            request=request,
            detail={"limit": PROBE_LIMIT},
        )
    return True
