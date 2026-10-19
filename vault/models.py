from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        OWNER = "owner", "Document owner"
        VIEWER = "viewer", "Viewer"

    # The ONLY place a user's role is stored. Default is least privilege.
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.VIEWER)
    # is_active = False means "disabled"; Django already refuses those users.
