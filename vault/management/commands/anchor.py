from datetime import timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from vault.models import AuditEvent


class Command(BaseCommand):
    help = "Print one anchor line (end of the chain) to be saved OUTSIDE the app, for example in Git."

    def handle(self, *args, **options):
        last = AuditEvent.objects.filter(seq__isnull=False).order_by("-seq").first()
        if last is None:
            raise CommandError("There are no chained audit rows yet.")
        stamp = timezone.now().astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.stdout.write(f"{stamp} seq={last.seq} hash={last.row_hash} count={last.seq}")
