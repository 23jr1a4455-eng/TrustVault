import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from vault.models import User
from vault.services import audit


class Command(BaseCommand):
    help = "Create a user. Roles are set only here, never from the website."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--role", choices=[r.value for r in User.Role], default="viewer")
        parser.add_argument("--email", default="")

    def handle(self, *args, **options):
        username, role = options["username"], options["role"]
        UserModel = get_user_model()
        if UserModel.objects.filter(username=username).exists():
            raise CommandError("That username already exists.")
        password = os.environ.get("NEW_USER_PASSWORD") or getpass.getpass("Password: ")
        try:
            validate_password(password)
        except ValidationError as problem:
            raise CommandError(" ".join(problem.messages))
        user = UserModel.objects.create_user(username=username, email=options["email"], password=password, role=role)
        audit.record(actor=None, action="user.created", allowed=True,
                     detail={"username": username, "role": role, "via": "command line"})
        self.stdout.write(self.style.SUCCESS(f"Created {user.get_username()} ({role})."))
