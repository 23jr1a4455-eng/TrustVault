
from datetime import timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from vault.models import AuditEvent
from vault.services.audit_chain import verify_chain


class Command(BaseCommand):
    help = "Print an anchor only if the audit chain verifies."

    def handle(self, *args, **options):
        report = verify_chain()

        if not report.ok:
            details = "\n".join(report.problems)
            raise CommandError(
                "Refusing to create an anchor: audit chain verification failed.\n"
                f"{details}"
            )

        last = (
            AuditEvent.objects.filter(seq__isnull=False)
            .order_by("-seq")
            .first()
        )

        if last is None:
            raise CommandError("There are no chained audit rows yet.")

        stamp = timezone.now().astimezone(dt_timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.stdout.write(
            f"{stamp} seq={last.seq} hash={last.row_hash} count={last.seq}"
        )
