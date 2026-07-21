"""The append-only audit ledger (ADR-004 §4, §6).

A durable, tenant-scoped record of "who did what, when, to which resource",
written in the same database transaction as the change it describes. Sibling to
the events outbox — but a LEDGER, not a QUEUE: rows are never processed, retried,
swept, or deleted by age, and (secrets, §4) nothing is captured indiscriminately
— only the curated metadata a mutation site chooses to attach, so signing secrets
and key material structurally cannot reach this permanent table.

Placement is the platform kernel (ADR-004 §6): any product or composition-layer
endpoint records through the one ``record()`` surface without crossing a product
boundary — infrastructure every product needs is not a fifth product. Not inside
``events/``: co-housing would re-blur the queue-vs-ledger line.
"""
from django.db import models

from apps.platform.audit.actors import SYSTEM
from core.models import BaseModel


class AuditRecord(BaseModel):
    # Inherits id (UUID pk) + created_at + updated_at from BaseModel, for
    # uniformity with every other kernel model. ``created_at`` IS the action
    # timestamp; ``updated_at`` is inert here — the append-only save() guard means
    # a row is never updated, so it always equals ``created_at``.

    # The tenant whose account this action is on — every row is tenant-scoped,
    # the axis the feed (#82) reads and paginates by. For a tenant principal this
    # is the tenant it authenticated against (the account being administered),
    # even when the touched resource lands on that tenant's sandbox sibling.
    tenant_id = models.UUIDField(db_index=True)

    # The registered action name (apps.platform.audit.actions). Indexed for
    # "show me every rate_card.published"-style filters.
    action = models.CharField(max_length=100, db_index=True)

    # The actor snapshot, denormalised so history survives the principal being
    # renamed or deleted (ADR-004 §4). ``actor_kind`` is the open enum; ``id`` and
    # ``display`` are point-in-time copies, never a live FK.
    actor_kind = models.CharField(max_length=20, default=SYSTEM)
    actor_id = models.CharField(max_length=255, blank=True, default="")
    actor_display = models.CharField(max_length=255, blank=True, default="")

    # The target resource: a stable type name (e.g. "api_key") plus its id.
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=255, blank=True, default="")

    # Links the entry to any outbox events the same request emitted (ADR-004 §4).
    correlation_id = models.CharField(max_length=100, blank=True, default="")

    # Curated, per-action metadata — NEVER an automatic before/after snapshot, so
    # secrets structurally cannot reach this permanent table (ADR-004 §4).
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ubb_audit_record"
        indexes = [
            # The feed's access path (#82): a tenant's entries, newest first.
            models.Index(
                fields=["tenant_id", "created_at"],
                name="idx_audit_tenant_created",
            ),
            # "Who changed THIS resource?" — resource history within a tenant.
            models.Index(
                fields=["tenant_id", "resource_type", "resource_id"],
                name="idx_audit_tenant_resource",
            ),
        ]

    def __str__(self):
        return (
            f"AuditRecord({self.action} by {self.actor_kind} "
            f"on {self.resource_type})"
        )

    def save(self, *args, **kwargs):
        # Append-only (ADR-004 §4): a row is written once and never updated. A
        # rolled-back mutation leaves no row because record() rides the mutation's
        # transaction — and a row that DID land is immutable thereafter. Deletion
        # is left available for the #82 sandbox-reset sweep (that clears
        # sandbox-scoped entries and is itself recorded).
        if not self._state.adding:
            raise ValueError(
                "AuditRecord is append-only; an existing row cannot be updated"
            )
        super().save(*args, **kwargs)
