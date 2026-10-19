import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

DEMO_USERS = [
    ("meena", "admin"),
    ("priya", "owner"),
    ("anita", "owner"),
    ("ravi", "viewer"),
    ("sunil", "viewer"),
    ("kiran", "viewer"),
]


class Command(BaseCommand):
    help = "Create demo users (safe to run twice)."

    def handle(self, *args, **options):
        password = os.environ.get("SEED_PASSWORD")
        if not password:
            raise CommandError("Set SEED_PASSWORD in the environment or .env file.")
        User = get_user_model()
        created_count = 0
        for username, role in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"role": role, "email": f"{username}@example.com"},
            )
            if created:
                user.set_password(password)
                user.save()
                created_count += 1
        self.stdout.write(self.style.SUCCESS(f"seed done: {created_count} created"))