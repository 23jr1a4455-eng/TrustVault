import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from vault.models import Document, Grant

DEMO_USERS = [
    ("meena", "admin"),
    ("priya", "owner"),
    ("anita", "owner"),
    ("ravi", "viewer"),
    ("sunil", "viewer"),
    ("kiran", "viewer"),
]

# (owner, title, category, person who gets access, level). All fake.
DEMO_DOCUMENTS = [
    ("priya", "Salary letter - Ravi (demo)", "HR", "ravi", "read"),
    ("priya", "Offer letter - Kiran (demo)", "HR", None, None),
    ("anita", "Supplier contract (demo)", "Legal", "kiran", "edit"),
]


class Command(BaseCommand):
    help = "Create demo users and fake documents (safe to run twice)."

    def handle(self, *args, **options):
        password = os.environ.get("SEED_PASSWORD")
        if not password:
            raise CommandError("Set SEED_PASSWORD in the environment or .env file.")
        User = get_user_model()
        created_users = 0
        for username, role in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"role": role, "email": f"{username}@example.com"},
            )
            if created:
                user.set_password(password)
                user.save()
                created_users += 1

        created_docs = 0
        for owner_name, title, category, grantee_name, level in DEMO_DOCUMENTS:
            owner = User.objects.get(username=owner_name)
            document, created = Document.objects.get_or_create(
                owner=owner, title=title, defaults={"category": category}
            )
            created_docs += int(created)
            if grantee_name:
                grantee = User.objects.get(username=grantee_name)
                if not Grant.objects.active().filter(document=document, user=grantee).exists():
                    # Seed grants are not audited. Real grants go through the audited
                    # grant service built on Day 4.
                    Grant.objects.create(
                        document=document, user=grantee, level=level, granted_by=owner
                    )
        self.stdout.write(
            self.style.SUCCESS(f"seed done: {created_users} users, {created_docs} documents created")
        )
