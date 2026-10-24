from django.core.management.base import BaseCommand, CommandError

from vault.services.audit_chain import parse_anchors, verify_chain


class Command(BaseCommand):
    help = "Check the whole audit chain (and optionally the saved anchors). Exits with an error if anything is wrong."

    def add_arguments(self, parser):
        parser.add_argument("--anchors", help="Path of the anchors log, for example docs/anchors.log")

    def handle(self, *args, **options):
        anchors = None
        if options["anchors"]:
            with open(options["anchors"], encoding="utf-8") as handle:
                anchors = parse_anchors(handle.read())
        report = verify_chain(anchors)
        self.stdout.write(
            f"checked {report.checked} chained rows, {report.legacy} older rows without a chain, "
            f"{report.anchors_checked} anchors"
        )
        if not report.ok:
            for problem in report.problems:
                self.stderr.write(f"PROBLEM: {problem}")
            raise CommandError("Audit chain verification FAILED.")
        self.stdout.write(self.style.SUCCESS("Audit chain verified."))
