"""Data models for the vault app."""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        OWNER = "owner", "Document owner"
        VIEWER = "viewer", "Viewer"

    # The ONLY place a user's role is stored. Default is least privilege.
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.VIEWER)
    # is_active = False means "disabled"; Django already refuses those users.


class Document(models.Model):
    """Document metadata. The file bytes are added on Day 3."""

    # Random, unguessable id. It is NOT a permission: the gate still decides every time.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="owned_documents")
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)  # soft delete

    def __str__(self):
        return self.title


class DocumentFile(models.Model):
    """The file bytes, kept in PostgreSQL in their own table.

    The host's disk is wiped on every redeploy, and a separate table means listing
    documents never loads file contents. Bytes are only ever served by the download
    view, after the gate.
    """

    document = models.OneToOneField(Document, on_delete=models.PROTECT, related_name="file")
    original_name = models.CharField(max_length=255)  # cleaned, display and download name only
    content_type = models.CharField(max_length=100)  # decided by us from the file itself
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    data = models.BinaryField()
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="uploaded_files")
    uploaded_at = models.DateTimeField(auto_now_add=True)


class GrantQuerySet(models.QuerySet):
    def active(self):
        """Grants that are not revoked and not expired, judged by the database clock now."""
        now = timezone.now()
        return self.filter(revoked_at__isnull=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )


class Grant(models.Model):
    """One person's access to one document. Nothing here is inherited from anywhere."""

    class Level(models.TextChoices):
        READ = "read", "Read"
        EDIT = "edit", "Edit"  # edit includes read

    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="grants")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="grants_received")
    level = models.CharField(max_length=4, choices=Level.choices)
    granted_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="grants_given")
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="grants_revoked"
    )

    objects = GrantQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document", "user"],
                condition=Q(revoked_at__isnull=True),
                name="one_active_grant_per_user_and_document",
            )
        ]


class AppendOnlyQuerySet(models.QuerySet):
    """Refuses bulk changes. The database trigger (PostgreSQL) is the second lock."""

    def update(self, **kwargs):
        raise RuntimeError("Audit events are append-only.")

    def delete(self):
        raise RuntimeError("Audit events are append-only.")

    def bulk_update(self, *args, **kwargs):
        raise RuntimeError("Audit events are append-only.")

    def bulk_create(
        self,
        objs,
        batch_size=None,
        ignore_conflicts=False,
        update_conflicts=False,
        update_fields=None,
        unique_fields=None,
    ):
        if update_conflicts:
            raise RuntimeError("Audit events are append-only.")
        return super().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )


class AuditChainHead(models.Model):
    """One row: where the audit chain currently ends. Locking it serialises writers,
    so two requests can never extend the chain from the same point."""

    last_seq = models.BigIntegerField(default=0)
    last_hash = models.CharField(max_length=64, default="0" * 64)


class AuditEvent(models.Model):
    """Append-only record of who tried what, allowed or refused.

    No foreign keys on purpose: deleting or renaming a user or document must never
    change history. Each row carries the keyed hash (HMAC) of itself and of the row
    before it, so any edit, deletion or insertion breaks the chain.
    """

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor_id = models.BigIntegerField(null=True, blank=True)
    actor_name = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    allowed = models.BooleanField()
    document_id = models.UUIDField(null=True, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    # NULL seq = written before the chain existed (Days 2 to 4).
    seq = models.BigIntegerField(null=True, blank=True, unique=True)
    prev_hash = models.CharField(max_length=64, blank=True)
    row_hash = models.CharField(max_length=64, blank=True)

    objects = AppendOnlyQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("Audit events are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit events are append-only.")
