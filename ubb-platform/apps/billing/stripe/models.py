from django.db import models
from django.utils import timezone

from core.models import BaseModel

WEBHOOK_EVENT_STATUSES = [
    ("processing", "Processing"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
    ("skipped", "Skipped"),
]


class StripeWebhookEvent(BaseModel):
    """
    Tracks Stripe webhook event processing for deduplication and auditing.

    Original outcome (succeeded/failed/skipped) is never overwritten by duplicates.
    Duplicate deliveries increment duplicate_count and update last_seen_at.
    """
    stripe_event_id = models.CharField(max_length=255, unique=True, db_index=True)
    event_type = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=20, choices=WEBHOOK_EVENT_STATUSES, default="processing")
    failure_reason = models.JSONField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    duplicate_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ubb_stripe_webhook_event"
        indexes = [
            models.Index(fields=["status", "created_at"], name="idx_webhook_status_created"),
            models.Index(fields=["created_at"], name="idx_webhook_created_at"),
        ]

    def __str__(self):
        return f"WebhookEvent({self.stripe_event_id}: {self.status})"
