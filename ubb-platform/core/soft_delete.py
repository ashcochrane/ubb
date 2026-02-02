"""
Soft delete support: sets deleted_at instead of removing from database.

Policy: Undelete only. Once soft-deleted, records are hidden from default queries
but can be restored. Hard delete is not supported through the ORM.
"""

from django.db import models
from django.utils import timezone


class SoftDeleteManager(models.Manager):
    """Default manager that excludes soft-deleted records."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager):
    """Manager that includes soft-deleted records."""
    pass


class SoftDeleteMixin(models.Model):
    """
    Mixin that adds soft delete functionality.

    Adds:
    - deleted_at: DateTimeField, null when active
    - objects: SoftDeleteManager (excludes deleted)
    - all_objects: AllObjectsManager (includes deleted)
    - soft_delete(): sets deleted_at
    - restore(): clears deleted_at
    - delete() override: calls soft_delete() instead
    """

    deleted_at = models.DateTimeField(null=True, blank=True, default=None, db_index=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def soft_delete(self):
        """Soft delete this record."""
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    def restore(self):
        """Restore a soft-deleted record."""
        self.deleted_at = None
        self.save(update_fields=["deleted_at", "updated_at"])

    def delete(self, *args, **kwargs):
        """Override delete to soft-delete instead."""
        self.soft_delete()

    @property
    def is_deleted(self):
        return self.deleted_at is not None
