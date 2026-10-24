"""Checking the audit chain, and the daily anchors kept outside the app."""

import re
from dataclasses import dataclass, field

from vault.models import AuditChainHead, AuditEvent
from vault.services.audit import GENESIS, compute_hash, hash_fields_of

ANCHOR_LINE = re.compile(r"seq=(\d+)\s+hash=([0-9a-f]{64})")
MAX_PROBLEMS = 20


@dataclass
class ChainReport:
    ok: bool = True
    checked: int = 0
    legacy: int = 0
    head_seq: int = 0
    anchors_checked: int = 0
    problems: list = field(default_factory=list)

    def fail(self, message):
        self.ok = False
        if len(self.problems) < MAX_PROBLEMS:
            self.problems.append(message)


def parse_anchors(text):
    """Lines look like: 2026-10-23T09:00:00Z seq=120 hash=<64 hex> count=120"""
    return [(int(seq), digest) for seq, digest in ANCHOR_LINE.findall(text or "")]


def verify_chain(anchors=None):
    report = ChainReport()
    first = AuditEvent.objects.filter(seq__isnull=False).order_by("id").first()
    legacy = AuditEvent.objects.filter(seq__isnull=True)
    report.legacy = legacy.count()
    if first is not None and legacy.filter(id__gt=first.id).exists():
        report.fail("Rows without a chain position were added after the chain started.")

    expected, previous = 1, GENESIS
    for event in AuditEvent.objects.filter(seq__isnull=False).order_by("seq").iterator(chunk_size=500):
        if event.seq != expected:
            report.fail(f"Missing or reordered rows: expected position {expected}, found {event.seq}.")
        if event.prev_hash != previous:
            report.fail(f"Row {event.seq} does not follow the row before it.")
        if compute_hash(event.prev_hash, hash_fields_of(event)) != event.row_hash:
            report.fail(f"Row {event.seq} was altered (its hash does not match).")
        previous, expected = event.row_hash, event.seq + 1
        report.checked += 1
        report.head_seq = event.seq

    head = AuditChainHead.objects.filter(pk=1).first()
    if report.checked and (head is None or head.last_seq != report.head_seq or head.last_hash != previous):
        report.fail("The recorded end of the chain does not match the last row (rows removed from the end?).")

    for seq, digest in anchors or []:
        row = AuditEvent.objects.filter(seq=seq).first()
        report.anchors_checked += 1
        if row is None or row.row_hash != digest:
            report.fail(f"Anchor for position {seq} does not match the database (history rewritten?).")
    return report
