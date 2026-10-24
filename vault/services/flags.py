"""'Worth noticing' signals for the administrator, found by simple rules over the audit trail."""

from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from vault.models import AuditEvent

# (how many, within how many minutes)
DENIED_BURST = (5, 10)
DOWNLOAD_BURST = (10, 10)
LOGIN_FAIL_BURST = (5, 15)
LOOKBACK = timedelta(hours=24)
NEW_ACCOUNT_AGE = timedelta(hours=24)
GRANT_LOOKBACK = timedelta(days=7)


@dataclass
class Flag:
    kind: str
    who: str
    count: int
    last: object
    note: str


def busiest(times, minutes):
    """The most events that fall inside any window of `minutes`."""
    times = sorted(times)
    best, start = 0, 0
    for end, moment in enumerate(times):
        while moment - times[start] > timedelta(minutes=minutes):
            start += 1
        best = max(best, end - start + 1)
    return best


def _bursts(events, who_of, threshold, kind, note):
    groups = {}
    for event in events:
        groups.setdefault(who_of(event), []).append(event.created_at)
    found = []
    needed, minutes = threshold
    for who, times in groups.items():
        count = busiest(times, minutes)
        if count >= needed:
            found.append(Flag(kind, who, count, max(times), note.format(count=count, minutes=minutes)))
    return found


def _who(event):
    return event.actor_name or (f"unknown ({event.ip_address})" if event.ip_address else "unknown")


def find_flags(now=None):
    now = now or timezone.now()
    since = now - LOOKBACK
    recent = AuditEvent.objects.filter(created_at__gte=since, created_at__lte=now)
    flags = []

    denied = recent.filter(allowed=False, action__startswith="document.").exclude(action="document.upload_rejected")
    flags += _bursts(denied, _who, DENIED_BURST, "Repeated refused attempts",
                     "{count} refused document attempts within {minutes} minutes")

    downloads = recent.filter(allowed=True, action="document.download")
    flags += _bursts(downloads, _who, DOWNLOAD_BURST, "Many downloads",
                     "{count} downloads within {minutes} minutes")

    failures = recent.filter(action__in=["auth.login_failed", "auth.login_throttled"])
    flags += _bursts(failures, lambda e: e.detail.get("username") or _who(e), LOGIN_FAIL_BURST,
                     "Repeated failed sign-ins", "{count} failed or blocked sign-ins within {minutes} minutes")

    for event in recent.filter(action="auth.probe_throttled", allowed=False):
        flags.append(
            Flag(
                "Anonymous probing threshold reached",
                _who(event),
                1,
                event.created_at,
                "Anonymous document probes exceeded the per-address limit.",
            )
        )

    for event in AuditEvent.objects.filter(action="document.integrity_failure",
                                           created_at__gte=now - GRANT_LOOKBACK, created_at__lte=now):
        flags.append(Flag("A stored file failed its integrity check", _who(event), 1, event.created_at,
                          "The bytes in the database no longer match their recorded hash."))

    grants = list(AuditEvent.objects.filter(action__in=["grant.created", "grant.changed"], allowed=True,
                                            created_at__gte=now - GRANT_LOOKBACK, created_at__lte=now))
    joined = dict(get_user_model().objects.filter(pk__in={g.detail.get("grantee_id") for g in grants})
                  .values_list("pk", "date_joined"))
    for event in grants:
        date_joined = joined.get(event.detail.get("grantee_id"))
        if date_joined and event.created_at - date_joined < NEW_ACCOUNT_AGE:
            flags.append(Flag("Access given to a brand-new account", _who(event), 1, event.created_at,
                              f"{event.detail.get('grantee')} got {event.detail.get('level')} access "
                              "within a day of their account being created."))
    return sorted(flags, key=lambda f: f.last, reverse=True)
